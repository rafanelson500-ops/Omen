<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { createChart } from 'lightweight-charts'
import { LineSeries, type LineData, type Time } from 'lightweight-charts'
import { chartOptions } from '../chartOptions'

const props = defineProps<{
  apiUrl: string
}>()

const emit = defineEmits<{
  close: []
}>()

const showDialog = ref(false)
const numSimulationsInput = ref('1000')
const loading = ref(false)
const error = ref<string | null>(null)
const results = ref<any>(null)

const equityChartContainer = ref<HTMLDivElement | null>(null)
const returnDistCanvas = ref<HTMLCanvasElement | null>(null)
const drawdownDistCanvas = ref<HTMLCanvasElement | null>(null)
const evDistCanvas = ref<HTMLCanvasElement | null>(null)

let equityChart: ReturnType<typeof createChart> | null = null

const openDialog = () => {
  showDialog.value = true
  numSimulationsInput.value = '1000'
}

const closeDialog = () => {
  showDialog.value = false
  emit('close')
}

const runSimulation = async () => {
  const numSimulations = parseInt(numSimulationsInput.value)
  if (isNaN(numSimulations) || numSimulations < 1 || numSimulations > 10000) {
    error.value = 'Please enter a number between 1 and 10000'
    return
  }
  
  loading.value = true
  error.value = null
  closeDialog()
  
  try {
    const response = await fetch(props.apiUrl + '/monte-carlo', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ num_simulations: numSimulations }),
    })
    
    if (!response.ok) {
      const errorData = await response.json()
      throw new Error(errorData.error || `HTTP error! status: ${response.status}`)
    }
    
    const data = await response.json()
    results.value = data
    
    // Render charts after data is loaded and DOM is ready
    await nextTick()
    setTimeout(() => {
      renderEquityCurves()
      renderDistributionCharts()
    }, 200) // Increased delay to ensure canvas elements are ready
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to run Monte Carlo simulation'
    console.error('Error running Monte Carlo:', err)
  } finally {
    loading.value = false
  }
}

const renderEquityCurves = () => {
  if (!equityChartContainer.value || !results.value) return
  
  if (equityChart) {
    equityChart.remove()
  }
  
  const percentiles = results.value.equity_percentiles
  const timePoints = results.value.time_points
  
  equityChart = createChart(equityChartContainer.value, {
    ...chartOptions,
    width: equityChartContainer.value.clientWidth,
    height: equityChartContainer.value.clientHeight,
    autoSize: true,
  })
  
  const p10Series = equityChart.addSeries(LineSeries, {
    color: '#ef4444',
    lineWidth: 2,
    title: '10th Percentile',
  })
  
  const p50Series = equityChart.addSeries(LineSeries, {
    color: '#fbbf24',
    lineWidth: 2,
    title: '50th Percentile (Median)',
  })
  
  const p90Series = equityChart.addSeries(LineSeries, {
    color: '#22c55e',
    lineWidth: 2,
    title: '90th Percentile',
  })
  
  const baseTime = Date.now() - (timePoints.length * 5 * 60 * 1000)
  const p10Data: LineData<Time>[] = timePoints.map((tradeIdx: number, i: number) => ({
    time: (Math.floor((baseTime + tradeIdx * 5 * 60 * 1000) / 1000)) as Time,
    value: percentiles.p10[i] || 0,
  }))
  
  const p50Data: LineData<Time>[] = timePoints.map((tradeIdx: number, i: number) => ({
    time: (Math.floor((baseTime + tradeIdx * 5 * 60 * 1000) / 1000)) as Time,
    value: percentiles.p50[i] || 0,
  }))
  
  const p90Data: LineData<Time>[] = timePoints.map((tradeIdx: number, i: number) => ({
    time: (Math.floor((baseTime + tradeIdx * 5 * 60 * 1000) / 1000)) as Time,
    value: percentiles.p90[i] || 0,
  }))
  
  p10Series.setData(p10Data)
  p50Series.setData(p50Data)
  p90Series.setData(p90Data)
}

interface BinData {
  count: number
  binStart: number
  binEnd: number
  binCenter: number
}

