<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue"
import { useBackend } from "./useBackend"
import { useChart } from "./useChart"

// --- State (wire these to your backend later)
const botEnabled = ref(false)
const session = ref<"ETH" | "RTH" | "ALL">("RTH")
const windowStart = ref("09:30")
const windowEnd = ref("16:00")
const lotsSize = ref(1)
const chartContainer = ref<HTMLElement | null>(null)
const loadingChartData = ref(false)
const logsContainer = ref<HTMLElement | null>(null)
const logs = ref<Array<{ timestamp: string; message: string }>>([])
const loadingLogs = ref(false)

const { connect, connected, sendMessage, request } = useBackend()
const { chart, initChart, addPriceSeries, addRegimeSeries, addValueAreaSeries, addChopSignalSeries, clearChart } = useChart()

const currentTime = ref("")
let timeInterval: ReturnType<typeof setInterval> | null = null

const updateTime = async () => {
  const now = new Date()
  const hours = String(now.getHours()).padStart(2, "0")
  const minutes = String(now.getMinutes()).padStart(2, "0")
  const seconds = String(now.getSeconds()).padStart(2, "0")
  currentTime.value = `${hours}:${minutes}:${seconds}`
  if (seconds === "01" && !loadingChartData.value) {
    loadingChartData.value = true
    console.log("Reloading chart data...")
    getEnrichedData()
  }
  if (seconds === "02" && loadingChartData.value) {
    loadingChartData.value = false
  }
}

const sessionOptions = [
  { value: "ETH" as const, label: "ETH" },
  { value: "RTH" as const, label: "RTH" },
  { value: "ALL" as const, label: "ALL" },
]

const toggleBot = () => {
  botEnabled.value = !botEnabled.value
  sendMessage({ action: "set_bot_enabled", data: botEnabled.value })
}

const updateLotsSize = () => {
  sendMessage({ action: "set_lots_size", data: lotsSize.value})
}

const getEnrichedData = async () => {
  const enrichedData = JSON.parse(await request({ action: "get_enriched_data" }, 5) as any)
  clearChart()
  addPriceSeries(enrichedData)
  addChopSignalSeries(enrichedData) 
  addRegimeSeries(enrichedData)
  addValueAreaSeries(enrichedData)
}

const updateSession = async () => {
  sendMessage({ action: "set_session", data: session.value })
}

const loadLogs = async () => {
  try {
    loadingLogs.value = true
    const logsText = await request({ action: "get_logs" }, 6) as string
    if (logsText) {
      const lines = logsText.trim().split('\n').filter(line => line.trim())
      logs.value = lines.map(line => {
        const match = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (.+)$/)
        if (match && match[1] && match[2]) {
          return { timestamp: match[1], message: match[2] }
        }
        return { timestamp: '', message: line }
      })
      // Auto-scroll to bottom after logs are loaded
      setTimeout(() => {
        if (logsContainer.value) {
          logsContainer.value.scrollTop = logsContainer.value.scrollHeight
        }
      }, 100)
    }
  } catch (error) {
    console.error('Failed to load logs:', error)
  } finally {
    loadingLogs.value = false
  }
}

onMounted(async() => {
  connect()
  chartContainer.value = document.querySelector(".chart") as HTMLElement
  initChart(chartContainer.value)
  const botData = await request({ action: "get_all" }, 1) as any
  botEnabled.value = botData.enabled as boolean
  session.value = botData.session
  lotsSize.value = botData.lots_size
  getEnrichedData()
  loadLogs()

  updateTime()
  timeInterval = setInterval(updateTime, 100)
})

onBeforeUnmount(() => {
  if (timeInterval) {
    clearInterval(timeInterval)
  }
})
</script>

<template>
  <div class="dashboard">
    <header class="header">
      <h1 class="title">
        <span class="title-icon">◈</span>
        Cheese Trading Bot - {{ connected ? "Connected" : "Disconnected" }}
      </h1>
      <div class="header-actions">
        <span class="status-label">Bot</span>
        <button
          type="button"
          class="toggle"
          :class="{ on: botEnabled }"
          :aria-pressed="botEnabled"
          @click="toggleBot"
        >
          <span class="toggle-track">
            <span class="toggle-thumb" />
          </span>
        </button>
        <span class="status-value" :class="{ active: botEnabled }">
          {{ botEnabled ? "ON" : "OFF" }}
        </span>
      </div>
      <button type="button" class="get-enriched-data" @click="getEnrichedData">Get Enriched Data</button>
    </header>

    <main class="main">
      <section class="chart-section">
        <div class="chart-header">
          <h2 class="chart-title">Chart</h2>
          <span class="chart-hint">{{ currentTime }}</span>
        </div>
        <div ref="chartContainer" class="chart" />>
      </section>

      <aside class="controls">
        <h2 class="controls-title">Session &amp; window</h2>

        <div class="field">
          <label class="label">Trading session</label>
          <select v-model="session" class="select" @change="updateSession">
            <option
              v-for="opt in sessionOptions"
              :key="opt.value"
              :value="opt.value"
            >
              {{ opt.label }}
            </option>
          </select>
        </div>

        <div class="field-row">
          <div class="field">
            <label class="label">Window start</label>
            <input
              v-model="windowStart"
              type="time"
              class="input"
              step="60"
            />
          </div>
          <div class="field">
            <label class="label">Window end</label>
            <input
              v-model="windowEnd"
              type="time"
              class="input"
              step="60"
            />
          </div>
        </div>

        <div class="field">
          <label class="label">Lots size</label>
          <input
            v-model.number="lotsSize"
            @change="updateLotsSize"
            type="number"
            class="input"
            min="1"
            step="1"
          />
        </div>
      </aside>

      <section class="logs-section">
        <div class="logs-header">
          <h2 class="logs-title">Logs</h2>
          <button 
            type="button" 
            class="refresh-logs" 
            @click="loadLogs"
            :disabled="loadingLogs"
          >
            {{ loadingLogs ? "Loading..." : "Refresh" }}
          </button>
        </div>
        <div ref="logsContainer" class="logs-container">
          <div v-if="logs.length === 0 && !loadingLogs" class="logs-empty">
            No logs available
          </div>
          <div v-else class="logs-list">
            <div 
              v-for="(log, index) in logs" 
              :key="index" 
              class="log-entry"
            >
              <span class="log-timestamp">{{ log.timestamp }}</span>
              <span class="log-message">{{ log.message }}</span>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.dashboard {
  --bg: #0f1419;
  --surface: #1a2332;
  --surface-hover: #243044;
  --border: rgba(148, 163, 184, 0.15);
  --text: #e2e8f0;
  --muted: #94a3b8;
  --accent: #fbbf24;
  --accent-dim: rgba(251, 191, 36, 0.25);
  --on: #22c55e;
  --on-dim: rgba(34, 197, 94, 0.2);
  font-family: "Outfit", system-ui, sans-serif;
  height: 100vh;
  width: 100vw;
  max-width: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  color: var(--text);
  box-sizing: border-box;
}

