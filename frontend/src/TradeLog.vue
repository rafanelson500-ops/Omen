<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import type { Socket } from 'socket.io-client'

const props = defineProps<{
  socket: Socket
}>()

type LogRow =
  | {
      kind: 'pending'
      ts: number
      side: string
      signalPrice: number
      wallPrice: number
    }
  | {
      kind: 'open'
      ts: number
      id: string
      side: string
      entry: number
      takeProfit: number
      stopLoss: number
      wallPrice: number
    }
  | {
      kind: 'closed'
      ts: number
      id: string
      side: string
      entry: number
      exit: number
      reason: string
      pnlTicks: number
    }

const rows = ref<LogRow[]>([])
const scrollRef = ref<HTMLElement | null>(null)
/** Cumulative P&amp;L in ticks (sum of closed trades) */
const runningPnlTicks = ref(0)

function fmtTs(ts: number) {
  return new Date(ts * 1000).toISOString().slice(11, 23)
}

function fmtPx(p: number) {
  return p.toFixed(2)
}

function onPending(p: {
  side: string
  signal_price: number
  wall_price: number
  ts: number
}) {
  rows.value.push({
    kind: 'pending',
    ts: p.ts,
    side: p.side,
    signalPrice: p.signal_price,
    wallPrice: p.wall_price,
  })
  queueScroll()
}

function onOpened(p: {
  id: string
  side: string
  entry: number
  take_profit: number
  stop_loss: number
  wall_price: number
  ts: number
}) {
  rows.value.push({
    kind: 'open',
    ts: p.ts,
    id: p.id,
    side: p.side,
    entry: p.entry,
    takeProfit: p.take_profit,
    stopLoss: p.stop_loss,
    wallPrice: p.wall_price,
  })
  queueScroll()
}

function onClosed(p: {
  id: string
  side: string
  entry: number
  exit: number
  reason: string
  pnl_ticks: number
  ts: number
}) {
  rows.value.push({
    kind: 'closed',
    ts: p.ts,
    id: p.id,
    side: p.side,
    entry: p.entry,
    exit: p.exit,
    reason: p.reason,
    pnlTicks: p.pnl_ticks,
  })
  runningPnlTicks.value += Number(p.pnl_ticks)
  queueScroll()
}

function fmtRunningPnl(v: number) {
  const rounded = Math.round(v * 1000) / 1000
  const s = rounded >= 0 ? `+${rounded}` : `${rounded}`
  return `${s} ticks`
}

