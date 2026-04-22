"""GEXbot realtime orderflow hub client (Azure Web PubSub).

Flow (per GEXbot docs + community example):
    1. GET /v2/negotiate  (Authorization: Bearer <key>)
         -> { websocket_urls: {classic, state_gex, state_greeks_zero, state_greeks_one, orderflow}, prefix }
    2. The URLs are Azure Web PubSub connection strings. Use the official
       azure-messaging-webpubsubclient SDK to connect.
    3. Join groups named "{prefix}_{ticker}_{package}_{category}".
       For the orderflow hub with ES_SPX: "{prefix}_ES_SPX_orderflow_orderflow".
    4. Each GROUP_MESSAGE payload is a serialized `google.protobuf.Any`.
         - Any.type_url indicates the message type (e.g. "type.googleapis.com/proto.orderflow....")
         - Any.value contains the serialized inner protobuf, which is (per GEXbot docs)
           Zstandard-compressed. After decompress we have the inner protobuf bytes.
    5. Since we don't have the .proto file, we brute-force-parse the inner protobuf
       wire format and map field numbers -> (name, type) using our known flat
       schema (37 fields). Field numbers are our best guess based on the sample
       data's key order; if the mapping is off we'll see it in the dashboard log
       and can tweak `ORDERFLOW_FIELD_MAP` in one spot.

Threading model:
    The Azure SDK's callbacks fire on its own thread. We bridge into the async
    event bus via `BUS.publish_threadsafe`, which uses
    `loop.call_soon_threadsafe` internally. The SDK's `open()` blocks, so we
    run it in a daemon thread and await a pair of `threading.Event`s from the
    async side.
"""
from __future__ import annotations

import asyncio
import struct
import threading
from typing import Any, Optional

import httpx
import zstandard as zstd
from azure.messaging.webpubsubclient import WebPubSubClient
from azure.messaging.webpubsubclient.models import (
    CallbackType,
    OnConnectedArgs,
    OnDisconnectedArgs,
    OnGroupDataMessageArgs,
)
from google.protobuf import any_pb2

from live.bus import BUS
from live.logger import get

log = get("gexbot")

NEGOTIATE_URL = "https://api.gex.bot/v2/negotiate"
USER_AGENT = "cheese-trading-live/1.0"


# ---------- Orderflow schema (flat; 37 scalar fields) -----------------------
# Field numbers (keys) are a best-guess 1..37 mapping in the order we've seen
# in sample data. If a field doesn't decode sanely, just reorder the numbers.
ORDERFLOW_FIELD_MAP: dict[int, tuple[str, str]] = {
    1:  ("timestamp", "int64"),
    2:  ("ticker", "string"),
    3:  ("spot", "double"),
    4:  ("z_mlgamma", "double"),
    5:  ("z_msgamma", "double"),
    6:  ("o_mlgamma", "double"),
    7:  ("o_msgamma", "double"),
    8:  ("zero_mcall", "double"),
    9:  ("zero_mput", "double"),
    10: ("one_mcall", "double"),
    11: ("one_mput", "double"),
    12: ("zcvr", "double"),
    13: ("ocvr", "double"),
    14: ("zgr", "double"),
    15: ("ogr", "double"),
    16: ("zvanna", "double"),
    17: ("ovanna", "double"),
    18: ("zcharm", "double"),
    19: ("ocharm", "double"),
    20: ("agg_dex", "double"),
    21: ("one_agg_dex", "double"),
    22: ("agg_call_dex", "double"),
    23: ("one_agg_call_dex", "double"),
    24: ("agg_put_dex", "double"),
    25: ("one_agg_put_dex", "double"),
    26: ("net_dex", "double"),
    27: ("one_net_dex", "double"),
    28: ("net_call_dex", "double"),
    29: ("one_net_call_dex", "double"),
    30: ("net_put_dex", "double"),
    31: ("one_net_put_dex", "double"),
    32: ("dexoflow", "double"),
    33: ("gexoflow", "double"),
    34: ("cvroflow", "double"),
    35: ("one_dexoflow", "double"),
    36: ("one_gexoflow", "double"),
    37: ("one_cvroflow", "double"),
}


