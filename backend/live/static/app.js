/* =============================================================================
 * Cheese Live dashboard client.
 *
 * Data model:
 *   - Server fan-outs bus events on /ws. Each event: { t, ch, data }.
 *   - We keep a rolling ring of recent prices + recent flow readings + recent
 *     pnl samples, re-render on each change.
 *
 * Visuals:
 *   - Hero tiles with live values and inline SVG sparklines (drawn here).
 *   - Plotly chart for ES price (gradient area fill + line).
 *   - Connection cards with pulse dots.
 *   - Log stream with filters + newline animation.
 *   - Signal card with side pill + KV grid.
 * ============================================================================= */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);

  // ---------- state -----------------------------------------------------------
  const RING_MAX   = 1800;  // 30 min @ 1s
  const FLOW_RING  = 600;   // 10 min of flow samples
  const LOG_MAX    = 6000;
  const PNL_RING   = 400;

  const state = {
    armed: false,
    status: {},              // component -> last event dict
    prices: [],              // {t: iso, y: num}
    priceOpen: null,         // anchor for % change (first price of session)
    flow: [],                // {t, gexz, dexz}
    pnl: [],                 // {t, cumulative}
    pnlDay: 0,
    pnlTrades: 0,
    position: { side: 0 },   // {side, entry_px, stop_px, target_px}
    lastSignal: null,
    orders: [],
    logs: [],
    sources: new Set(),
    filterText: "",
    filterLevel: "",
    filterSource: "",
  };

  const LEVELS = { DEBUG: 10, INFO: 20, WARNING: 30, ERROR: 40, CRITICAL: 50 };

  // ---------- utils -----------------------------------------------------------
  const nowISO = () => new Date().toISOString();
  const fmt2   = (n) => (n == null || isNaN(n)) ? "—" : (+n).toFixed(2);
  const fmtUSD = (n) => {
    if (n == null || isNaN(n)) return "—";
    const sign = n < 0 ? "-" : n > 0 ? "+" : "";
    const abs  = Math.abs(n);
    return sign + "$" + abs.toLocaleString("en-US", { maximumFractionDigits: 0 });
  };
  const fmtTime = (iso) => {
    try { return new Date(iso).toLocaleTimeString("en-US", { hour12: false }); }
    catch { return iso; }
  };
  const escapeHtml = (s) => (s ?? "").toString()
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  // ---------- Plotly chart ----------------------------------------------------
  let chartReady = false;
  const initChart = () => {
    const layout = {
      margin: { t: 8, l: 42, r: 10, b: 22 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor:  "rgba(0,0,0,0)",
      xaxis: {
        gridcolor: "rgba(255,255,255,0.04)",
        linecolor: "rgba(255,255,255,0.04)",
        zerolinecolor: "rgba(255,255,255,0.04)",
        color: "#5b6577", tickfont: { family: "JetBrains Mono", size: 10 },
        type: "date", fixedrange: true,
      },
      yaxis: {
        gridcolor: "rgba(255,255,255,0.04)",
        linecolor: "rgba(255,255,255,0.04)",
        zerolinecolor: "rgba(255,255,255,0.04)",
        color: "#5b6577", tickfont: { family: "JetBrains Mono", size: 10 },
        fixedrange: true,
      },
      showlegend: false,
      font: { color: "#9aa3b2", family: "Inter" },
      hovermode: "x unified",
      hoverlabel: {
        bgcolor: "#0b0e17", bordercolor: "#1f2838",
        font: { family: "JetBrains Mono", color: "#e7eaf0" },
      },
    };
    // Single line trace, no fill. Earlier attempts with fill:"tozeroy" and
    // fill:"tonexty"+baseline both produced a visible diagonal stroke on
    // reload (Plotly strokes the fill polygon edge when the rapid history
    // replay outpaces the y-axis relayout). Keeping it clean is better.
    const price = {
      x: [], y: [], mode: "lines", showlegend: false,
      line: { color: "#60a5fa", width: 2, shape: "linear" },
      connectgaps: false,
      hovertemplate: "%{y:.2f}<extra></extra>",
    };
    Plotly.newPlot("price-chart", [price], layout,
      { displayModeBar: false, responsive: true, staticPlot: false });
    chartReady = true;
  };

  // Throttle chart updates so the history replay (which can fire hundreds of
  // price events in one tick) doesn't cause a restyle storm.
  let chartPending = false;
  const updateChart = () => {
    if (!chartReady || !state.prices.length || chartPending) return;
    chartPending = true;
    requestAnimationFrame(() => {
      chartPending = false;
      if (!state.prices.length) return;
      const xs = state.prices.map(d => d.t);
      const ys = state.prices.map(d => d.y);
      const finite = ys.filter(v => v != null && isFinite(v));
      if (!finite.length) return;
      const mn = Math.min(...finite);
      const mx = Math.max(...finite);
      const pad = Math.max((mx - mn) * 0.25, 0.5);
      Plotly.restyle("price-chart", { x: [xs], y: [ys] }, [0]);
      Plotly.relayout("price-chart", { "yaxis.range": [mn - pad, mx + pad] });
      $("chart-range").textContent =
        `${fmtTime(xs[0])} – ${fmtTime(xs[xs.length - 1])}`;
    });
  };

  // ---------- Sparkline (SVG path generator) ---------------------------------
  const sparkline = (id, values, { color = "#60a5fa", fill = null } = {}) => {
    const el = $(id);
    if (!el) return;
    const n = values.length;
    if (n < 2) { el.innerHTML = ""; return; }
    const W = 120, H = 32;
    const mn = Math.min(...values), mx = Math.max(...values);
    const rng = mx - mn || 1;
    const pts = values.map((v, i) => {
      const x = (i / (n - 1)) * W;
      const y = H - ((v - mn) / rng) * (H - 4) - 2;
      return [x, y];
    });
    const linePath = "M " + pts.map(p => p.map(n => n.toFixed(2)).join(" ")).join(" L ");
    const areaPath = fill
      ? linePath + ` L ${W} ${H} L 0 ${H} Z`
      : null;
    el.innerHTML = (fill ? `<path d="${areaPath}" fill="${fill}"/>` : "") +
      `<path d="${linePath}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>`;
  };

  // ---------- WebSocket -------------------------------------------------------
  let ws;
  const connect = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => {
      addLog({ t: nowISO(), level: "INFO", source: "client", msg: "ws connected" });
      renderLog();
    };
    ws.onclose = () => {
      addLog({ t: nowISO(), level: "WARNING", source: "client", msg: "ws disconnected; retrying in 2s" });
      renderLog();
      setTimeout(connect, 2000);
    };
    ws.onmessage = (e) => { try { dispatch(JSON.parse(e.data)); } catch {} };
  };

  const dispatch = (ev) => {
    switch (ev.ch) {
      case "log":    addLog({ t: ev.t, ...ev.data }); renderLog(); break;
      case "status": state.status[ev.data.component] = { ...ev.data, last_ts: ev.t }; renderStatus(); break;
      case "price":  onPrice(ev);   break;
      case "signal": onSignal(ev);  break;
      case "order":  onOrder(ev);   break;
      case "flow":   onFlow(ev);    break;
    }
  };

  // ---------- Price -----------------------------------------------------------
  const onPrice = (ev) => {
    const p = ev.data || {};
    if (p.src !== "databento" && p.src !== "tradovate_md") return;
    const px = +(p.close ?? p.price);
    if (!isFinite(px)) return;

    if (state.priceOpen == null) state.priceOpen = px;
    const delta = px - state.priceOpen;
    const pct   = (delta / state.priceOpen) * 100;
    const up    = delta >= 0;

    $("price").textContent = px.toFixed(2);
    $("price-src").textContent = p.src.replace("_", " ");
    $("price-delta").textContent = (up ? "+" : "") + delta.toFixed(2);
    $("price-pct").textContent   = `(${(up ? "+" : "")}${pct.toFixed(2)}%)`;

    const change = document.querySelector(".tile--price .tile-change");
    change.classList.toggle("up", up);
    change.classList.toggle("down", !up);
    $("price-arrow").innerHTML = `<use href="#${up ? "i-arrow-up" : "i-arrow-down"}"/>`;

    // Insert a null "gap marker" if the stream dropped for >10s, so the
    // line breaks instead of bridging a time gap with a straight segment.
    const last = state.prices.length ? state.prices[state.prices.length - 1] : null;
    if (last && last.y != null) {
      const gapMs = new Date(ev.t) - new Date(last.t);
      if (gapMs > 10_000) {
        const gapT = new Date(new Date(last.t).getTime() + 1000).toISOString();
        state.prices.push({ t: gapT, y: null });
      }
    }
    state.prices.push({ t: ev.t, y: px });
    if (state.prices.length > RING_MAX) state.prices.shift();
    updateChart();
    sparkline("spark-price", state.prices.slice(-80).map(d => d.y),
      { color: up ? "#34d399" : "#f87171", fill: up ? "url(#gradGain)" : "url(#gradLoss)" });
  };

  // ---------- Flow ------------------------------------------------------------
  const onFlow = (ev) => {
    const d = ev.data;
    const pay = d.payload;
    if (!pay) return;
    const gex = +pay.gexoflow, dex = +pay.dexoflow;
    if (!isFinite(gex) && !isFinite(dex)) return;
    state.flow.push({ t: ev.t, gex: isFinite(gex) ? gex : null, dex: isFinite(dex) ? dex : null });
    if (state.flow.length > FLOW_RING) state.flow.shift();
  };

  // ---------- Signal / position ----------------------------------------------
  const onSignal = (ev) => {
    const d = ev.data || {};

    // Flow z-scores + regime + ATR
    if (d.gexoflow_z != null && isFinite(d.gexoflow_z)) {
      const z = +d.gexoflow_z;
      $("flow-val").textContent = z.toFixed(2);
      $("flow-sigma").textContent = `σ ${Math.abs(z).toFixed(2)}`;
      const el = $("flow-val");
      el.style.color = z > 1 ? "var(--green)" : z < -1 ? "var(--red)" : "var(--fg-0)";
    }
    if (d.dexoflow_z != null && isFinite(d.dexoflow_z)) {
      // use dex as secondary spark source
      state.pnl; // no-op placeholder
    }
    if (d.regime) {
      const r = d.regime;
      $("regime-detail").textContent = r;
      const pill = $("regime-pill");
      pill.textContent = r;
      pill.className = "tile-tag " +
        (r.includes("pos") ? "pill-pos" :
         r.includes("neg") ? "pill-neg" : "pill-flat");
    }
    if (d.atr != null && isFinite(d.atr)) $("atr-val").textContent = (+d.atr).toFixed(2);

    // Position
    if (d.position_side !== undefined) {
      state.position.side = d.position_side;
      const side = d.position_side === 1 ? "LONG" : d.position_side === -1 ? "SHORT" : "FLAT";
      const pill = $("pos-side-pill");
      pill.textContent = side;
      pill.className = "tile-tag " +
        (side === "LONG" ? "pill-long" : side === "SHORT" ? "pill-short" : "pill-flat");
    }

    // Last signal event (side set)
    if (d.side !== undefined) {
      state.lastSignal = { ...d, t: ev.t };
      renderSignalBox();
      if (d.entry_px != null) {
        $("pos-entry").textContent = "@ " + (+d.entry_px).toFixed(2);
        $("pos-bracket").textContent =
          `stop ${(+d.stop_px).toFixed(2)} · tgt ${(+d.target_px).toFixed(2)}`;
      } else if (state.position.side === 0) {
        $("pos-entry").textContent = "—";
        $("pos-bracket").textContent = "stop — · tgt —";
      }
    }

    // Update flow sparkline from the tile flow buffer
    const spark = state.flow.slice(-80).map(r => r.gex).filter(v => v != null);
    if (spark.length >= 2) {
      const last = spark[spark.length - 1];
      const up = last >= 0;
      sparkline("spark-flow", spark,
        { color: up ? "#a78bfa" : "#f472b6", fill: null });
    }
  };

  const renderSignalBox = () => {
    const s = state.lastSignal;
    const box = $("signal-box");
    if (!s) { box.innerHTML = `<div class="signal-empty">awaiting edge…</div>`; return; }
    const sideCls = s.side === 1 ? "long" : s.side === -1 ? "short" : "suppressed";
    const sideLabel = s.side === 1 ? "LONG" : s.side === -1 ? "SHORT" : "NONE";
    const arrowIcon = s.side === 1 ? "i-arrow-up" : s.side === -1 ? "i-arrow-down" : "i-target";
    const armed = s.armed
      ? `<span class="signal-side ${sideCls}"><svg class="ic-sm"><use href="#${arrowIcon}"/></svg> ${sideLabel}</span>`
      : `<span class="signal-side suppressed">${sideLabel} · DISARMED</span>`;

    const kv = [];
    if (s.entry_px  != null) kv.push(["entry",  (+s.entry_px ).toFixed(2)]);
    if (s.stop_px   != null) kv.push(["stop",   (+s.stop_px  ).toFixed(2)]);
    if (s.target_px != null) kv.push(["target", (+s.target_px).toFixed(2)]);
    if (s.atr       != null) kv.push(["atr",    (+s.atr      ).toFixed(2)]);
    if (s.gexoflow_z!= null) kv.push(["gex z",  (+s.gexoflow_z).toFixed(2)]);

    box.innerHTML = `
      <div class="signal-head">
        ${armed}
        <span class="time">${fmtTime(s.t || s.ts)}</span>
      </div>
      <div class="signal-kv">
        ${kv.map(([k, v]) => `<span class="k">${k}</span><span class="v">${v}</span>`).join("")}
      </div>`;
  };

  // ---------- Orders ----------------------------------------------------------
  const onOrder = (ev) => {
    const d = ev.data || {};
    const ev_name = d.event ?? "?";
    const desc = shortOrder(d);
    const cls = /fill|filled|placed|ok|dry_submit/i.test(ev_name) ? "ok"
              : /reject|error|fail/i.test(ev_name) ? "err" : "neu";

    // PnL extraction (best-effort): some venues include realized P&L on fill
    const x = d.msg?.d;
    if (x && typeof x.realizedPnL === "number") {
      state.pnlDay += x.realizedPnL;
      state.pnlTrades += 1;
      state.pnl.push({ t: ev.t, y: state.pnlDay });
      if (state.pnl.length > PNL_RING) state.pnl.shift();
      renderPnL();
    }

    state.orders.unshift({ t: ev.t, event: ev_name, desc, cls });
    if (state.orders.length > 120) state.orders.pop();
    renderOrders();
  };

  const shortOrder = (d) => {
    if (d.body) return `${d.body.action} ${d.body.orderQty} ${d.body.symbol} ${d.body.orderType}`;
    const x = d.msg?.d;
    if (x) {
      return [x.action, x.orderQty, x.symbol, x.orderType, x.orderStatus]
        .filter(Boolean).join(" ");
    }
    if (d.reason) return d.reason;
    return JSON.stringify(d).slice(0, 180);
  };

  const renderOrders = () => {
    const wrap = $("order-list");
    wrap.innerHTML = state.orders.map(o => `
      <div class="order-item">
        <span class="ot">${fmtTime(o.t)}</span>
        <span class="oev ${o.cls}">${escapeHtml(o.event)}</span>
        <span class="od">${escapeHtml(o.desc)}</span>
      </div>
    `).join("");
    $("order-count").textContent = state.orders.length;
  };

  const renderPnL = () => {
    $("pnl").textContent = fmtUSD(state.pnlDay);
    $("pnl-trades").textContent = `${state.pnlTrades} trade${state.pnlTrades === 1 ? "" : "s"}`;
    const pnlTile = $("pnl").parentElement.parentElement;
    pnlTile.querySelector(".tile-change")?.classList.toggle("up",   state.pnlDay > 0);
    pnlTile.querySelector(".tile-change")?.classList.toggle("down", state.pnlDay < 0);
    sparkline("spark-pnl", state.pnl.map(d => d.y),
      { color: state.pnlDay >= 0 ? "#34d399" : "#f87171",
        fill: state.pnlDay >= 0 ? "url(#gradGain)" : "url(#gradLoss)" });
  };

  // ---------- Status / connections -------------------------------------------
  const renderStatus = () => {
    const el = $("status-list");
    const names = Object.keys(state.status).sort();
    if (!names.length) {
      el.innerHTML = `<li class="conn-item idle"><span class="dot"></span><span class="name">no components yet</span></li>`;
      $("conn-count").textContent = "0 / 0";
      $("conn-summary").textContent = "—";
      return;
    }
    let ok = 0, total = 0;
    el.innerHTML = names.map(n => {
      const s = state.status[n];
      const cls = s.ok === true ? "ok" : s.ok === false ? "bad" : "idle";
      if (s.ok === true) ok += 1;
      total += 1;
      const meta = s.last_ts ? fmtTime(s.last_ts) : "";
      return `<li class="conn-item ${cls}">
        <span class="dot"></span>
        <span class="name">${escapeHtml(n)}</span>
        <span class="meta">${meta}</span>
      </li>`;
    }).join("");
    $("conn-count").textContent = `${ok} / ${total}`;
    $("conn-summary").textContent = `${ok}/${total} online`;
  };

  // ---------- Log -------------------------------------------------------------
  const addLog = (r) => {
    r._new = true;
    state.logs.push(r);
    if (r.source) state.sources.add(r.source);
    if (state.logs.length > LOG_MAX) state.logs.splice(0, 1000);
  };

  const matchFilter = (r) => {
    if (state.filterLevel && LEVELS[r.level] < LEVELS[state.filterLevel]) return false;
    if (state.filterSource && r.source !== state.filterSource) return false;
    const q = state.filterText.trim();
    if (!q) return true;
    if (q.startsWith("!")) return !(r.msg ?? "").toLowerCase().includes(q.slice(1).toLowerCase());
    try {
      const re = new RegExp(q, "i");
      return re.test(r.msg ?? "") || re.test(r.source ?? "");
    } catch {
      return (r.msg ?? "").toLowerCase().includes(q.toLowerCase());
    }
  };

  const renderLog = () => {
    const el = $("log");
    const auto = $("log-autoscroll").checked;
    const filtered = state.logs.filter(matchFilter);
    $("log-count").textContent = `${filtered.length} / ${state.logs.length}`;
    const slice = filtered.slice(-500);
    el.innerHTML = slice.map(r => {
      const t   = fmtTime(r.t);
      const src = r.source ?? "";
      const cls = `log-line log-${r.level || "INFO"}${r._new ? " new" : ""}`;
      r._new = false;
      return `<div class="${cls}"><span class="lt">${t}</span><span class="ls">${escapeHtml(src)}</span><span class="lm">${escapeHtml(r.msg ?? "")}</span></div>`;
    }).join("");
    if (auto) el.scrollTop = el.scrollHeight;
    // Refresh source dropdown if new sources appeared
    const sel = $("log-source");
    if (state.sources.size !== (sel.options.length - 1)) {
      const cur = sel.value;
      const opts = [""].concat([...state.sources].sort());
      sel.innerHTML = opts.map(o => `<option value="${o}">${o || "ALL SOURCES"}</option>`).join("");
      sel.value = cur;
    }
  };

  // ---------- Arm button ------------------------------------------------------
  const updateArmUI = () => {
    const btn = $("arm-btn");
    const lbl = $("arm-label");
    const icon = $("arm-icon");
    if (state.armed) {
      btn.classList.add("armed-on");
      btn.setAttribute("aria-pressed", "true");
      lbl.textContent = "ARMED";
      icon.setAttribute("href", "#i-play");
    } else {
      btn.classList.remove("armed-on");
      btn.setAttribute("aria-pressed", "false");
      lbl.textContent = "DISARMED";
      icon.setAttribute("href", "#i-pause");
    }
  };

  // ---------- Listeners -------------------------------------------------------
  $("arm-btn").addEventListener("click", async () => {
    const want = !state.armed;
    if (want && !confirm("ARM real order submission?\nDry-run will be disabled and trades will be LIVE.")) return;
    try {
      const r = await fetch(`/api/arm?flag=${want}`, { method: "POST" });
      if (!r.ok) throw new Error("http " + r.status);
      const j = await r.json();
      state.armed = !!j.armed;
      updateArmUI();
    } catch (e) { alert("arm failed: " + e.message); }
  });

  $("log-filter").addEventListener("input",  (e) => { state.filterText   = e.target.value; renderLog(); });
  $("log-level" ).addEventListener("change", (e) => { state.filterLevel  = e.target.value; renderLog(); });
  $("log-source").addEventListener("change", (e) => { state.filterSource = e.target.value; renderLog(); });

  // ---------- Clock (ET) ------------------------------------------------------
  const etClock = () => {
    try {
      $("clock").textContent = new Date().toLocaleTimeString("en-US", {
        hour12: false, timeZone: "America/New_York",
      });
    } catch {
      $("clock").textContent = new Date().toLocaleTimeString("en-US", { hour12: false });
    }
  };
  etClock();
  setInterval(etClock, 1000);

  // ---------- Initial hydrate -------------------------------------------------
  fetch("/api/status").then(r => r.json()).then(j => {
    state.armed = !!j.armed;
    updateArmUI();
    if (j.components) { state.status = j.components; renderStatus(); }
  }).catch(() => {});

  initChart();
  renderPnL();
  renderSignalBox();
  connect();
})();
