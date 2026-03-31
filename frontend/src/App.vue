<script setup lang="ts">
import { onMounted, onUnmounted, provide, ref, shallowRef } from 'vue'
import { io, Socket } from 'socket.io-client'
import Chart from './Chart.vue'
import { ChartSyncGroup, chartSyncKey } from './chartSync'

const syncCharts = ref(true)
const chartSync = new ChartSyncGroup(() => syncCharts.value)
provide(chartSyncKey, chartSync)

let url = 'http://localhost:8000'
if (window.location.hostname === 'play.nukesmp.com') {
  url = 'http://play.nukesmp.com:8000'
}

const socket = shallowRef<Socket | null>(null)
const connected = ref(false)

const backtest = () => {
  const d = "2026-03-27" // prompt("enter date")
  socket.value?.emit('backtest', d)
}

onMounted(() => {
  const s = io(url)
  socket.value = s
  s.on('connect', () => {
    connected.value = true
  })
  s.on('disconnect', () => {
    connected.value = false
  })
})

onUnmounted(() => {
  socket.value?.disconnect()
})
</script>

<template>
  <div class="app">
    <header class="app-header">
      <div class="app-header__brand">
        <span class="app-header__mark" aria-hidden="true">
          <svg width="28" height="28" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="2" y="2" width="28" height="28" rx="6" stroke="currentColor" stroke-width="1.5" opacity="0.35"/>
            <path d="M8 22 L12 14 L16 18 L20 10 L24 16" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </span>
        <div>
          <h1 class="app-header__title">Cheese trading</h1>
          <p class="app-header__subtitle">Backtest view — tick stream and aggregated bars</p>
        </div>
      </div>
      <div class="app-header__actions">
        <label class="sync-switch" :data-on="syncCharts">
          <span class="sync-switch__label">Sync charts</span>
          <input
            v-model="syncCharts"
            type="checkbox"
            class="sync-switch__input"
            role="switch"
            :aria-checked="syncCharts ? 'true' : 'false'"
          />
          <span class="sync-switch__track" aria-hidden="true">
            <span class="sync-switch__thumb" />
          </span>
        </label>
        <span class="status-pill" :data-on="connected">
          <span class="status-pill__dot" />
          {{ connected ? 'Live socket' : 'Disconnected' }}
        </span>
        <button type="button" class="btn-backtest" @click="backtest">
          Run backtest
        </button>
      </div>
    </header>

    <main v-if="socket" class="chart-board">
      <section class="chart-card chart-card--wide">
        <div class="chart-card__head">
          <span class="chart-card__icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M4 18 L8 12 L12 16 L16 8 L20 14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
              <circle cx="4" cy="18" r="1.5" fill="currentColor"/>
              <circle cx="20" cy="14" r="1.5" fill="currentColor"/>
            </svg>
          </span>
          <div>
            <h2 class="chart-card__title">Tick — line</h2>
            <p class="chart-card__hint">Per-trade close, microsecond time axis</p>
          </div>
        </div>
        <Chart class="tick-chart" :socket="socket" endpoint="tick" seriesType="line" />
      </section>

      <div class="chart-row">
        <section class="chart-card">
          <div class="chart-card__head">
            <span class="chart-card__icon" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="6" y="8" width="4" height="10" rx="0.5" stroke="currentColor" stroke-width="1.4"/>
                <line x1="8" y1="4" x2="8" y2="20" stroke="currentColor" stroke-width="1.2"/>
                <rect x="14" y="6" width="4" height="12" rx="0.5" stroke="currentColor" stroke-width="1.4"/>
                <line x1="16" y1="3" x2="16" y2="21" stroke="currentColor" stroke-width="1.2"/>
              </svg>
            </span>
            <div>
              <h2 class="chart-card__title">10-tick bars</h2>
              <p class="chart-card__hint">Candlestick, 10 trades per bar</p>
            </div>
          </div>
          <Chart class="ten-tick-chart" :socket="socket" endpoint="10-tick" seriesType="candlestick" />
        </section>

        <section class="chart-card">
          <div class="chart-card__head">
            <span class="chart-card__icon chart-card__icon--alt" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="5" y="7" width="5" height="11" rx="0.5" stroke="currentColor" stroke-width="1.4"/>
                <line x1="7.5" y1="3" x2="7.5" y2="21" stroke="currentColor" stroke-width="1.2"/>
                <rect x="14" y="5" width="5" height="14" rx="0.5" stroke="currentColor" stroke-width="1.4"/>
                <line x1="16.5" y1="2" x2="16.5" y2="22" stroke="currentColor" stroke-width="1.2"/>
              </svg>
            </span>
            <div>
              <h2 class="chart-card__title">100-tick bars</h2>
              <p class="chart-card__hint">Candlestick, 100 trades per bar</p>
            </div>
          </div>
          <Chart class="hundred-tick-chart" :socket="socket" endpoint="100-tick" seriesType="candlestick" />
        </section>
      </div>
    </main>
  </div>