const createHistogramData = (data: number[], numBins: number = 30): { bins: BinData[], min: number, max: number, binWidth: number, decimals: number } => {
  if (!data || data.length === 0) return { bins: [], min: 0, max: 0, binWidth: 0, decimals: 2 }
  
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min
  if (range === 0) return { bins: [], min, max, binWidth: 0, decimals: 2 }
  
  const binWidth = range / numBins
  
  const bins = new Array(numBins).fill(0)
  data.forEach(value => {
    const binIndex = Math.min(Math.floor((value - min) / binWidth), numBins - 1)
    bins[binIndex]++
  })
  
  // Calculate appropriate decimal places
  const getDecimals = (value: number) => {
    const absValue = Math.abs(value)
    if (absValue >= 1000) return 0
    if (absValue >= 100) return 1
    if (absValue >= 10) return 2
    if (absValue >= 1) return 2
    if (absValue >= 0.1) return 3
    if (absValue >= 0.01) return 4
    return 5
  }
  const decimals = Math.max(getDecimals(min), getDecimals(max))
  
  // Create bin data with ranges
  const binData: BinData[] = []
  for (let i = 0; i < numBins; i++) {
    const binStart = min + (i * binWidth)
    const binEnd = min + ((i + 1) * binWidth)
    const binCenter = (binStart + binEnd) / 2
    binData.push({
      count: bins[i],
      binStart,
      binEnd,
      binCenter,
    })
  }
  
  return { bins: binData, min, max, binWidth, decimals }
}

const tooltip = ref<{ show: boolean, x: number, y: number, text: string }>({ show: false, x: 0, y: 0, text: '' })

const renderHistogram = (canvas: HTMLCanvasElement, data: number[], title: string, color: string) => {
  if (!canvas || !data || data.length === 0) return
  
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  
  // Set canvas size
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width * window.devicePixelRatio
  canvas.height = rect.height * window.devicePixelRatio
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio)
  
  const width = rect.width
  const height = rect.height
  
  // Clear canvas
  ctx.clearRect(0, 0, width, height)
  
  const { bins, min, max, decimals } = createHistogramData(data)
  if (bins.length === 0) return
  
  const maxCount = Math.max(...bins.map(b => b.count))
  if (maxCount === 0) return
  
  // Calculate spacing
  const titleHeight = 30
  const xAxisLabelHeight = 50
  const chartAreaTop = titleHeight
  const chartAreaBottom = height - xAxisLabelHeight
  const chartAreaHeight = chartAreaBottom - chartAreaTop
  
  // Draw title
  ctx.fillStyle = '#e2e8f0'
  ctx.font = '14px "Outfit", system-ui, sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText(title, width / 2, 20)
  
  // Draw histogram bars
  const barWidth = width / bins.length
  const padding = 1
  
  let hoveredBin: BinData | null = null
  
  const redraw = () => {
    // Clear the entire canvas (accounting for device pixel ratio)
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio)
    
    // Redraw title
    ctx.fillStyle = '#e2e8f0'
    ctx.font = '14px "Outfit", system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(title, width / 2, 20)
    
    // Draw bars
    bins.forEach((bin, i) => {
      const barHeight = (bin.count / maxCount) * chartAreaHeight
      const x = i * barWidth + padding
      const y = chartAreaBottom - barHeight
      
      // Highlight hovered bar
      if (hoveredBin === bin) {
        ctx.fillStyle = color
        ctx.globalAlpha = 1.0
      } else {
        ctx.fillStyle = color
        ctx.globalAlpha = 0.6
      }
      
      ctx.fillRect(x, y, barWidth - padding * 2, barHeight)
      
      // Draw border
      ctx.strokeStyle = color
      ctx.lineWidth = 1
      ctx.strokeRect(x, y, barWidth - padding * 2, barHeight)
    })
    
    ctx.globalAlpha = 1.0
    
    // Draw axes
    ctx.strokeStyle = '#94a3b8'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(0, chartAreaBottom)
    ctx.lineTo(width, chartAreaBottom)
    ctx.stroke()
    
    ctx.beginPath()
    ctx.moveTo(0, chartAreaBottom)
    ctx.lineTo(0, chartAreaTop)
    ctx.stroke()
    
    // Draw x-axis labels
    ctx.fillStyle = '#94a3b8'
    ctx.font = '9px "Outfit", system-ui, sans-serif'
    const numLabels = 15
    const labelSpacing = width / (numLabels - 1)
    
    for (let i = 0; i < numLabels; i++) {
      const xPos = i * labelSpacing
      const binIndex = Math.floor((xPos / width) * bins.length)
      if (binIndex >= 0 && binIndex < bins.length) {
        const value = bins[binIndex].binCenter
        
        // Draw tick mark
        ctx.beginPath()
        ctx.moveTo(xPos, chartAreaBottom)
        ctx.lineTo(xPos, chartAreaBottom + 3)
        ctx.stroke()
        
        // Draw rotated label
        ctx.save()
        ctx.translate(xPos, chartAreaBottom + 35)
        ctx.rotate(-Math.PI / 4)
        ctx.textAlign = 'right'
        ctx.textBaseline = 'middle'
        ctx.fillText(value.toFixed(decimals), 0, 0)
        ctx.restore()
      }
    }
  }
  
  const handleMouseMove = (e: MouseEvent) => {
    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    
    if (y >= chartAreaTop && y <= chartAreaBottom && x >= 0 && x <= width) {
      const binIndex = Math.floor(x / barWidth)
      if (binIndex >= 0 && binIndex < bins.length && bins[binIndex].count > 0) {
        hoveredBin = bins[binIndex]
        tooltip.value = {
          show: true,
          x: e.clientX,
          y: e.clientY - 10,
          text: `Simulations: ${hoveredBin.count}\nRange: ${hoveredBin.binStart.toFixed(decimals)} - ${hoveredBin.binEnd.toFixed(decimals)}`
        }
        redraw()
      } else {
        if (tooltip.value.show) {
          tooltip.value.show = false
          hoveredBin = null
          redraw()
        }
      }
    } else {
      if (tooltip.value.show) {
        tooltip.value.show = false
        hoveredBin = null
        redraw()
      }
    }
  }
  
  const handleMouseLeave = () => {
    tooltip.value.show = false
    hoveredBin = null
    redraw()
  }
  
  // Remove old event listeners
  canvas.removeEventListener('mousemove', handleMouseMove as any)
  canvas.removeEventListener('mouseleave', handleMouseLeave)
  
  // Add event listeners
  canvas.addEventListener('mousemove', handleMouseMove as any)
  canvas.addEventListener('mouseleave', handleMouseLeave)
  
  // Initial draw
  redraw()
}