def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if i >= len(buf):
            raise ValueError("truncated varint")
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, i
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def _parse_flat_proto(
    data: bytes,
    schema: dict[int, tuple[str, str]],
) -> tuple[dict[str, Any], dict[int, Any]]:
    """Walk a protobuf wire-format message. Return (named_out, raw_by_field).

    Only supports wire types 0 (varint), 1 (fixed64), 2 (length-delimited), 5 (fixed32).
    Unknown field numbers are still captured in raw_by_field for debugging.
    """
    named: dict[str, Any] = {}
    raw: dict[int, Any] = {}
    i = 0
    n = len(data)
    while i < n:
        try:
            tag, i = _read_varint(data, i)
        except ValueError:
            break
        field_num = tag >> 3
        wire = tag & 0x07
        try:
            if wire == 0:  # varint
                val, i = _read_varint(data, i)
            elif wire == 1:  # fixed64 / double
                if i + 8 > n:
                    break
                val = struct.unpack_from("<d", data, i)[0]
                i += 8
            elif wire == 2:  # length-delimited (string/bytes/submsg)
                length, i = _read_varint(data, i)
                if i + length > n:
                    break
                chunk = data[i:i + length]
                i += length
                try:
                    val = chunk.decode("utf-8")
                except UnicodeDecodeError:
                    val = chunk.hex()
            elif wire == 5:  # fixed32 / float
                if i + 4 > n:
                    break
                val = struct.unpack_from("<f", data, i)[0]
                i += 4
            else:
                # groups (3,4) are deprecated; bail out
                break
        except (struct.error, ValueError):
            break
        raw[field_num] = val
        meta = schema.get(field_num)
        if meta is not None:
            name, typ = meta
            if typ == "int64" and isinstance(val, float):
                val = int(val)
            named[name] = val
    return named, raw


