<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { createChart, ColorType, LineSeries, CrosshairMode } from 'lightweight-charts'
import type { IChartApi, ISeriesApi, UTCTimestamp } from 'lightweight-charts'

interface EquityPoint {
  time: number
  value: number
}

interface Iteration {
  id: number
  equity_curve: EquityPoint[]
  max_profit: number
  max_drawdown: number
  total_return: number
}

interface MonteCarloData {
  iterations: Iteration[]
  stats: {
    max_profits: number[]
    max_drawdowns: number[]
    total_returns: number[]
  }
}

const props = defineProps<{
  loading: boolean
  monteCarloData: MonteCarloData | null
}>()

const emit = defineEmits<{
  (e: 'run'): void
}>()

const equityChartContainer = ref<HTMLElement | null>(null)
let equityChart: IChartApi | null = null
let equitySeries: ISeriesApi<any>[] = []

const chartTheme = {
  bg: '#1a2332',
  text: '#e2e8f0',
  muted: '#94a3b8',
  border: 'rgba(148, 163, 184, 0.22)',
  accent: '#fbbf24',
}

// Generate a unique HSL color for any iteration index across any N
const iterationColor = (idx: number, total: number) => {
  const hue = (idx / total) * 360
  return `hsla(${hue.toFixed(1)}, 75%, 65%, 0.55)`
}

onMounted(() => {
  if (equityChartContainer.value) {
    equityChart = createChart(equityChartContainer.value, {
      layout: {
        textColor: chartTheme.text,
        background: { type: ColorType.Solid, color: chartTheme.bg },
        fontFamily: '"Outfit", system-ui, sans-serif',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: chartTheme.border },
        horzLines: { color: chartTheme.border },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: chartTheme.muted, labelBackgroundColor: chartTheme.accent },
        horzLine: { color: chartTheme.muted, labelBackgroundColor: chartTheme.accent },
      },
      rightPriceScale: {
        borderColor: chartTheme.border,
        scaleMargins: { top: 0.06, bottom: 0.06 },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: chartTheme.border,
      },
    })
  }
})

const clearEquityChart = () => {
  equitySeries.forEach(s => equityChart?.removeSeries(s))
  equitySeries = []
}

const renderEquityChart = (data: MonteCarloData) => {
  if (!equityChart) return
  clearEquityChart()
  const total = data.iterations.length
  data.iterations.forEach((iter, idx) => {
    const color = iterationColor(idx, total)
    const s = equityChart!.addSeries(LineSeries, {
      color,
      lineWidth: 1,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
      lastValueVisible: false,
      priceLineVisible: false,
      title: '',
    })
    s.setData(iter.equity_curve.map(p => ({ time: p.time as UTCTimestamp, value: p.value })))
    equitySeries.push(s)
  })
}

watch(
  () => props.monteCarloData,
  (newData) => {
    if (newData) renderEquityChart(newData)
  }
)

// ── Histogram helpers ─────────────────────────────────────────────────────────
interface HistBin {
  label: string
  count: number
  pct: number
}

const computeHistogram = (values: number[], bins = 8): HistBin[] => {
  if (!values.length) return []
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const binWidth = range / bins
  const counts = Array<number>(bins).fill(0)
  values.forEach(v => {
    let idx = Math.floor((v - min) / binWidth)
    if (idx >= bins) idx = bins - 1
    counts[idx] = (counts[idx] ?? 0) + 1
  })
  return counts.map((count, i) => ({
    label: (min + (i + 0.5) * binWidth).toFixed(1),
    count,
    pct: count / values.length,
  }))
}

const maxProfitBins = computed(() =>
  props.monteCarloData ? computeHistogram(props.monteCarloData.stats.max_profits) : []
)
const maxDrawdownBins = computed(() =>
  props.monteCarloData ? computeHistogram(props.monteCarloData.stats.max_drawdowns) : []
)
const returnsBins = computed(() =>
  props.monteCarloData ? computeHistogram(props.monteCarloData.stats.total_returns) : []
)

