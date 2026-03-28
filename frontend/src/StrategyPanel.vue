<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { Socket } from 'socket.io-client'

const props = defineProps<{
  socket: Socket
}>()

type MicrostateSnapshot = {
  tps: number
  average_tps: number
  aggression_efficiency: number
}

type SetupDeltaSnapshot = {
  bar_delta: number
  avg_delta: number
}

type StrategySnapshot = {
  status: string
  side: number
  position_size: number
  pnl: number
  entry_price: number
  commission: number
  trade_count: number
  cooldown_ticks: number
  balance: number
  ruin_level: number
  account_blown: boolean
}

type StatusEvent = {
  time: number
  status: string
  side: number
}

const micro = ref<MicrostateSnapshot>({
  tps: 0,
  average_tps: 0,
  aggression_efficiency: 0,
})

const setupDelta = ref<SetupDeltaSnapshot>({
  bar_delta: 0,
  avg_delta: 0,
})

const strategy = ref<StrategySnapshot>({
  status: 'IDLE',
  side: 0,
  position_size: 0,
  pnl: 0,
  entry_price: 0,
  commission: 0,
  trade_count: 0,
  cooldown_ticks: 0,
  balance: 50000,
  ruin_level: 48000,
  account_blown: false,
})

const lastMark = ref<number | null>(null)
const statusEvents = ref<StatusEvent[]>([])

const sideLabel = computed(() => {
  const s = strategy.value.side
  if (s === 1) return 'LONG'
  if (s === -1) return 'SHORT'
  return '—'
})

const unrealizedPnl = computed(() => {
  const st = strategy.value.status
  if (
    (st !== 'IN_TRADE' && st !== 'EXIT_ORDER_SUBMITTED') ||
    strategy.value.side === 0 ||
    lastMark.value == null
  )
    return 0
  const { position_size: q, side, entry_price: e } = strategy.value
  return q * side * 20 * (lastMark.value - e)
})

const statusClass = computed(() => {
  const s = strategy.value.status
  if (s === 'IN_TRADE') return 'pill--trade'
  if (s === 'ORDER_SUBMITTED' || s === 'EXIT_ORDER_SUBMITTED') return 'pill--order'
  if (s === 'COOLDOWN') return 'pill--cooldown'
  return 'pill--idle'
})

function fmtNum(n: number, d = 2) {
  if (!Number.isFinite(n)) return '—'
  return n.toFixed(d)
}

function fmtTs(t: number) {
  return new Date(t * 1000).toISOString().slice(11, 23)
}

function onTickPayload(payload: {
  tick: { time: number; value: number }
  microstate: MicrostateSnapshot
  strategy: StrategySnapshot
}) {
  lastMark.value = payload.tick.value
  micro.value = payload.microstate
  strategy.value = payload.strategy
}

function onStrategyStatus(payload: StrategySnapshot & { time: number }) {
  const { time, ...rest } = payload
  strategy.value = rest
  statusEvents.value.push({ time, status: rest.status, side: rest.side })
  if (statusEvents.value.length > 32) statusEvents.value.shift()
}

function on10Tick(payload: {
  time: number
  open: number
  high: number
  low: number
  close: number
  bar_delta?: number
  avg_delta?: number
}) {
  setupDelta.value = {
    bar_delta: payload.bar_delta ?? 0,
    avg_delta: payload.avg_delta ?? 0,
  }
}

onMounted(() => {
  props.socket.on('tick', onTickPayload)
  props.socket.on('strategy_status', onStrategyStatus)
  props.socket.on('10-tick', on10Tick)
})

onUnmounted(() => {
  props.socket.off('tick', onTickPayload)
  props.socket.off('strategy_status', onStrategyStatus)
  props.socket.off('10-tick', on10Tick)
})
</script>

