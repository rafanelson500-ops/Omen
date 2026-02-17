<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue"
import { createChart, type IChartApi } from "lightweight-charts"
import { useBackend } from "./useBackend"
import { idText } from "typescript"

// --- State (wire these to your backend later)
const botEnabled = ref(false)
const session = ref<"ETH" | "RTH" | "ALL">("RTH")
const windowStart = ref("09:30")
const windowEnd = ref("16:00")
const lotsSize = ref(1)

const { connect, connected, sendMessage, request } = useBackend()

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

onMounted(async() => {
  connect()
  const botData = await request({ action: "get_all" }, 1) as any
  botEnabled.value = botData.enabled as boolean
  session.value = botData.session
  lotsSize.value = botData.lots_size
})

onBeforeUnmount(() => {
  
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
    </header>

    <main class="main">
      <section class="chart-section">
        <div class="chart-header">
          <h2 class="chart-title">Chart</h2>
          <span class="chart-hint">Loading...</span>
        </div>
        <div ref="chartContainer" class="chart" />
      </section>

      <aside class="controls">
        <h2 class="controls-title">Session &amp; window</h2>

        <div class="field">
          <label class="label">Trading session</label>
          <select v-model="session" class="select">
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
  grid-template-columns: 1fr 280px;
  gap: 1rem;
  padding: 1rem;
  overflow: hidden;
}

@media (max-width: 900px) {
  .main {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr auto;
  }

  .controls {
    width: 100%;
    min-width: 0;
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
}

.input[type="number"]::-webkit-outer-spin-button,
.input[type="number"]::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
</style>