const renderDistributionCharts = () => {
  if (!results.value) return
  
  if (returnDistCanvas.value) {
    renderHistogram(
      returnDistCanvas.value,
      results.value.return_distribution,
      'Return Distribution',
      '#22c55e'
    )
  }
  
  if (drawdownDistCanvas.value) {
    renderHistogram(
      drawdownDistCanvas.value,
      results.value.max_drawdown_distribution,
      'Max Drawdown Distribution',
      '#ef4444'
    )
  }
  
  if (evDistCanvas.value) {
    renderHistogram(
      evDistCanvas.value,
      results.value.expected_value_distribution,
      'Expected Value Distribution',
      '#fbbf24'
    )
  }
}

const resizeHandler = () => {
  if (equityChart && equityChartContainer.value) {
    equityChart.applyOptions({
      width: equityChartContainer.value.clientWidth,
      height: equityChartContainer.value.clientHeight
    })
  }
  // Re-render histograms on resize
  if (results.value) {
    renderDistributionCharts()
  }
}

onMounted(() => {
  window.addEventListener('resize', resizeHandler)
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeHandler)
  if (equityChart) equityChart.remove()
})

defineExpose({
  openDialog,
})
</script>

<template>
  <div>
    <!-- Monte Carlo Results -->
    <div v-if="results && !loading" class="monte-carlo-section">
      <h2 class="section-title">Monte Carlo Simulation Results</h2>
      
      <div v-if="error" class="error-message">
        <p>⚠️ {{ error }}</p>
      </div>
      
      <div class="monte-carlo-charts">
        <!-- Equity Curves -->
        <div class="chart-panel">
          <h3 class="panel-title">Equity Curves (Percentile Bands)</h3>
          <div ref="equityChartContainer" class="equity-chart-container"></div>
        </div>
        
        <!-- Distribution Charts -->
        <div class="distribution-panels">
          <div class="chart-panel">
            <div class="histogram-wrapper">
              <canvas ref="returnDistCanvas" class="histogram-canvas"></canvas>
            </div>
          </div>
          
          <div class="chart-panel">
            <div class="histogram-wrapper">
              <canvas ref="drawdownDistCanvas" class="histogram-canvas"></canvas>
            </div>
          </div>
          
          <div class="chart-panel">
            <div class="histogram-wrapper">
              <canvas ref="evDistCanvas" class="histogram-canvas"></canvas>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Tooltip -->
    <div 
      v-if="tooltip.show" 
      class="histogram-tooltip"
      :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }"
    >
      <div class="tooltip-content">
        <div v-for="(line, i) in tooltip.text.split('\n')" :key="i">{{ line }}</div>
      </div>
    </div>
    
    <!-- Monte Carlo Dialog -->
    <div v-if="showDialog" class="dialog-overlay" @click.self="closeDialog">
      <div class="dialog-content">
        <h2 class="dialog-title">Run Monte Carlo Simulation</h2>
        <p class="dialog-description">Enter the number of simulations to run:</p>
        <input
          v-model="numSimulationsInput"
          type="number"
          min="1"
          max="10000"
          class="dialog-input"
          placeholder="1000"
          @keyup.enter="runSimulation"
        />
        <div class="dialog-actions">
          <button @click="closeDialog" class="dialog-btn dialog-btn-cancel">Cancel</button>
          <button @click="runSimulation" class="dialog-btn dialog-btn-confirm">Run</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.monte-carlo-section {
  margin-top: 2rem;
  padding: 2rem;
  background: rgba(26, 35, 50, 0.5);
  border-radius: 1rem;
  border: 1px solid rgba(148, 163, 184, 0.22);
}