<template>
  <section class="strategy-dashboard">
    <header class="head">
      <div class="head-left">
        <span class="title">Strategy</span>
        <span class="pill" :class="statusClass">{{ strategy.status }}</span>
        <span v-if="strategy.account_blown" class="pill pill--blown">ACCOUNT BLOWN</span>
      </div>
      <div class="head-right">
        <span class="side-tag" :data-side="strategy.side">{{ sideLabel }}</span>
      </div>
    </header>

    <div class="grid">
      <article class="card card--micro">
        <h3 class="card-h">Microstate <span class="live">live</span></h3>
        <dl class="kv">
          <div class="row">
            <dt>TPS</dt>
            <dd>{{ fmtNum(micro.tps, 3) }}</dd>
          </div>
          <div class="row">
            <dt>Avg TPS (rolling)</dt>
            <dd>{{ fmtNum(micro.average_tps, 3) }}</dd>
          </div>
          <div class="row">
            <dt>Aggression efficiency</dt>
            <dd>{{ fmtNum(micro.aggression_efficiency, 6) }}</dd>
          </div>
        </dl>
      </article>

      <article class="card card--setup">
        <h3 class="card-h">Setup <span class="setup-hint">10-tick bars</span></h3>
        <dl class="kv">
          <div class="row">
            <dt>Bar Δ (close − open)</dt>
            <dd :class="setupDelta.bar_delta >= 0 ? 'pos' : 'neg'">{{ fmtNum(setupDelta.bar_delta, 4) }}</dd>
          </div>
          <div class="row">
            <dt>Avg Δ (rolling)</dt>
            <dd :class="setupDelta.avg_delta >= 0 ? 'pos' : 'neg'">{{ fmtNum(setupDelta.avg_delta, 4) }}</dd>
          </div>
        </dl>
      </article>

      <article class="card card--account">
        <h3 class="card-h">Account &amp; risk</h3>
        <dl class="kv">
          <div class="row">
            <dt>Balance</dt>
            <dd>{{ fmtNum(strategy.balance, 2) }}</dd>
          </div>
          <div class="row">
            <dt>Ruin level</dt>
            <dd>{{ fmtNum(strategy.ruin_level, 2) }}</dd>
          </div>
          <div class="row">
            <dt>Realized P&amp;L</dt>
            <dd :class="strategy.pnl >= 0 ? 'pos' : 'neg'">{{ fmtNum(strategy.pnl, 2) }}</dd>
          </div>
          <div class="row">
            <dt>Unrealized P&amp;L</dt>
            <dd :class="unrealizedPnl >= 0 ? 'pos' : 'neg'">{{ fmtNum(unrealizedPnl, 2) }}</dd>
          </div>
          <div class="row">
            <dt>Commission (cumulative)</dt>
            <dd>{{ fmtNum(strategy.commission, 2) }}</dd>
          </div>
        </dl>
      </article>

      <article class="card card--trade">
        <h3 class="card-h">Position</h3>
        <dl class="kv">
          <div class="row">
            <dt>Size</dt>
            <dd>{{ strategy.position_size }}</dd>
          </div>
          <div class="row">
            <dt>Entry</dt>
            <dd>{{ strategy.entry_price > 0 ? fmtNum(strategy.entry_price, 2) : '—' }}</dd>
          </div>
          <div class="row">
            <dt>Mark</dt>
            <dd>{{ lastMark != null ? fmtNum(lastMark, 2) : '—' }}</dd>
          </div>
          <div class="row">
            <dt>Trades (count)</dt>
            <dd>{{ strategy.trade_count }}</dd>
          </div>
          <div class="row">
            <dt>Cooldown ticks</dt>
            <dd>
              {{ strategy.status === 'COOLDOWN' ? strategy.cooldown_ticks : '—' }}
            </dd>
          </div>
        </dl>
      </article>
    </div>

    <article class="events">
      <h3 class="events-h">Trade status</h3>
      <p v-if="statusEvents.length === 0" class="events-empty">Status changes appear here (e.g. IDLE → ORDER_SUBMITTED → IN_TRADE).</p>
      <ul v-else class="events-list">
        <li v-for="(e, i) in [...statusEvents].reverse()" :key="i" class="events-item">
          <span class="events-ts">{{ fmtTs(e.time) }}</span>
          <span class="events-st">{{ e.status }}</span>
          <span class="events-side" :data-side="e.side">{{
            e.side === 1 ? 'LONG' : e.side === -1 ? 'SHORT' : '—'
          }}</span>
        </li>
      </ul>
    </article>
  </section>
