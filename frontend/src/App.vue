<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from "vue"
import { useBackend } from "./composables/useBackend"
import { useChart } from "./composables/useChart"
import Header from "./components/Header.vue"
import ChartSection from "./components/ChartSection.vue"
import Controls from "./components/Controls.vue"
import LogsSection from "./components/LogsSection.vue"

// --- State
const botEnabled = ref(false)
const session = ref<"ETH" | "RTH" | "ALL">("RTH")
const windowStart = ref("09:30")
const windowEnd = ref("16:00")
const lotsSize = ref(1)
const chartSectionRef = ref<InstanceType<typeof ChartSection> | null>(null)
const loadingChartData = ref(false)
const logs = ref<Array<{ timestamp: string; message: string }>>([])
const loadingLogs = ref(false)

const { connect, connected, sendMessage, request, loadLogs, updateDashboard: updateDashboardFromBackend, setUpdateAllCallback } = useBackend()
const { chart, initChart, addPriceSeries, addRegimeSeries, addValueAreaSeries, addChopSignalSeries, addTrendSignalSeries, clearChart } = useChart()

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

const toggleBot = () => {
  botEnabled.value = !botEnabled.value
  sendMessage({ action: "set_bot_enabled", data: botEnabled.value, update_all: true})
}

const updateLotsSize = () => {
  sendMessage({ action: "set_lots_size", data: lotsSize.value, update_all: true})
}

const getEnrichedData = async () => {
  const enrichedData = JSON.parse(await request({ action: "get_enriched_data" }, 5) as any)
  clearChart()
  addPriceSeries(enrichedData)
  addChopSignalSeries(enrichedData) 
  addTrendSignalSeries(enrichedData)
  addRegimeSeries(enrichedData)
  addValueAreaSeries(enrichedData)
  console.log(enrichedData[enrichedData.length - 1])
}

const updateSession = async () => {
  sendMessage({ action: "set_session", data: session.value, update_all: true})
}

const updateDashboard = async () => {
  loadingLogs.value = true
  try {
    const { botData, logs: loadedLogs } = await updateDashboardFromBackend()
    botEnabled.value = botData.enabled
    session.value = botData.session
    lotsSize.value = botData.lots_size
    logs.value = loadedLogs
  } finally {
    loadingLogs.value = false
  }
}

const handleRefreshLogs = async () => {
  loadingLogs.value = true
  try {
    logs.value = await loadLogs()
  } finally {
    loadingLogs.value = false
  }
}

// Set up the update_all callback after updateDashboard is defined
setUpdateAllCallback(updateDashboard)

onMounted(async() => {
  connect()
  await nextTick()
  if (chartSectionRef.value?.chartContainer) {
    initChart(chartSectionRef.value.chartContainer)
  }
  updateDashboard()
  getEnrichedData()

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
    <Header 
      :connected="connected" 
      :bot-enabled="botEnabled" 
      @toggle-bot="toggleBot"
    />

    <main class="main">
      <ChartSection 
        ref="chartSectionRef"
        :current-time="currentTime"
      />

      <Controls
        v-model:session="session"
        v-model:window-start="windowStart"
        v-model:window-end="windowEnd"
        v-model:lots-size="lotsSize"
        @session-change="updateSession"
        @lots-size-change="updateLotsSize"
      />

      <LogsSection
        :logs="logs"
        :loading-logs="loadingLogs"
        @refresh="handleRefreshLogs"
      />
    </main>
  </div>
</template>

<style scoped>
@import './styles/variables.css';

.dashboard {
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
</style>