let scrollQueued = false
function queueScroll() {
  if (scrollQueued) return
  scrollQueued = true
  requestAnimationFrame(() => {
    scrollQueued = false
    const el = scrollRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

onMounted(() => {
  props.socket.on('trade_pending', onPending)
  props.socket.on('trade_opened', onOpened)
  props.socket.on('trade_closed', onClosed)
})

onUnmounted(() => {
  props.socket.off('trade_pending', onPending)
  props.socket.off('trade_opened', onOpened)
  props.socket.off('trade_closed', onClosed)
})
</script>

<template>
  <div class="trade-log">
    <div class="trade-log-header">
      <span class="trade-log-title">Trade log</span>
      <span
        class="running-pnl"
        :class="{
          'running-pnl--zero': runningPnlTicks === 0,
          'running-pnl--pos': runningPnlTicks > 0,
          'running-pnl--neg': runningPnlTicks < 0,
        }"
        title="Cumulative P&amp;L (closed trades, ticks)"
      >
        Σ P&amp;L {{ fmtRunningPnl(runningPnlTicks) }}
      </span>
    </div>
    <div ref="scrollRef" class="trade-log-body">
      <div v-if="rows.length === 0" class="empty">Waiting for signals…</div>
      <div
        v-for="(r, i) in rows"
        :key="i"
        class="row"
        :class="['row--' + r.kind, r.kind === 'closed' && (r.pnlTicks >= 0 ? 'row--win' : 'row--loss')]"
      >
        <template v-if="r.kind === 'pending'">
          <span class="badge badge--armed">ARMED</span>
          <span class="meta">{{ fmtTs(r.ts) }}</span>
          <span class="side" :class="r.side">{{ r.side.toUpperCase() }}</span>
          <span class="detail"
            >signal {{ fmtPx(r.signalPrice) }} · wall {{ fmtPx(r.wallPrice) }} (1 tick)</span
          >
        </template>
        <template v-else-if="r.kind === 'open'">
          <span class="badge badge--open">OPEN</span>
          <span class="meta">#{{ r.id }} · {{ fmtTs(r.ts) }}</span>
          <span class="side" :class="r.side">{{ r.side.toUpperCase() }}</span>
          <span class="detail"
            >entry {{ fmtPx(r.entry) }} · TP {{ fmtPx(r.takeProfit) }} · SL {{ fmtPx(r.stopLoss) }}</span
          >
        </template>
        <template v-else>
          <span class="badge" :class="r.reason === 'tp' ? 'badge--tp' : 'badge--sl'">{{
            r.reason.toUpperCase()
          }}</span>
          <span class="meta">#{{ r.id }} · {{ fmtTs(r.ts) }}</span>
          <span class="side" :class="r.side">{{ r.side.toUpperCase() }}</span>
          <span class="detail"
            >exit {{ fmtPx(r.exit) }} · P&amp;L {{ r.pnlTicks >= 0 ? '+' : '' }}{{ r.pnlTicks }} ticks</span
          >
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.trade-log {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  background: #111d2c;
  border-left: 2px solid #2d3f55;
}

.trade-log-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px 6px 12px;
  border-bottom: 2px solid #2d3f55;
}

.trade-log-title {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: #94a3b8;
  text-transform: uppercase;
}

.running-pnl {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.running-pnl--zero {
  color: #94a3b8;
}

.running-pnl--pos {
  color: #4ade80;
  text-shadow: 0 0 12px rgba(34, 197, 94, 0.25);
}

.running-pnl--neg {
  color: #f87171;
  text-shadow: 0 0 12px rgba(248, 113, 113, 0.2);
}

.trade-log-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  font-size: 12px;
  line-height: 1.45;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: #3d5169 #0d1520;
}

.trade-log-body::-webkit-scrollbar {
  width: 9px;
}

.trade-log-body::-webkit-scrollbar-track {
  background: #0d1520;
  border-radius: 6px;
  margin: 4px 0;
}

.trade-log-body::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, #4a6282 0%, #3d5169 100%);
  border-radius: 6px;
  border: 2px solid #0d1520;
  min-height: 40px;
}

.trade-log-body::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, #5a7292 0%, #4d6180 100%);
}

.trade-log-body::-webkit-scrollbar-thumb:active {
  background: #647896;
}

.empty {
  color: #64748b;
  padding: 12px;
  font-size: 12px;
}

.row {
  padding: 8px 10px;
  margin-bottom: 6px;
  border-radius: 6px;
  background: #1a2332;
  border: 1px solid #2d3f55;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px 10px;
}

.row--pending {
  border-left: 3px solid #eab308;
}

.row--open {
  border-left: 3px solid #3b82f6;
}

.row--closed.row--win {
  border-left: 3px solid #22c55e;
}

.row--closed.row--loss {
  border-left: 3px solid #ef4444;
}

.badge {
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.06em;
  padding: 2px 6px;
  border-radius: 4px;
  background: #334155;
  color: #e2e8f0;
}

.badge--armed {
  background: #713f12;
  color: #fef08a;
}

.badge--open {
  background: #1e3a5f;
  color: #93c5fd;
}

.badge--tp {
  background: #14532d;
  color: #86efac;
}

.badge--sl {
  background: #7f1d1d;
  color: #fecaca;
}

.meta {
  font-size: 10px;
  color: #64748b;
  font-variant-numeric: tabular-nums;
}

.side {
  font-weight: 700;
  font-size: 11px;
}

.side.long {
  color: #4ade80;
}

.side.short {
  color: #f87171;
}

.detail {
  flex-basis: 100%;
  color: #cbd5e1;
  font-variant-numeric: tabular-nums;
}
</style>
