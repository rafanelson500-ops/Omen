"""Tradovate live client: REST auth + token renewal + trading/MD WebSockets + OSO bracket orders.

Quirks (learned from docs + forum):
    - Auth POST: /auth/accesstokenrequest with {name, password, appId, appVersion,
      cid, sec, deviceId}. Returns accessToken, mdAccessToken, expirationTime.
    - Token renewal: /auth/renewaccesstoken MUST be called on the LIVE subdomain
      even for demo accounts. Authorization: Bearer <accessToken>.
    - Access tokens expire after ~80 min. We refresh every 30 min.
    - WebSocket custom frame protocol:
        'o'   on-open (no body)
        'h'   heartbeat  (respond with '[]')
        'a'   data frame followed by a JSON array of messages
        'c'   close frame
      Requests are 4 newline-separated lines: endpoint\\nid\\nquery\\nbody
    - After WS connect, FIRST frame must be: authorize\\n<id>\\n\\n<accessToken>
      (body is the raw token string, NOT JSON-wrapped)
    - Heartbeats: client must send '[]' every ~2.5s independent of server.
    - Trading WS uses accessToken. Market data WS uses mdAccessToken.
    - Orders: use order/placeoso to submit entry + bracket1 (stop) + bracket2 (target)
      in a single request.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

from cheese.config import round_to_tick
import websockets

from live.bus import BUS
from live.logger import get
from live.settings import LiveSettings

log = get("tradovate")

HEARTBEAT_INTERVAL_S = 2.5
RENEW_INTERVAL_S = 30 * 60  # refresh every 30 min (~2x headroom vs 80-min expiry)


@dataclass
class AuthState:
    access_token: str = ""
    md_access_token: str = ""
    expiration_time: str = ""
    user_id: int = 0
    name: str = ""
    last_refresh: float = 0.0


class _FrameRouter:
    """Tracks in-flight request IDs and resolves their futures on response."""

    def __init__(self) -> None:
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[dict]] = {}

    def next_id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    def track(self, req_id: int) -> asyncio.Future[dict]:
        fut: asyncio.Future[dict] = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        return fut

    def resolve(self, msg: dict[str, Any]) -> None:
        req_id = msg.get("i")
        if req_id is None:
            return
        fut = self._pending.pop(req_id, None)
        if fut and not fut.done():
            fut.set_result(msg)


class TradovateClient:
    """High-level Tradovate client: REST + trading WS + MD WS with auth + heartbeat."""

    def __init__(self, settings: LiveSettings) -> None:
        self.s = settings
        self.auth = AuthState()
        self.account_id: int | None = None
        self.account_spec: str = settings.tradovate.account_spec or ""
        self._http = httpx.AsyncClient(timeout=20.0)
        self._trading_ws: websockets.WebSocketClientProtocol | None = None
        self._md_ws: websockets.WebSocketClientProtocol | None = None
        self._trading_router = _FrameRouter()
        self._md_router = _FrameRouter()
        self._tasks: list[asyncio.Task] = []
        self._md_callbacks: list[Callable[[dict], Awaitable[None]]] = []
        self._shutdown = asyncio.Event()

    # ---------- lifecycle ---------------------------------------------------
    async def close(self) -> None:
        self._shutdown.set()
        for t in self._tasks:
            t.cancel()
        for ws in (self._trading_ws, self._md_ws):
            if ws:
                try:
                    await ws.close()
                except Exception:  # noqa: BLE001
                    pass
        await self._http.aclose()

    # ---------- REST auth ---------------------------------------------------
    async def authenticate(self) -> None:
        tc = self.s.tradovate
        if not tc.is_complete:
            raise RuntimeError("Tradovate credentials incomplete; check .env")
        body = {
            "name": tc.name,
            "password": tc.password,
            "appId": tc.app_id,
            "appVersion": tc.app_version,
            "deviceId": tc.device_id,
            "cid": tc.cid,
            "sec": tc.sec,
        }
        log.info(f"authenticating (env={self.s.env}) ...")
        r = await self._http.post(f"{self.s.tradovate_rest}/auth/accesstokenrequest", json=body)
        r.raise_for_status()
        j = r.json()
        if "errorText" in j and j.get("errorText"):
            raise RuntimeError(f"Tradovate auth error: {j['errorText']}")
        self.auth = AuthState(
            access_token=j["accessToken"],
            md_access_token=j.get("mdAccessToken", j["accessToken"]),
            expiration_time=j.get("expirationTime", ""),
            user_id=j.get("userId", 0),
            name=j.get("name", tc.name),
            last_refresh=time.time(),
        )
        await BUS.publish("status", {"component": "tradovate_auth", "ok": True,
                                     "expires": self.auth.expiration_time,
                                     "user_id": self.auth.user_id})
        log.info(f"authenticated as {self.auth.name} (user={self.auth.user_id}), "
                 f"token expires {self.auth.expiration_time}")

    async def renew_once(self) -> None:
        """Use the LIVE subdomain regardless of env (Tradovate quirk)."""
        if not self.auth.access_token:
            return
        url = f"{self.s.tradovate_rest_live}/auth/renewaccesstoken"
        headers = {"Authorization": f"Bearer {self.auth.access_token}"}
        r = await self._http.get(url, headers=headers)
        if r.status_code >= 400:
            log.warning(f"renew got HTTP {r.status_code}: {r.text[:200]}")
            # re-auth as a fallback
            await self.authenticate()
            return
        j = r.json()
        if "accessToken" in j:
            self.auth.access_token = j["accessToken"]
            self.auth.md_access_token = j.get("mdAccessToken", self.auth.md_access_token)
            self.auth.expiration_time = j.get("expirationTime", self.auth.expiration_time)
            self.auth.last_refresh = time.time()
            await BUS.publish("status", {"component": "tradovate_auth", "ok": True,
                                         "expires": self.auth.expiration_time,
                                         "renewed": True})
            log.info(f"renewed token; expires {self.auth.expiration_time}")

    async def _renew_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=RENEW_INTERVAL_S)
                return
            except asyncio.TimeoutError:
                try:
                    await self.renew_once()
                except Exception as e:  # noqa: BLE001
                    log.error(f"renew failed: {e!r}")

    # ---------- REST helpers -----------------------------------------------
    async def _rest_get(self, path: str, params: dict | None = None) -> Any:
        r = await self._http.get(
            f"{self.s.tradovate_rest}{path}",
            params=params,
            headers={"Authorization": f"Bearer {self.auth.access_token}"},
        )
        r.raise_for_status()
        return r.json()

    async def list_accounts(self) -> list[dict]:
        return await self._rest_get("/account/list")

    async def list_positions(self) -> list[dict]:
        return await self._rest_get("/position/list")

    async def list_orders(self) -> list[dict]:
        return await self._rest_get("/order/list")

    async def list_cash_balances(self) -> list[dict]:
        return await self._rest_get("/cashBalance/list")

    async def get_cash_balance_snapshot(self) -> dict | None:
        """Best-effort current balance snapshot (includes net liq/realized/open P&L).

        The v1 endpoint `/cashBalance/getcashbalancesnapshot` requires a POST
        with {accountId}; we fall back to the latest item from `/cashBalance/list`
        if the snapshot endpoint is unavailable.
        """
        if self.account_id is None:
            return None
        try:
            r = await self._http.post(
                f"{self.s.tradovate_rest}/cashBalance/getcashbalancesnapshot",
                json={"accountId": self.account_id},
                headers={"Authorization": f"Bearer {self.auth.access_token}"},
            )
            if r.status_code == 200:
                return r.json()
        except Exception:  # noqa: BLE001
            pass
        try:
            rows = await self.list_cash_balances()
            mine = [b for b in rows if b.get("accountId") == self.account_id]
            return mine[-1] if mine else (rows[-1] if rows else None)
        except Exception:  # noqa: BLE001
            return None

    async def _contract_name(self, contract_id: int, cache: dict[int, str]) -> str:
        if contract_id in cache:
            return cache[contract_id]
        try:
            j = await self._rest_get("/contract/item", params={"id": contract_id})
            name = j.get("name") or str(contract_id)
        except Exception:  # noqa: BLE001
            name = str(contract_id)
        cache[contract_id] = name
        return name

    async def get_account_snapshot(self) -> dict:
        """Fetch positions + working orders + balance for our account.

        Contract IDs are resolved to symbol names so the dashboard can render
        them directly without a second round-trip.
        """
        if not self.auth.access_token or self.account_id is None:
            return {"ready": False}

        positions, orders, balance = await asyncio.gather(
            self.list_positions(), self.list_orders(), self.get_cash_balance_snapshot(),
            return_exceptions=True,
        )
        if isinstance(positions, Exception):
            log.warning(f"list_positions failed: {positions!r}")
            positions = []
        if isinstance(orders, Exception):
            log.warning(f"list_orders failed: {orders!r}")
            orders = []
        if isinstance(balance, Exception):
            log.warning(f"cash balance failed: {balance!r}")
            balance = None

        mine_pos = [p for p in positions if p.get("accountId") == self.account_id]
        mine_pos = [p for p in mine_pos if (p.get("netPos") or 0) != 0]
        # Working = not in a terminal state. Tradovate reports order state via
        # /orderVersion but /order/list already exposes `ordStatus`.
        TERMINAL = {"Filled", "Canceled", "Cancelled", "Rejected", "Expired"}
        mine_ord = [o for o in orders
                    if o.get("accountId") == self.account_id
                    and (o.get("ordStatus") or "").strip() not in TERMINAL]

        name_cache: dict[int, str] = {}
        for p in mine_pos:
            cid = p.get("contractId")
            if cid is not None:
                p["symbol"] = await self._contract_name(int(cid), name_cache)
        for o in mine_ord:
            cid = o.get("contractId")
            if cid is not None:
                o["symbol"] = await self._contract_name(int(cid), name_cache)

        return {
            "ready": True,
            "account_id": self.account_id,
            "account_spec": self.account_spec,
            "positions": mine_pos,
            "orders": mine_ord,
            "balance": balance,
        }

    async def account_poll_loop(self, interval: float = 10.0) -> None:
        """Background poller: pushes account snapshots onto the bus."""
        await BUS.publish("status", {"component": "tradovate_account", "ok": False,
                                     "note": "poll starting"})
        while not self._shutdown.is_set():
            try:
                snap = await self.get_account_snapshot()
                if snap.get("ready"):
                    await BUS.publish("account", snap)
                    await BUS.publish("status", {
                        "component": "tradovate_account", "ok": True,
                        "positions": len(snap.get("positions", [])),
                        "orders": len(snap.get("orders", [])),
                    })
            except Exception as e:  # noqa: BLE001
                log.warning(f"account poll failed: {e!r}")
                await BUS.publish("status", {"component": "tradovate_account",
                                             "ok": False, "error": repr(e)})
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                continue

    async def find_front_month(self, symbol_root: str) -> dict:
        """Find the current front-month contract for a product root via REST."""
        r = await self._http.get(
            f"{self.s.tradovate_rest}/contract/suggest",
            params={"t": symbol_root, "l": 20},
            headers={"Authorization": f"Bearer {self.auth.access_token}"},
        )
        r.raise_for_status()
        contracts = r.json()
        # Pick the one with closest expiration >= today among matching roots
        cands = [c for c in contracts if c.get("name", "").startswith(symbol_root)
                 and c.get("productType", "Future") == "Future"]
        if not cands:
            raise RuntimeError(f"No {symbol_root} futures returned by contract/suggest")
        # Prefer one with 'front-month' status if Tradovate tags it; else the soonest
        cands.sort(key=lambda c: c.get("maturityMonthYear", ""))
        pick = cands[0]
        log.info(f"front-month {symbol_root} -> {pick.get('name')} id={pick.get('id')}")
        return pick

    async def bootstrap(self) -> dict:
        """Authenticate + discover account + front-month contract. Returns contract dict."""
        await self.authenticate()
        accts = await self.list_accounts()
        if not accts:
            raise RuntimeError("No accounts returned by /account/list")
        if self.account_spec:
            match = next((a for a in accts if a.get("name") == self.account_spec), None)
            if not match:
                log.warning(f"account_spec {self.account_spec!r} not found; using first")
                match = accts[0]
        else:
            match = accts[0]
        self.account_id = match["id"]
        self.account_spec = match["name"]
        log.info(f"account: {self.account_spec} (id={self.account_id})")
        return await self.find_front_month(self.s.symbol_root)

    # ---------- WebSocket infrastructure -----------------------------------
    async def _ws_heartbeat_loop(self, ws: websockets.WebSocketClientProtocol,
                                 name: str) -> None:
        while not self._shutdown.is_set():
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL_S)
                await ws.send("[]")
            except (websockets.ConnectionClosed, asyncio.CancelledError):
                log.warning(f"{name} WS heartbeat loop: connection closed")
                return
            except Exception as e:  # noqa: BLE001
                log.warning(f"{name} WS heartbeat loop error: {e!r}")
                return

    async def _ws_connect(self, url: str, token: str, name: str,
                          router: _FrameRouter,
                          on_a_frame: Callable[[dict], Awaitable[None]] | None = None
                          ) -> websockets.WebSocketClientProtocol:
        log.info(f"{name} WS connecting -> {url}")
        ws = await websockets.connect(url, max_size=2**22, ping_interval=None)
        # First frame from server is 'o'
        first = await asyncio.wait_for(ws.recv(), timeout=10)
        if first != "o":
            log.warning(f"{name} WS first frame was {first!r}, expected 'o'")

        # Authorize
        auth_id = router.next_id()
        fut = router.track(auth_id)
        await ws.send(f"authorize\n{auth_id}\n\n{token}")
        # Kick heartbeat loop now (server will also heartbeat but we send independently)
        self._tasks.append(asyncio.create_task(self._ws_heartbeat_loop(ws, name)))
        self._tasks.append(asyncio.create_task(self._ws_reader(ws, name, router, on_a_frame)))
        # Await auth response
        try:
            resp = await asyncio.wait_for(fut, timeout=10)
        except asyncio.TimeoutError:
            raise RuntimeError(f"{name} WS authorize timed out")
        s = resp.get("s")
        if s != 200:
            raise RuntimeError(f"{name} WS authorize failed: {resp}")
        await BUS.publish("status", {"component": f"tradovate_{name}_ws", "ok": True})
        log.info(f"{name} WS authorized")
        return ws

    async def _ws_reader(self, ws: websockets.WebSocketClientProtocol, name: str,
                         router: _FrameRouter,
                         on_a_frame: Callable[[dict], Awaitable[None]] | None) -> None:
        try:
            async for raw in ws:
                if not raw:
                    continue
                t = raw[0]
                body = raw[1:]
                if t == "h":
                    # server heartbeat; respond to be safe
                    try:
                        await ws.send("[]")
                    except Exception:  # noqa: BLE001
                        pass
                    continue
                if t == "a":
                    try:
                        messages = json.loads(body)
                    except json.JSONDecodeError:
                        log.warning(f"{name} WS could not parse: {body[:200]!r}")
                        continue
                    for m in messages:
                        router.resolve(m)
                        if on_a_frame:
                            try:
                                await on_a_frame(m)
                            except Exception as e:  # noqa: BLE001
                                log.error(f"{name} WS callback error: {e!r}")
                    continue
                if t == "c":
                    log.warning(f"{name} WS close frame received: {body!r}")
                    return
                # 'o' already consumed in _ws_connect; ignore stray
        except websockets.ConnectionClosed as e:
            log.warning(f"{name} WS closed: code={e.code} reason={e.reason!r}")
            await BUS.publish("status", {"component": f"tradovate_{name}_ws", "ok": False,
                                         "code": e.code, "reason": str(e.reason)})
        except Exception as e:  # noqa: BLE001
            log.error(f"{name} WS reader error: {e!r}")

    async def _ws_request(self, ws: websockets.WebSocketClientProtocol,
                          router: _FrameRouter,
                          endpoint: str, body: Any = None, query: str = "") -> dict:
        req_id = router.next_id()
        fut = router.track(req_id)
        body_s = "" if body is None else (body if isinstance(body, str) else json.dumps(body))
        frame = f"{endpoint}\n{req_id}\n{query}\n{body_s}"
        await ws.send(frame)
        return await asyncio.wait_for(fut, timeout=15)

    # ---------- Public WS ops ----------------------------------------------
    async def connect_trading_ws(self) -> None:
        self._trading_ws = await self._ws_connect(
            self.s.tradovate_ws_trading, self.auth.access_token, "trading",
            self._trading_router, on_a_frame=self._on_trading_frame,
        )
        self._tasks.append(asyncio.create_task(self._renew_loop()))

    async def connect_md_ws(self) -> None:
        self._md_ws = await self._ws_connect(
            self.s.tradovate_ws_md, self.auth.md_access_token, "md",
            self._md_router, on_a_frame=self._on_md_frame,
        )

    async def subscribe_quote(self, symbol: str) -> None:
        if not self._md_ws:
            raise RuntimeError("md WS not connected")
        resp = await self._ws_request(self._md_ws, self._md_router,
                                      "md/subscribequote", {"symbol": symbol})
        if resp.get("s") != 200:
            log.warning(f"subscribequote {symbol} -> {resp}")
        else:
            log.info(f"subscribed quote {symbol}")

    async def _on_md_frame(self, m: dict) -> None:
        # MD frames have shape {e: "md", d: {quotes: [...], ...}} or similar
        if m.get("e") == "md":
            d = m.get("d") or {}
            # quotes
            for q in d.get("quotes", []):
                px = (q.get("entries", {}).get("Trade", {}).get("price")
                      or q.get("entries", {}).get("Bid", {}).get("price"))
                if px is not None:
                    await BUS.publish("price", {"src": "tradovate_md",
                                                "symbol": q.get("contractId"),
                                                "price": px})

    async def _on_trading_frame(self, m: dict) -> None:
        # Order-related events surface here via server-pushed updates
        e = m.get("e")
        if e in {"props", "clockupdate"}:
            return
        await BUS.publish("order", {"src": "tradovate", "event": e, "msg": m})

    # ---------- Orders ------------------------------------------------------
    async def place_bracket_market(self, contract: dict, side: str, qty: int,
                                   stop_px: float, target_px: float) -> dict:
        """Submit a market entry + stop + target via /order/placeoso.

        Returns the response dict. Subsequent fill / replace events will arrive
        via the trading WS 'a' frames and be published on the 'order' channel.
        """
        assert self._trading_ws is not None and self.account_id is not None
        stop_px_tick = round_to_tick(stop_px)
        target_px_tick = round_to_tick(target_px)
        body = {
            "accountSpec": self.account_spec,
            "accountId": self.account_id,
            "action": side,
            "symbol": contract["name"],
            "orderQty": qty,
            "orderType": "Market",
            "isAutomated": True,
            "bracket1": {
                "action": "Sell" if side == "Buy" else "Buy",
                "orderType": "Stop",
                "stopPrice": stop_px_tick,
                "timeInForce": "GTC",
            },
            "bracket2": {
                "action": "Sell" if side == "Buy" else "Buy",
                "orderType": "Limit",
                "price": target_px_tick,
                "timeInForce": "GTC",
            },
        }

        if self.s.dry_run:
            log.warning(f"[DRY RUN] would submit OSO: {json.dumps(body)}")
            await BUS.publish("order", {"src": "local", "event": "dry_submit", "body": body})
            return {"s": 200, "d": {"dry_run": True, "body": body}}

        log.info(f"submitting OSO bracket: {side} {qty} {contract['name']} "
                 f"stop={body['bracket1']['stopPrice']} tgt={body['bracket2']['price']}")
        resp = await self._ws_request(self._trading_ws, self._trading_router,
                                      "order/placeoso", body)
        await BUS.publish("order", {"src": "tradovate", "event": "place_response", "msg": resp})
        return resp

    async def close_position_market(self, contract: dict, side_to_close: str, qty: int) -> dict:
        """Emergency/time-stop flat-out at market."""
        assert self._trading_ws is not None and self.account_id is not None
        body = {
            "accountSpec": self.account_spec,
            "accountId": self.account_id,
            "action": "Sell" if side_to_close == "Buy" else "Buy",
            "symbol": contract["name"],
            "orderQty": qty,
            "orderType": "Market",
            "isAutomated": True,
        }
        if self.s.dry_run:
            log.warning(f"[DRY RUN] would flatten: {json.dumps(body)}")
            return {"s": 200, "d": {"dry_run": True, "body": body}}
        return await self._ws_request(self._trading_ws, self._trading_router,
                                      "order/placeorder", body)
