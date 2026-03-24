<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { Socket } from 'socket.io-client'

const props = defineProps<{
  socket: Socket
}>()

type StrategyState = {
  state: 'IDLE' | 'SETUP_FOUND' | 'WAITING_TRIGGER' | 'IN_TRADE' | 'EXIT'
  side: 'long' | 'short' | null
  entryGateOpen: boolean
  killFlags: string[]
}

type StrategyRegime = {
  tradable: boolean
  type: 'trend' | 'chop'
  volatility: 'low' | 'medium' | 'high'
  reasons: string[]
  movement_ratio?: number
  direction_consistency?: number
}

type StrategySetup = {
  type: 'trend' | 'absorption' | null
  direction: 'long' | 'short' | null
  quality: number
  reasons: string[]
}

type StrategyMicro = {
  pressure: number
  absorption: number
  volatility: number
}

type DecisionEvent = {
  kind: string
  ts: number
  [key: string]: unknown
}

const states: StrategyState['state'][] = ['IDLE', 'SETUP_FOUND', 'WAITING_TRIGGER', 'IN_TRADE', 'EXIT']

const strategyState = ref<StrategyState>({
  state: 'IDLE',
  side: null,
  entryGateOpen: false,
  killFlags: [],
})
const regime = ref<StrategyRegime>({
  tradable: false,
  type: 'chop',
  volatility: 'low',
  reasons: ['warming_up'],
})
const setup = ref<StrategySetup>({
  type: null,
  direction: null,
  quality: 0,
  reasons: ['warming_up'],
})
const micro = ref<StrategyMicro>({
  pressure: 0,
  absorption: 0,
  volatility: 0,
})
const decisions = ref<DecisionEvent[]>([])

const setupQualityPct = computed(() => Math.max(0, Math.min(100, Math.round(setup.value.quality * 100))))
const pressurePct = computed(() => Math.max(0, Math.min(100, Math.round(((micro.value.pressure + 1) / 2) * 100))))
const absorptionPct = computed(() => Math.max(0, Math.min(100, Math.round(micro.value.absorption * 100))))

function labelize(reason: string): string {
  return reason.split('_').join(' ')
}

function pushDecision(event: DecisionEvent) {
  decisions.value.push(event)
  if (decisions.value.length > 24) {
    decisions.value.shift()
  }
}

function onState(payload: StrategyState) {
  strategyState.value = payload
}

function onRegime(payload: StrategyRegime) {
  regime.value = payload
}

function onSetup(payload: StrategySetup) {
  setup.value = payload
}

function onMicro(payload: StrategyMicro) {
  micro.value = payload
}

function onDecision(payload: DecisionEvent) {
  pushDecision(payload)
}

onMounted(() => {
  props.socket.on('strategy_state', onState)
  props.socket.on('strategy_regime', onRegime)
  props.socket.on('strategy_setup', onSetup)
  props.socket.on('strategy_microstate', onMicro)
  props.socket.on('strategy_decision', onDecision)
})

onUnmounted(() => {
  props.socket.off('strategy_state', onState)
  props.socket.off('strategy_regime', onRegime)
  props.socket.off('strategy_setup', onSetup)
  props.socket.off('strategy_microstate', onMicro)
  props.socket.off('strategy_decision', onDecision)
})
</script>