.header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}

.title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.title-icon {
  color: var(--accent);
  font-size: 1rem;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}

.toggle {
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
  display: block;
}

.toggle-track {
  display: flex;
  align-items: center;
  width: 2.75rem;
  height: 1.25rem;
  border-radius: 999px;
  background: var(--surface-hover);
  border: 1px solid var(--border);
  transition: background 0.2s, border-color 0.2s;
}

.toggle.on .toggle-track {
  background: var(--on-dim);
  border-color: var(--on);
}

.toggle-thumb {
  width: 1rem;
  height: 1rem;
  border-radius: 50%;
  background: var(--muted);
  margin-left: 0.15rem;
  transition: transform 0.2s, background 0.2s;
}

.toggle.on .toggle-thumb {
  transform: translateX(1.5rem);
  background: var(--on);
}

.status-value {
  font-family: "JetBrains Mono", monospace;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted);
  min-width: 2rem;
}

.status-value.active {
  color: var(--on);
}

.main {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 280px 320px;
  gap: 1rem;
  padding: 1rem;
  overflow: hidden;
}

@media (max-width: 1400px) {
  .main {
    grid-template-columns: 1fr 280px;
    grid-template-rows: 1fr auto;
  }

  .logs-section {
    grid-column: 1 / -1;
  }
}

@media (max-width: 900px) {
  .main {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr auto auto;
  }

  .controls {
    width: 100%;
    min-width: 0;
  }

  .logs-section {
    grid-column: 1;
  }
}

.chart-section {
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.chart-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border);
}

.chart-title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
}

.chart-hint {
  font-size: 0.7rem;
  color: var(--muted);
}

.chart {
  flex: 1;
  min-height: 0;
  width: 100%;
}

.controls {
  flex-shrink: 0;
  width: 280px;
  min-width: 280px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1.25rem;
  overflow-y: auto;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.controls-title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
}

.controls .field {
  margin: 0;
}

.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.field-row .field {
  min-width: 0;
}

.label {
  display: block;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--muted);
  margin-bottom: 0.4rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.select,
.input {
  width: 100%;
  min-width: 0;
  padding: 0.5rem 0.75rem;
  font-family: "JetBrains Mono", monospace;
  font-size: 0.875rem;
  color: var(--text);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
  box-sizing: border-box;
}

.select:hover,
.input:hover {
  border-color: rgba(148, 163, 184, 0.3);
}

.select:focus,
.input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-dim);
}

.input[type="number"] {
  -moz-appearance: textfield;
  appearance: textfield;
}

.input[type="number"]::-webkit-outer-spin-button,
.input[type="number"]::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.get-enriched-data {
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}

.get-enriched-data:hover {
  background: var(--surface-hover);
  border-color: rgba(148, 163, 184, 0.3);
}

.logs-section {
  flex-shrink: 0;
  width: 320px;
  min-width: 320px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.logs-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border);
}

.logs-title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
}

.refresh-logs {
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}

.refresh-logs:hover:not(:disabled) {
  background: var(--surface-hover);
  border-color: rgba(148, 163, 184, 0.3);
}

.refresh-logs:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.logs-container {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0.5rem;
}

.logs-container::-webkit-scrollbar {
  width: 8px;
}

.logs-container::-webkit-scrollbar-track {
  background: var(--bg);
}

.logs-container::-webkit-scrollbar-thumb {
  background: var(--surface-hover);
  border-radius: 4px;
}

.logs-container::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.3);
}

.logs-empty {
  padding: 2rem 1rem;
  text-align: center;
  color: var(--muted);
  font-size: 0.875rem;
}

.logs-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.log-entry {
  padding: 0.625rem 0.75rem;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.8125rem;
  line-height: 1.5;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  transition: border-color 0.2s;
}

.log-entry:hover {
  border-color: rgba(148, 163, 184, 0.3);
}

.log-timestamp {
  font-family: "JetBrains Mono", monospace;
  font-size: 0.75rem;
  color: var(--muted);
}

.log-message {
  color: var(--text);
  word-break: break-word;
}
</style>