</template>

<style scoped>
.strategy-dashboard {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  background: linear-gradient(180deg, #0f1826 0%, #101928 100%);
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(15, 23, 42, 0.35);
  flex-shrink: 0;
}

.head-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}

.title {
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #94a3b8;
  font-weight: 700;
}

.pill {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 3px 8px;
  border-radius: 6px;
  border: 1px solid #334155;
  color: #cbd5e1;
}

.pill--idle {
  border-color: #475569;
  color: #94a3b8;
}

.pill--order {
  border-color: #ca8a04;
  color: #fde047;
  background: rgba(202, 138, 4, 0.12);
}

.pill--trade {
  border-color: #2563eb;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.15);
}

.pill--cooldown {
  border-color: #7c3aed;
  color: #c4b5fd;
  background: rgba(124, 58, 237, 0.12);
}

.pill--blown {
  border-color: #b91c1c;
  color: #fecaca;
  background: rgba(185, 28, 28, 0.2);
}

.side-tag {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.06em;
}

.side-tag[data-side='1'] {
  color: #4ade80;
}

.side-tag[data-side='-1'] {
  color: #f87171;
}

.side-tag[data-side='0'] {
  color: #64748b;
}

.grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  max-height: 52%;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #3d5169 #0d1520;
}

.setup-hint {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #64748b;
}

@media (min-width: 520px) {
  .grid {
    grid-template-columns: 1fr 1fr;
  }

  .card--micro {
    grid-column: 1 / -1;
  }

  .card--setup {
    grid-column: 1 / -1;
  }
}

.card {
  background: rgba(26, 35, 50, 0.92);
  border: 1px solid rgba(71, 85, 105, 0.55);
  border-radius: 8px;
  padding: 8px 10px;
}

.card-h {
  font-size: 11px;
  font-weight: 700;
  color: #e2e8f0;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.live {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #22c55e;
}

.live::before {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #22c55e;
  margin-right: 4px;
  vertical-align: middle;
  box-shadow: 0 0 6px #22c55e;
  animation: pulse 1.8s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}

.kv {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
  font-size: 12px;
}

dt {
  margin: 0;
  color: #94a3b8;
}

dd {
  margin: 0;
  color: #e2e8f0;
  font-variant-numeric: tabular-nums;
}

.pos {
  color: #4ade80;
}

.neg {
  color: #f87171;
}

.events {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 8px 10px 10px;
}

.events-h {
  font-size: 11px;
  font-weight: 700;
  color: #e2e8f0;
  margin-bottom: 6px;
  flex-shrink: 0;
}

.events-empty {
  font-size: 12px;
  color: #64748b;
}

.events-list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 5px;
  scrollbar-width: thin;
  scrollbar-color: #3d5169 #0d1520;
}

.events-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 11px;
  border: 1px solid rgba(71, 85, 105, 0.55);
  border-radius: 6px;
  background: #1a2332;
  padding: 5px 8px;
}

.events-ts {
  color: #64748b;
  font-variant-numeric: tabular-nums;
}

.events-st {
  color: #cbd5e1;
  font-weight: 600;
}

.events-side[data-side='1'] {
  color: #4ade80;
}

.events-side[data-side='-1'] {
  color: #f87171;
}

.events-side[data-side='0'] {
  color: #64748b;
}
</style>