const fmt = (v: number) => v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2)
</script>

<template>
  <section class="mc-section">
    <!-- Header -->
    <div class="mc-header">
      <h2 class="mc-title">Monte Carlo</h2>
      <button class="run-button" :disabled="loading" @click="emit('run')">
        <span v-if="loading" class="btn-spinner" />
        {{ loading ? 'Running simulations…' : 'Run Monte Carlo' }}
      </button>
    </div>

    <!-- Equity curves chart (always rendered so chart can mount) -->
    <div class="equity-block">
      <div class="block-header">
        <span class="block-label">
          Equity Curves
          <span v-if="monteCarloData" class="iter-count">({{ monteCarloData.iterations.length }} iterations)</span>
        </span>
        <!-- summary stats instead of per-line legend -->
        <div v-if="monteCarloData" class="equity-summary">
          <span class="summary-pill">
            <span class="summary-key">n</span>
            <span class="summary-val">{{ monteCarloData.iterations.length }}</span>
          </span>
          <span class="summary-pill">
            <span class="summary-key">avg return</span>
            <span class="summary-val" :class="{ positive: monteCarloData.stats.total_returns.reduce((a,b)=>a+b,0) >= 0, negative: monteCarloData.stats.total_returns.reduce((a,b)=>a+b,0) < 0 }">
              {{ fmt(monteCarloData.stats.total_returns.reduce((a,b)=>a+b,0) / monteCarloData.stats.total_returns.length) }}
            </span>
          </span>
          <span class="summary-pill">
            <span class="summary-key">win rate</span>
            <span class="summary-val positive">
              {{ ((monteCarloData.stats.total_returns.filter(r => r > 0).length / monteCarloData.stats.total_returns.length) * 100).toFixed(0) }}%
            </span>
          </span>
        </div>
      </div>

      <!-- Loading overlay -->
      <div v-if="loading" class="chart-overlay">
        <div class="spinner" />
        <span class="loading-text">Running 1000 Monte Carlo simulations…</span>
      </div>

      <!-- Placeholder when no data yet -->
      <div v-else-if="!monteCarloData" class="chart-overlay muted">
        <span>Click "Run Monte Carlo" to simulate randomized equity paths</span>
      </div>

      <div ref="equityChartContainer" class="equity-canvas" />
    </div>

    <!-- Distribution charts (only when data available) -->
    <div v-if="monteCarloData" class="dist-row">

      <!-- Max Profit -->
      <div class="dist-block">
        <div class="block-header">
          <span class="block-label">Max Profit Distribution</span>
          <span class="dist-stat positive">
            avg {{ fmt(monteCarloData.stats.max_profits.reduce((a,b)=>a+b,0)/monteCarloData.stats.max_profits.length) }}
          </span>
        </div>
        <div class="dist-chart">
          <div v-for="bin in maxProfitBins" :key="bin.label" class="bar-row">
            <span class="bar-label">{{ bin.label }}</span>
            <div class="bar-track">
              <div class="bar-fill profit" :style="{ width: (bin.pct * 100) + '%' }" />
            </div>
            <span class="bar-count">{{ bin.count }}</span>
          </div>
        </div>
      </div>

      <!-- Max Drawdown -->
      <div class="dist-block">
        <div class="block-header">
          <span class="block-label">Max Drawdown Distribution</span>
          <span class="dist-stat negative">
            avg {{ fmt(monteCarloData.stats.max_drawdowns.reduce((a,b)=>a+b,0)/monteCarloData.stats.max_drawdowns.length) }}
          </span>
        </div>
        <div class="dist-chart">
          <div v-for="bin in maxDrawdownBins" :key="bin.label" class="bar-row">
            <span class="bar-label">{{ bin.label }}</span>
            <div class="bar-track">
              <div class="bar-fill drawdown" :style="{ width: (bin.pct * 100) + '%' }" />
            </div>
            <span class="bar-count">{{ bin.count }}</span>
          </div>
        </div>
      </div>

      <!-- Returns -->
      <div class="dist-block">
        <div class="block-header">
          <span class="block-label">Returns Distribution</span>
          <span class="dist-stat" :class="{ positive: monteCarloData.stats.total_returns.reduce((a,b)=>a+b,0) >= 0, negative: monteCarloData.stats.total_returns.reduce((a,b)=>a+b,0) < 0 }">
            avg {{ fmt(monteCarloData.stats.total_returns.reduce((a,b)=>a+b,0)/monteCarloData.stats.total_returns.length) }}
          </span>
        </div>
        <div class="dist-chart">
          <div v-for="bin in returnsBins" :key="bin.label" class="bar-row">
            <span class="bar-label">{{ bin.label }}</span>
            <div class="bar-track">
              <div
                class="bar-fill"
                :class="parseFloat(bin.label) >= 0 ? 'returns-pos' : 'returns-neg'"
                :style="{ width: (bin.pct * 100) + '%' }"
              />
            </div>
            <span class="bar-count">{{ bin.count }}</span>
          </div>
        </div>
      </div>

    </div>
  </section>