<template>
  <section class="strategy-panel">
    <header class="panel-head">
      <span class="panel-title">Strategy dashboard</span>
      <span class="gate" :class="{ 'gate--open': strategyState.entryGateOpen }">
        {{ strategyState.entryGateOpen ? 'ENTRY GATE OPEN' : 'ENTRY GATE CLOSED' }}
      </span>
    </header>

    <div class="state-row">
      <span
        v-for="s in states"
        :key="s"
        class="state-chip"
        :class="{ 'state-chip--active': strategyState.state === s }"
      >
        {{ s }}
      </span>
    </div>

    <div class="cards">
      <article class="card">
        <div class="card-title">Regime</div>
        <div class="line">
          <span class="k">tradable</span><span :class="regime.tradable ? 'v v--ok' : 'v v--bad'">{{ regime.tradable }}</span>
        </div>
        <div class="line"><span class="k">type</span><span class="v">{{ regime.type }}</span></div>
        <div class="line"><span class="k">volatility</span><span class="v">{{ regime.volatility }}</span></div>
        <div class="tags">
          <span v-for="r in regime.reasons" :key="r" class="tag">{{ labelize(r) }}</span>
        </div>
      </article>

      <article class="card">
        <div class="card-title">Setup</div>
        <div class="line"><span class="k">type</span><span class="v">{{ setup.type ?? 'none' }}</span></div>
        <div class="line"><span class="k">direction</span><span class="v">{{ setup.direction ?? '-' }}</span></div>
        <div class="meter">
          <div class="meter-label">quality {{ setupQualityPct }}%</div>
          <div class="meter-track"><div class="meter-fill" :style="{ width: `${setupQualityPct}%` }" /></div>
        </div>
        <div class="tags">
          <span v-for="r in setup.reasons" :key="r" class="tag">{{ labelize(r) }}</span>
        </div>
      </article>

      <article class="card">
        <div class="card-title">Microstate</div>
        <div class="line"><span class="k">pressure</span><span class="v">{{ micro.pressure.toFixed(3) }}</span></div>
        <div class="meter">
          <div class="meter-label">pressure balance</div>
          <div class="meter-track"><div class="meter-fill meter-fill--pressure" :style="{ width: `${pressurePct}%` }" /></div>
        </div>
        <div class="line"><span class="k">absorption</span><span class="v">{{ micro.absorption.toFixed(3) }}</span></div>
        <div class="meter">
          <div class="meter-label">absorption</div>
          <div class="meter-track"><div class="meter-fill meter-fill--absorption" :style="{ width: `${absorptionPct}%` }" /></div>
        </div>
        <div class="line"><span class="k">volatility</span><span class="v">{{ micro.volatility.toFixed(3) }}</span></div>
      </article>
    </div>

    <article class="timeline">
      <div class="timeline-title">Decision timeline</div>
      <div v-if="decisions.length === 0" class="empty">Waiting for strategy events...</div>
      <div v-else class="timeline-list">
        <div v-for="(d, i) in [...decisions].reverse()" :key="i" class="timeline-item">
          <span class="timeline-kind">{{ labelize(d.kind) }}</span>
          <span class="timeline-ts">{{ Number(d.ts).toFixed(3) }}</span>
        </div>
      </div>
    </article>
  </section>
</template>

<style scoped>
.strategy-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  background: linear-gradient(180deg, #0f1826 0%, #101928 100%);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(15, 23, 42, 0.35);
}

.panel-title {
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #94a3b8;
  font-weight: 700;
}

.gate {
  font-size: 10px;
  letter-spacing: 0.05em;
  font-weight: 700;
  color: #ef4444;
}

.gate--open {
  color: #22c55e;
}

.state-row {
  display: flex;
  gap: 6px;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  overflow-x: auto;
  scrollbar-width: thin;
  scrollbar-color: #3d5169 transparent;
}

.state-chip {
  font-size: 10px;
  border: 1px solid #334155;
  padding: 2px 6px;
  border-radius: 999px;
  color: #94a3b8;
  white-space: nowrap;
}

.state-chip--active {
  border-color: #3b82f6;
  color: #bfdbfe;
  background: rgba(59, 130, 246, 0.2);
}

.cards {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  max-height: 42%;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #3d5169 #0d1520;
}

.card {
  background: rgba(26, 35, 50, 0.92);
  border: 1px solid rgba(71, 85, 105, 0.55);
  border-radius: 8px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.card-title {
  font-size: 11px;
  font-weight: 700;
  color: #e2e8f0;
}

.line {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
}

.k {
  color: #94a3b8;
}

.v {
  color: #e2e8f0;
  font-variant-numeric: tabular-nums;
}

.v--ok {
  color: #22c55e;
}

.v--bad {
  color: #ef4444;
}

.meter {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.meter-label {
  font-size: 10px;
  color: #94a3b8;
  letter-spacing: 0.04em;
}

.meter-track {
  height: 6px;
  border-radius: 999px;
  background: #0f172a;
  border: 1px solid #334155;
  overflow: hidden;
}

.meter-fill {
  height: 100%;
  background: linear-gradient(90deg, #38bdf8, #60a5fa);
}

.meter-fill--pressure {
  background: linear-gradient(90deg, #ef4444, #f59e0b, #22c55e);
}

.meter-fill--absorption {
  background: linear-gradient(90deg, #60a5fa, #a78bfa);
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.tag {
  font-size: 10px;
  color: #cbd5e1;
  border: 1px solid #334155;
  border-radius: 999px;
  padding: 2px 6px;
}

.timeline {
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 8px 10px 10px;
  background: rgba(13, 21, 32, 0.18);
}

.timeline-title {
  font-size: 11px;
  font-weight: 700;
  color: #e2e8f0;
  margin-bottom: 8px;
}

.timeline-list {
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  scrollbar-width: thin;
  scrollbar-color: #3d5169 #0d1520;
}

.timeline-item {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  border: 1px solid rgba(71, 85, 105, 0.6);
  border-radius: 6px;
  background: #1a2332;
  padding: 6px 8px;
}

.timeline-kind {
  color: #cbd5e1;
}

.timeline-ts {
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}

.empty {
  font-size: 12px;
  color: #64748b;
}

@media (max-width: 980px) {
  .cards {
    grid-template-columns: 1fr;
    max-height: none;
  }
}
</style>