.section-title {
  margin: 0 0 1.5rem 0;
  font-size: 1.5rem;
  font-weight: 600;
  color: #e2e8f0;
}

.monte-carlo-charts {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.chart-panel {
  background: #1a2332;
  border-radius: 0.75rem;
  padding: 1.5rem;
  border: 1px solid rgba(148, 163, 184, 0.22);
}

.panel-title {
  margin: 0 0 1rem 0;
  font-size: 1.1rem;
  font-weight: 500;
  color: #e2e8f0;
}

.equity-chart-container {
  width: 100%;
  height: 400px;
  min-height: 400px;
}

.histogram-wrapper {
  width: 100%;
  height: 300px;
  min-height: 300px;
  position: relative;
}

.histogram-canvas {
  width: 100% !important;
  height: 100% !important;
  background: #0f172a;
  border-radius: 0.5rem;
  cursor: crosshair;
}

.histogram-tooltip {
  position: fixed;
  pointer-events: none;
  z-index: 1000;
  transform: translate(-50%, -100%);
  margin-top: -10px;
}

.tooltip-content {
  background: rgba(26, 35, 50, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 0.5rem;
  padding: 0.5rem 0.75rem;
  color: #e2e8f0;
  font-size: 0.875rem;
  font-family: '"Outfit", system-ui, sans-serif';
  white-space: pre-line;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
}

.distribution-panels {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
}

.error-message {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 0.75rem;
  padding: 1rem;
  margin-bottom: 1rem;
  color: #fca5a5;
}

/* Dialog */
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog-content {
  background: #1a2332;
  border-radius: 1rem;
  padding: 2rem;
  width: 90%;
  max-width: 400px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3);
}

.dialog-title {
  margin: 0 0 1rem 0;
  font-size: 1.5rem;
  font-weight: 600;
  color: #e2e8f0;
}

.dialog-description {
  margin: 0 0 1rem 0;
  color: #94a3b8;
  font-size: 0.875rem;
}

.dialog-input {
  width: 100%;
  padding: 0.75rem;
  background: #0f172a;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 0.5rem;
  color: #e2e8f0;
  font-size: 1rem;
  margin-bottom: 1.5rem;
  box-sizing: border-box;
}

.dialog-input:focus {
  outline: none;
  border-color: #8b5cf6;
  box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.1);
}

.dialog-actions {
  display: flex;
  gap: 1rem;
  justify-content: flex-end;
}

.dialog-btn {
  padding: 0.625rem 1.25rem;
  border: none;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.dialog-btn-cancel {
  background: rgba(148, 163, 184, 0.2);
  color: #e2e8f0;
}

.dialog-btn-cancel:hover {
  background: rgba(148, 163, 184, 0.3);
}

.dialog-btn-confirm {
  background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
  color: white;
  box-shadow: 0 2px 4px rgba(139, 92, 246, 0.3);
}

.dialog-btn-confirm:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(139, 92, 246, 0.4);
}

/* Responsive */
@media (max-width: 768px) {
  .distribution-panels {
    grid-template-columns: 1fr;
  }
  
  .monte-carlo-section {
    padding: 1rem;
  }
  
  .equity-chart-container {
    height: 300px;
    min-height: 300px;
  }
  
  .histogram-container {
    height: 250px;
    min-height: 250px;
  }
}
</style>