</template>

<style scoped>
@import '../styles/variables.css';

.mc-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  padding-bottom: 1.25rem;
}

/* ── Header ─────────────────────────────────────── */
.mc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
  gap: 0.5rem;
}

.mc-title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
}

.run-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1.1rem;
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}

.run-button:hover:not(:disabled) {
  background: var(--bg);
  border-color: var(--accent);
  color: var(--accent);
}

.run-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* inline spinner inside button */
.btn-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  flex-shrink: 0;
}

/* ── Equity chart block ─────────────────────────── */
.equity-block {
  position: relative;
  margin: 0 1rem;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
  gap: 0.5rem;
}

.block-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.iter-count {
  font-weight: 400;
  font-size: 0.75rem;
  color: var(--muted);
  margin-left: 0.3rem;
}

.equity-summary {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.summary-pill {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  background: rgba(148, 163, 184, 0.08);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.15rem 0.5rem;
  font-size: 0.75rem;
}

.summary-key {
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  font-size: 0.7rem;
}

.summary-val {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text);
}

.legend-val {
  font-variant-numeric: tabular-nums;
}

.equity-canvas {
  height: 380px;
  width: 100%;
}

/* chart overlay (loading / placeholder) */
.chart-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  background: rgba(26, 35, 50, 0.88);
  z-index: 10;
  font-size: 0.875rem;
  color: var(--text);
}

.chart-overlay.muted {
  color: var(--muted);
  font-size: 0.82rem;
}

/* large spinner for overlay */
.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(255,255,255,0.12);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-text {
  font-size: 0.82rem;
  color: var(--muted);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── Distribution row ───────────────────────────── */
.dist-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  padding: 0 1rem;
}

@media (max-width: 1100px) {
  .dist-row {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 700px) {
  .dist-row {
    grid-template-columns: 1fr;
  }
}

.dist-block {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.dist-stat {
  font-size: 0.78rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.dist-chart {
  padding: 0.6rem 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.bar-row {
  display: grid;
  grid-template-columns: 56px 1fr 24px;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.72rem;
}

.bar-label {
  color: var(--muted);
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.bar-track {
  height: 10px;
  background: rgba(148, 163, 184, 0.08);
  border-radius: 3px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
}

.bar-fill.profit      { background: rgba(34, 197, 94, 0.75); }
.bar-fill.drawdown    { background: rgba(239, 68, 68, 0.75); }
.bar-fill.returns-pos { background: rgba(34, 197, 94, 0.75); }
.bar-fill.returns-neg { background: rgba(239, 68, 68, 0.75); }

.bar-count {
  color: var(--muted);
  text-align: center;
  font-variant-numeric: tabular-nums;
}

/* ── Shared color utils ─────────────────────────── */
.positive { color: #22c55e; }
.negative { color: #ef4444; }
</style>
