<script setup lang="ts">
import { onMounted, ref, onUnmounted } from 'vue'
import { createChart } from 'lightweight-charts'
import { CandlestickSeries, LineSeries, type CandlestickData, type LineData, type Time } from 'lightweight-charts'
import { chartOptions } from './chartOptions'
import { addHmmStateRectangles } from './helpers/hmmStateRectangles'

const chartContainer = ref<HTMLDivElement | null>(null)
const chartData = ref<any[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const fetchData = async () => {
  try {
    loading.value = true
    error.value = null
    const response = await fetch('http://localhost:8000/data')
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    const data = await response.json()
    chartData.value = data
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to fetch data'
    console.error('Error fetching data:', err)
  } finally {
    loading.value = false
  }
}

const cleanSeries = (data: any[], map: Record<string, [string, number]>): any[] => {
    return data.map((item) => {
        const newItem: Record<string, any> = {}
        for (const new_key of Object.keys(map)) {
            const [src, scale] = map[new_key]!
            newItem[new_key] = item[src as keyof typeof item] * scale
        }
        return newItem as any
    })
}

let chart: ReturnType<typeof createChart> | null = null

const resizeHandler = () => {
  if (chart && chartContainer.value) {
    chart.applyOptions({ 
      width: chartContainer.value.clientWidth,
      height: chartContainer.value.clientHeight 
    })
  }
}

onMounted(async () => {
  await fetchData()
  if (chartContainer.value && chartData.value.length > 0) {
    // Use chartOptions for styling
    chart = createChart(chartContainer.value, {
      ...chartOptions,
      width: chartContainer.value.clientWidth,
      height: chartContainer.value.clientHeight,
      autoSize: true,
    })
    
    const priceSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    })
    
    priceSeries.setData(cleanSeries(chartData.value, {
      time: ['time', 1/1000],
      open: ['open', 1],
      high: ['high', 1],
      low: ['low', 1],
      close: ['close', 1],
    }) as CandlestickData<Time>[])
    
    // Add HMM state rectangles as highlighted boxes
    if (chartData.value.length > 0 && chartData.value[0].hmm_state !== undefined) {
      addHmmStateRectangles(priceSeries, chartData.value)
    }
    
    if (chartData.value.length > 0) {
      const columns = Object.keys(chartData.value[0]).filter(key => key.startsWith('graph:'))
      for (const column of columns) {
        const args = column.split(':')
        if (args.length >= 3) {
          const [_, pane, color] = args
          const paneNum = parseInt(pane as string)
          if (!isNaN(paneNum) && pane !== undefined) {
            const seriesColor: string = color || "#aaaaaa"
            const series = chart.addSeries(LineSeries, { 
              color: seriesColor, 
              lineWidth: 1,
              priceLineVisible: false,
              lastValueVisible: true,
            }, paneNum)
            series.setData(cleanSeries(chartData.value, {
              time: ['time', 1/1000],
              value: [column, 1],
            }) as LineData<Time>[])
          }
        }
      }
    }
    
    window.addEventListener('resize', resizeHandler)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeHandler)
  if (chart) {
    chart.remove()
  }
})
</script>

<template>
  <div class="app-container">
    <header class="app-header">
      <h1 class="app-title">Cheese Trading Dashboard</h1>
      <div class="header-actions">
      </div>
    </header>
    
    <main class="app-main">
      <div v-if="error" class="error-message">
        <p>⚠️ {{ error }}</p>
        <button @click="fetchData" class="retry-btn">Retry</button>
      </div>
      
      <div v-else-if="loading" class="loading-container">
        <div class="spinner"></div>
        <p>Loading chart data...</p>
      </div>
      
      <div v-else class="chart-wrapper">
        <div ref="chartContainer" class="chart-container"></div>
      </div>
    </main>
  </div>
</template>

<style scoped>
* {
  box-sizing: border-box;
}

.app-container {
  min-height: 100vh;
  background: linear-gradient(135deg, #0f172a 0%, #1a2332 100%);
  color: #e2e8f0;
  font-family: 'Outfit', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  display: flex;
  flex-direction: column;
}

.app-header {
  background: rgba(26, 35, 50, 0.8);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
  padding: 1.5rem 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.app-title {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 600;
  background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: -0.02em;
}

.header-actions {
  display: flex;
  gap: 1rem;
}

.refresh-btn {
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: white;
  border: none;
  padding: 0.625rem 1.25rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3);
}

.refresh-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(59, 130, 246, 0.4);
}

.refresh-btn:active:not(:disabled) {
  transform: translateY(0);
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.app-main {
  flex: 1;
  padding: 2rem;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.error-message {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 0.75rem;
  padding: 1.5rem;
  text-align: center;
  color: #fca5a5;
}

.retry-btn {
  margin-top: 1rem;
  background: #ef4444;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  cursor: pointer;
  font-weight: 500;
  transition: background 0.2s ease;
}

.retry-btn:hover {
  background: #dc2626;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  flex: 1;
  color: #94a3b8;
}

.spinner {
  width: 48px;
  height: 48px;
  border: 4px solid rgba(148, 163, 184, 0.2);
  border-top-color: #fbbf24;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.chart-wrapper {
  flex: 1;
  background: #1a2332;
  border-radius: 1rem;
  overflow: hidden;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(148, 163, 184, 0.22);
  display: flex;
  min-height: 0;
}

.chart-container {
  width: 100%;
  height: 100%;
  min-height: 600px;
}

/* Responsive design */
@media (max-width: 768px) {
  .app-header {
    padding: 1rem;
    flex-direction: column;
    gap: 1rem;
    align-items: flex-start;
  }

  .app-title {
    font-size: 1.5rem;
  }

  .app-main {
    padding: 1rem;
  }

  .chart-container {
    min-height: 400px;
  }
}

/* Smooth transitions */
.chart-wrapper {
  transition: box-shadow 0.3s ease;
}

.chart-wrapper:hover {
  box-shadow: 0 25px 30px -5px rgba(0, 0, 0, 0.4), 0 15px 15px -5px rgba(0, 0, 0, 0.3);
}
</style>