# ---------- Client ----------------------------------------------------------
class GEXbotHub:
    """Single-hub subscriber. Spawn one per hub you want (orderflow by default)."""

    def __init__(
        self,
        api_key: str,
        hub: str = "orderflow",
        ticker: str = "ES_SPX",
        package: str | None = None,
        category: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.hub = hub
        self.ticker = ticker
        self.package = package or self._default_package(hub)
        self.category = category or self._default_category(hub)
        self.prefix: str = ""
        self.hub_url: str = ""
        self.groups: list[str] = []
        self._client: Optional[WebPubSubClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connected_evt = threading.Event()
        self._disconnected_evt = threading.Event()
        self._dctx = zstd.ZstdDecompressor()

    @staticmethod
    def _default_package(hub: str) -> str:
        return {
            "classic": "classic",
            "state_gex": "state",
            "state_greeks_zero": "state",
            "state_greeks_one": "state",
            "orderflow": "orderflow",
        }.get(hub, hub)

    @staticmethod
    def _default_category(hub: str) -> str:
        return {
            "classic": "gex_full",
            "state_gex": "gex_full",
            "state_greeks_zero": "gamma_zero",
            "state_greeks_one": "gamma_one",
            "orderflow": "orderflow",
        }.get(hub, hub)

    # ---------- REST negotiate ---------------------------------------------
    async def negotiate(self) -> None:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(NEGOTIATE_URL, headers=headers)
        if r.status_code != 200:
            raise RuntimeError(f"negotiate failed HTTP {r.status_code}: {r.text[:300]}")
        j = r.json()
        self.prefix = j.get("prefix") or "red"
        self.hub_url = (j.get("websocket_urls") or {}).get(self.hub, "")
        if not self.hub_url:
            raise RuntimeError(f"/negotiate response missing '{self.hub}' URL: {j}")
        self.groups = [f"{self.prefix}_{self.ticker}_{self.package}_{self.category}"]
        log.info(
            f"negotiate ok: hub={self.hub} prefix={self.prefix!r} "
            f"group={self.groups[0]}"
        )
        await BUS.publish("status", {"component": "gexbot_negotiate", "ok": True,
                                     "hub": self.hub, "prefix": self.prefix,
                                     "groups": self.groups})

    # ---------- connect + run -----------------------------------------------
    async def run(self) -> None:
        if not self.hub_url:
            await self.negotiate()
        self._loop = asyncio.get_running_loop()
        self._connected_evt.clear()
        self._disconnected_evt.clear()

        self._client = WebPubSubClient(self.hub_url)
        self._client.subscribe(CallbackType.CONNECTED, self._on_connected)
        self._client.subscribe(CallbackType.DISCONNECTED, self._on_disconnected)
        self._client.subscribe(CallbackType.GROUP_MESSAGE, self._on_group_message)

        log.info(f"gexbot WS opening hub={self.hub} ...")
        self._thread = threading.Thread(target=self._client.open, daemon=True,
                                        name=f"gexbot-{self.hub}")
        self._thread.start()

        # Wait for connect
        ok = await asyncio.get_running_loop().run_in_executor(
            None, self._connected_evt.wait, 30.0
        )
        if not ok:
            raise RuntimeError("gexbot WS connect timeout")
        await BUS.publish("status", {"component": "gexbot_ws", "ok": True,
                                     "hub": self.hub})

        # Wait for disconnect (supervisor will reconnect)
        await asyncio.get_running_loop().run_in_executor(
            None, self._disconnected_evt.wait
        )
        await BUS.publish("status", {"component": "gexbot_ws", "ok": False,
                                     "hub": self.hub})
        raise RuntimeError("gexbot WS disconnected")

    async def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                pass
        self._disconnected_evt.set()

    # ---------- callbacks (Azure SDK thread) --------------------------------
    def _on_connected(self, evt: OnConnectedArgs) -> None:
        log.info(f"gexbot WS connected id={evt.connection_id}")
        for grp in self.groups:
            try:
                self._client.join_group(grp)   # type: ignore[union-attr]
                log.info(f"gexbot joined group: {grp}")
            except Exception as e:  # noqa: BLE001
                log.error(f"gexbot join_group {grp} failed: {e!r}")
        self._connected_evt.set()

    def _on_disconnected(self, evt: OnDisconnectedArgs) -> None:
        log.warning(f"gexbot WS disconnected: {evt.message}")
        self._disconnected_evt.set()

    def _on_group_message(self, evt: OnGroupDataMessageArgs) -> None:
        try:
            # data can be bytes or str. Azure WebPubSub delivers binary messages
            # as bytes directly.
            raw = evt.data if isinstance(evt.data, (bytes, bytearray)) else evt.data.encode()
        except Exception as e:  # noqa: BLE001
            log.warning(f"gexbot data coerce failed: {e!r}")
            return

        # Outer envelope: google.protobuf.Any
        try:
            any_msg = any_pb2.Any()
            any_msg.ParseFromString(bytes(raw))
        except Exception as e:  # noqa: BLE001
            log.warning(f"gexbot Any.ParseFromString failed: {e!r}  head={bytes(raw)[:24].hex()}")
            return

        inner = any_msg.value
        type_url = any_msg.type_url

        # Inner is Zstandard-compressed protobuf. Try zstd-decompress; if that
        # fails treat it as raw protobuf directly.
        try:
            decomp = self._dctx.decompress(inner)
        except zstd.ZstdError:
            decomp = inner

        # If this is the orderflow type, parse with our best-guess schema
        named: dict[str, Any] = {}
        raw_fields: dict[int, Any] = {}
        if "orderflow" in type_url.lower() or self.hub == "orderflow":
            try:
                named, raw_fields = _parse_flat_proto(decomp, ORDERFLOW_FIELD_MAP)
            except Exception as e:  # noqa: BLE001
                log.warning(f"flat-proto parse failed: {e!r}")

        # Compact log line
        if named:
            preview = (f"spot={named.get('spot', '?')} "
                       f"gexoflow={named.get('gexoflow', '?')} "
                       f"dexoflow={named.get('dexoflow', '?')} "
                       f"z_mlgamma={named.get('z_mlgamma', '?')}")
            log.info(f"gexbot orderflow {preview}")
        else:
            log.info(f"gexbot msg type_url={type_url} len={len(decomp)} head={decomp[:24].hex()}")

        BUS.publish_threadsafe("flow", {
            "src": "gexbot",
            "group": evt.group,
            "type_url": type_url,
            "payload": named or None,
            "raw_fields": raw_fields or None,
            "bytes_len": len(decomp),
        })