</template>

<style>
.app {
  min-height: 100vh;
  padding: 1.25rem 1.25rem 2rem;
  box-sizing: border-box;
}

.app-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem 1.5rem;
  max-width: 1400px;
  margin: 0 auto 1.5rem;
  padding-bottom: 1.25rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}

.app-header__brand {
  display: flex;
  align-items: flex-start;
  gap: 0.875rem;
}

.app-header__mark {
  color: #7dd3fc;
  flex-shrink: 0;
  margin-top: 0.15rem;
}

.app-header__title {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #f1f5f9;
}

.app-header__subtitle {
  margin: 0.2rem 0 0;
  font-size: 0.875rem;
  color: #94a3b8;
  font-weight: 500;
}

.app-header__actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.sync-switch {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  user-select: none;
  font-size: 0.8125rem;
  font-weight: 500;
  color: #94a3b8;
}

.sync-switch__label {
  letter-spacing: 0.02em;
}

.sync-switch__input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
  pointer-events: none;
}

.sync-switch__track {
  position: relative;
  width: 38px;
  height: 22px;
  flex-shrink: 0;
  border-radius: 999px;
  background: rgba(51, 65, 85, 0.85);
  border: 1px solid rgba(148, 163, 184, 0.2);
  transition: background 0.15s ease, border-color 0.15s ease;
}

.sync-switch__thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #e2e8f0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
  transition: transform 0.15s ease, background 0.15s ease;
}

.sync-switch[data-on="true"] .sync-switch__track {
  background: rgba(14, 165, 233, 0.35);
  border-color: rgba(56, 189, 248, 0.45);
}

.sync-switch[data-on="true"] .sync-switch__thumb {
  transform: translateX(16px);
  background: #38bdf8;
}

.sync-switch:focus-within .sync-switch__track {
  outline: 2px solid rgba(56, 189, 248, 0.45);
  outline-offset: 2px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.4rem 0.75rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: #94a3b8;
  background: rgba(15, 23, 42, 0.65);
  border: 1px solid rgba(148, 163, 184, 0.15);
}

.status-pill[data-on="true"] {
  color: #6ee7b7;
  border-color: rgba(110, 231, 183, 0.25);
  background: rgba(6, 78, 59, 0.25);
}

.status-pill__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #64748b;
}

.status-pill[data-on="true"] .status-pill__dot {
  background: #34d399;
  box-shadow: 0 0 10px rgba(52, 211, 153, 0.65);
}

.btn-backtest {
  appearance: none;
  border: none;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.875rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  padding: 0.55rem 1.15rem;
  border-radius: 8px;
  color: #0f172a;
  background: linear-gradient(165deg, #7dd3fc 0%, #38bdf8 50%, #0ea5e9 100%);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.2) inset,
    0 4px 14px rgba(14, 165, 233, 0.35);
  transition: transform 0.12s ease, box-shadow 0.12s ease, filter 0.12s ease;
}

.btn-backtest:hover {
  filter: brightness(1.05);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.25) inset,
    0 6px 18px rgba(14, 165, 233, 0.45);
}

.btn-backtest:active {
  transform: translateY(1px);
}

.chart-board {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.chart-row {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.25rem;
}

@media (min-width: 960px) {
  .chart-row {
    grid-template-columns: 1fr 1fr;
  }
}

.chart-card {
  background: linear-gradient(165deg, rgba(17, 24, 39, 0.92) 0%, rgba(10, 14, 22, 0.98) 100%);
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 12px;
  padding: 0.85rem 0.85rem 0.75rem;
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.04) inset,
    0 12px 40px rgba(0, 0, 0, 0.35);
}

.chart-card--wide {
  padding-top: 0.75rem;
}

.chart-card__head {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  margin-bottom: 0.65rem;
  padding: 0 0.15rem;
}

.chart-card__icon {
  color: #38bdf8;
  flex-shrink: 0;
  margin-top: 0.1rem;
  opacity: 0.95;
}

.chart-card__icon--alt {
  color: #a78bfa;
}

.chart-card__title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: #f1f5f9;
}

.chart-card__hint {
  margin: 0.15rem 0 0;
  font-size: 0.75rem;
  color: #64748b;
  font-weight: 500;
}

.tick-chart,
.ten-tick-chart,
.hundred-tick-chart {
  width: 100%;
  height: min(38vh, 420px);
  min-height: 240px;
  border-radius: 8px;
  overflow: hidden;
}

.tick-chart {
  min-height: 50vh;
}
</style>
