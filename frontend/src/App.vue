<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from "vue"
import { useBackend } from "./composables/useBackend"
import { useChart } from "./composables/useChart"
import Header from "./components/Header.vue"
import ChartSection from "./components/ChartSection.vue"
import Controls from "./components/Controls.vue"
import LogsSection from "./components/LogsSection.vue"
import BacktestSection from "./components/BacktestSection.vue"

// --- State
const botEnabled = ref(false)
const session = ref<"ETH" | "RTH" | "ALL">("RTH")
const lotsSize = ref(1)
const confidenceThreshold = ref(0)
const mode = ref<"paper" | "live" | "prop">("paper")
const currentPosition = ref(0)
const chartSectionRef = ref<InstanceType<typeof ChartSection> | null>(null)
const backtestSectionRef = ref<InstanceType<typeof BacktestSection> | null>(null)
const loadingChartData = ref(false)
const logs = ref<Array<{ timestamp: string; message: string }>>([])
const loadingLogs = ref(false)
const loadingBacktest = ref(false)
const cachedBacktestData = ref<any[]>([])
const backtestDataLength = ref(0)

const { connect, connected, sendMessage, request, loadLogs, updateDashboard: updateDashboardFromBackend, setUpdateAllCallback, getBacktestData } = useBackend()
const { chart, initChart, addPriceSeries, addRegimeSeries, addValueAreaSeries, addChopSignalSeries, addTrendSignalSeries, addWeightedSignalSeries, clearChart, initBacktestChart, addBacktestPriceSeries, addBacktestCumulativeSeries, addBacktestPositionSeries, clearBacktestChart } = useChart()

const currentTime = ref("")
let timeInterval: ReturnType<typeof setInterval> | null = null

const updateTime = async () => {
  const now = new Date()
  const hours = String(now.getHours()).padStart(2, "0")
  const minutes = String(now.getMinutes()).padStart(2, "0")
  const seconds = String(now.getSeconds()).padStart(2, "0")
  currentTime.value = `${hours}:${minutes}:${seconds}`
  if (parseInt(minutes) % 5 === 0) {
    if (seconds === "05" && !loadingChartData.value) {
      loadingChartData.value = true
      console.log("Reloading chart data...")
      getEnrichedData()
      updateDashboard()
    }
    if (seconds === "06" && loadingChartData.value) {
      loadingChartData.value = false
    }
  }
}

const toggleBot = () => {
  botEnabled.value = !botEnabled.value
  sendMessage({ action: "set_bot_enabled", data: botEnabled.value, update_all: true})
}

const updateLotsSize = () => {
  sendMessage({ action: "set_lots_size", data: lotsSize.value, update_all: true})
}

const updateConfidenceThreshold = () => {
  sendMessage({ action: "set_confidence_threshold", data: confidenceThreshold.value, update_all: true})
}

const updateMode = () => {
  sendMessage({ action: "set_mode", data: mode.value, update_all: true})
}

const getEnrichedData = async () => {
  const enrichedData = JSON.parse(await request({ action: "get_enriched_data" }, 5) as any)
  clearChart()
  addPriceSeries(enrichedData)
  addValueAreaSeries(enrichedData)
  addChopSignalSeries(enrichedData) 
  addTrendSignalSeries(enrichedData)
  addRegimeSeries(enrichedData)
  addWeightedSignalSeries(enrichedData)
  console.log(enrichedData)
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
    confidenceThreshold.value = botData.confidence_threshold
    mode.value = botData.mode
    currentPosition.value = botData.current_position
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

const renderBacktestData = (data: any[]) => {
  clearBacktestChart()
  addBacktestPriceSeries(data)
  addBacktestCumulativeSeries(data)
  addBacktestPositionSeries(data)
}

const loadBacktestData = async () => {
  loadingBacktest.value = true
  try {
    const backtestData = await getBacktestData()
    cachedBacktestData.value = backtestData
    backtestDataLength.value = backtestData.length
    renderBacktestData(backtestData)
  } catch (error) {
    console.error('Failed to load backtest data:', error)
  } finally {
    loadingBacktest.value = false
  }
}

const handleBacktestRangeChange = (start: number, end: number) => {
  if (cachedBacktestData.value.length === 0) return
  const sliced = cachedBacktestData.value.slice(start, end)
  if (sliced.length === 0) return
  const strategyOffset = sliced[0].cum_strategy || 0
  const buyHoldOffset = sliced[0].cum_buy_hold || 0
  const adjusted = sliced.map((row: any) => ({
    ...row,
    cum_strategy: (row.cum_strategy || 0) - strategyOffset,
    cum_buy_hold: (row.cum_buy_hold || 0) - buyHoldOffset,
  }))
  renderBacktestData(adjusted)
}

const handleBacktestReset = () => {
  if (cachedBacktestData.value.length === 0) return
  renderBacktestData(cachedBacktestData.value)
}

// Set up the update_all callback after updateDashboard is defined
setUpdateAllCallback(updateDashboard)

onMounted(async() => {
  connect()
  await nextTick()
  if (chartSectionRef.value?.chartContainer) {
    initChart(chartSectionRef.value.chartContainer)
  }
  if (backtestSectionRef.value?.chartContainer) {
    initBacktestChart(backtestSectionRef.value.chartContainer)
  }
  updateDashboard()
  getEnrichedData()
  loadBacktestData()

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
      :current-position="currentPosition"
      @toggle-bot="toggleBot"
    />

    <main class="main">
      <ChartSection 
        ref="chartSectionRef"
        :current-time="currentTime"
      />

      <Controls
        v-model:session="session"
        v-model:lots-size="lotsSize"
        v-model:confidence-threshold="confidenceThreshold"
        v-model:mode="mode"
        @session-change="updateSession"
        @lots-size-change="updateLotsSize"
        @confidence-threshold-change="updateConfidenceThreshold"
        @mode-change="updateMode"
      />

      <LogsSection
        :logs="logs"
        :loading-logs="loadingLogs"
        @refresh="handleRefreshLogs"
      />
    </main>

    <section class="backtest-container">
      <BacktestSection
        ref="backtestSectionRef"
        :loading-backtest="loadingBacktest"
        :data-length="backtestDataLength"
        @load="loadBacktestData"
        @range-change="handleBacktestRangeChange"
        @reset="handleBacktestReset"
      />
    </section>
  </div>
</template>

<style scoped>
@import './styles/variables.css';

.dashboard {
  font-family: "Outfit", system-ui, sans-serif;
  min-height: 100vh;
  width: 100%;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  color: var(--text);
  box-sizing: border-box;
}

.main {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 280px 320px;
  gap: 1.5rem;
  padding: 1.5rem;
  min-height: 600px;
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

.logs-section {
  max-height: 600px;
  overflow-y: auto;
}

.backtest-container {
  padding: 1.5rem;
  padding-top: 0;
  min-height: 600px;
}
</style>
