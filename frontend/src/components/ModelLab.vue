<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useBackend } from '../composables/useBackend'
import { createChart } from 'lightweight-charts'
import type { IChartApi } from 'lightweight-charts'
import { chartOptions } from '../styles/chartOptions.ts'
import { useChartUtils } from '../composables/useChartUtils.ts'
import { CandlestickSeries, LineSeries, type ISeriesApi } from 'lightweight-charts'

const { request, socket } = useBackend()
const { registerChart, addSeries, clearChart, cleanSeries } = useChartUtils()

const chartRef = ref<HTMLElement | null>(null)
const chart = ref<IChartApi | null>(null)
const allFeatures = ref<string[]>([])
const hmmFeatures = ref<string[]>([])
const hmmStates = ref<number>(2)
const gbtFeatures = ref<string[]>([])
const gbtTargetOptions = ref<string[]>(["Volatility Weighted Reversion Return"])
const gbtTarget = ref<string>('Volatility Weighted Reversion Return')
const gbtTargetHorizon = ref<number>(2)
const trainingHMM = ref<boolean>(false)
const trainingGBT = ref<boolean>(false)
const loadingData = ref<boolean>(false)
const latestData = ref<any[]>([])
const addedFeatures = ref<Record<string, ISeriesApi<any>>>({})

const loadData = async (type: 'live' | 'cache') => {
    loadingData.value = true
    clearChart(0)
    addedFeatures.value = {}
    const response = await request('load_data', type, 120000)
    latestData.value = response as any[]
    allFeatures.value = Object.keys((response as any[])[0])
    addSeries(0, CandlestickSeries, cleanSeries(response as any[], {
        time: ['time', 1/1000],
        open: ['open', 1],
        high: ['high', 1],
        low: ['low', 1],
        close: ['close', 1],
        volume: ['volume', 1],
    }))
    loadingData.value = false
}

const trainHMM = async () => {
    if (hmmFeatures.value.length === 0) {
      alert('Please select at least one feature')
      return
    }
    trainingHMM.value = true
    const response = await request('train_hmm', { features: hmmFeatures.value, states: hmmStates.value })
    latestData.value = response as any[]
    clearChart(0)
    addedFeatures.value = {}
    allFeatures.value = Object.keys((response as any[])[0])
    addSeries(0, CandlestickSeries, cleanSeries(response as any[], {
        time: ['time', 1/1000],
        open: ['open', 1],
        high: ['high', 1],
        low: ['low', 1],
        close: ['close', 1],
        volume: ['volume', 1],
    }))
    trainingHMM.value = false
}

const trainGBT = async () => {
    if (gbtFeatures.value.length === 0) {
      alert('Please select at least one feature')
      return
    }
    trainingGBT.value = true
    console.log('Training GBT...')
    await new Promise(resolve => setTimeout(resolve, 1000))
    trainingGBT.value = false
}

const addFeatureSeries = (name: string) => {
  const pane = prompt('Enter the pane number to add the series to:')
  if (!pane || addedFeatures.value[name]) return
  try {
    const cleanedSeries = cleanSeries(latestData.value, {
      time: ['time', 1/1000],
      value: [name, 1],
    })
    console.log(cleanedSeries)
    const series = addSeries(0, LineSeries, cleanedSeries, parseInt(pane))
    if (!series) return
    addedFeatures.value[name] = series
  } catch (error) {
    alert('Error adding feature series: ' + error)
  }
}

const removeFeatureSeries = (name: string) => {
  if (!addedFeatures.value[name]) return
  chart.value?.removeSeries(addedFeatures.value[name])
  delete addedFeatures.value[name]
}

const toggleHmmFeature = (feat: string, checked: boolean) => {
  hmmFeatures.value = checked
    ? [...hmmFeatures.value, feat]
    : hmmFeatures.value.filter(f => f !== feat)
}

const toggleGbtFeature = (feat: string, checked: boolean) => {
  gbtFeatures.value = checked
    ? [...gbtFeatures.value, feat]
    : gbtFeatures.value.filter(f => f !== feat)
}

onMounted(() => {
  if (!chartRef.value) return
  chart.value = createChart(chartRef.value, chartOptions)
  registerChart(chart.value, 0)
})
</script>

<style module src="../styles/ModelLab.module.css"></style>

<template>
  <div :class="$style.panel">

    <!-- ── Panel header ── -->
    <div :class="$style.panelHeader">
      <span :class="$style.panelIcon">🧪</span>
      <span :class="$style.panelTitle">Model Lab</span>
    </div>

    <div :class="$style.container">

      <!-- ── Chart section ── -->
      <div :class="$style.sectionCard">
        <div :class="$style.sectionHeader">
          <span :class="$style.sectionTitle">Data</span>
        </div>
        <div :class="$style.sectionBody">
          <div :class="$style.chartFeaturesRow">
            <div :class="$style.chartContainer" ref="chartRef" />
            <div :class="$style.featureBlock">
              <div :class="$style.featureBlockHeader">
                <span :class="$style.featureBlockTitle">Features</span>
                <span :class="$style.featureCount">{{ allFeatures.length }}</span>
              </div>
              <div v-if="allFeatures.length === 0" :class="$style.featureEmpty">
                Load data to populate features
              </div>
              <div v-else :class="$style.featureList">
                <div v-for="feat in allFeatures" :key="feat" :class="$style.featureRow">
                  <span :class="$style.featureLabel">{{ feat }}</span>
                  <div :class="$style.featureActions">
                    <button :class="$style.featureBtn" @click="addFeatureSeries(feat)" title="Add to chart">📊</button>
                    <button :class="$style.featureBtn" @click="removeFeatureSeries(feat)" title="Remove from chart">❌</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div :class="$style.buttonGroup">
            <button :class="$style.actionBtn" :disabled="loadingData" @click="loadData('live')">
              <span v-if="loadingData" :class="$style.spinner" />
              📂 Load Data
            </button>
            <button :class="$style.actionBtn" :disabled="loadingData" @click="loadData('cache')">
              <span v-if="loadingData" :class="$style.spinner" />
              📂 Load Cached Data
            </button>
            <button :class="$style.actionBtn" :disabled="loadingData" @click="socket.emit('save_cache')">
              <span v-if="loadingData" :class="$style.spinner" />
              📂 Save Cached Data
            </button>
          </div>
        </div>
      </div>

      <!-- ── Model cards row ── -->
      <div :class="$style.modelsRow">

        <!-- HMM -->
        <div :class="$style.sectionCard">
          <div :class="$style.sectionHeader">
            <span :class="$style.sectionTitle">Hidden Markov Model</span>
            <span :class="$style.sectionBadge">HMM</span>
          </div>
          <div :class="$style.sectionBody">
            <div :class="$style.featuresControlsRow">
              <!-- Feature selection -->
              <div :class="$style.featureBlock">
                <div :class="$style.featureBlockHeader">
                  <span :class="$style.featureBlockTitle">Features</span>
                  <span :class="$style.featureCount">{{ hmmFeatures.length }} / {{ allFeatures.length }}</span>
                </div>
                <div v-if="allFeatures.length === 0" :class="$style.featureEmpty">
                  Load data to populate features
                </div>
                <div v-else :class="$style.featureGrid">
                  <label
                    v-for="feat in allFeatures"
                    :key="feat"
                    :class="[$style.featureItem, hmmFeatures.includes(feat) && $style.featureItemChecked]"
                  >
                    <input
                      type="checkbox"
                      :class="$style.featureCheckbox"
                      :value="feat"
                      :checked="hmmFeatures.includes(feat)"
                      @change="(e) => toggleHmmFeature(feat, (e.target as HTMLInputElement).checked)"
                    />
                    <span :class="$style.featureLabel">{{ feat }}</span>
                  </label>
                </div>
              </div>

              <!-- Controls column -->
              <div :class="$style.controlsColumn">
                <!-- States slider -->
                <div :class="$style.controlRow">
                  <div :class="$style.controlMeta">
                    <span :class="$style.controlLabel">States</span>
                    <span :class="$style.controlValue">{{ hmmStates }}</span>
                  </div>
                  <input
                    type="range"
                    :class="$style.slider"
                    min="2" max="4" step="1"
                    v-model.number="hmmStates"
                  />
                  <div :class="$style.sliderTicks">
                    <span>2</span><span>4</span>
                  </div>
                </div>
              </div>
            </div>

            <div :class="$style.buttonGroup">
              <button
                :class="[$style.actionBtn, $style.actionBtnPrimary]"
                :disabled="trainingHMM"
                @click="trainHMM"
              >
                <span v-if="trainingHMM" :class="$style.spinner" />
                <span>{{ trainingHMM ? 'Training…' : 'Train HMM' }}</span>
              </button>
              <button
                :class="[$style.actionBtn, $style.actionBtnPrimary]"
                @click="socket.emit('save_hmm')"
              >
                Save HMM
              </button>
            </div>
          </div>
        </div>

        <!-- GBT -->
        <div :class="$style.sectionCard">
          <div :class="$style.sectionHeader">
            <span :class="$style.sectionTitle">Gradient-Boosted Tree</span>
            <span :class="$style.sectionBadge">GBT</span>
          </div>
          <div :class="$style.sectionBody">
            <div :class="$style.featuresControlsRow">
              <!-- Feature selection -->
              <div :class="$style.featureBlock">
                <div :class="$style.featureBlockHeader">
                  <span :class="$style.featureBlockTitle">Features</span>
                  <span :class="$style.featureCount">{{ gbtFeatures.length }} / {{ allFeatures.length }}</span>
                </div>
                <div v-if="allFeatures.length === 0" :class="$style.featureEmpty">
                  Load data to populate features
                </div>
                <div v-else :class="$style.featureGrid">
                  <label
                    v-for="feat in allFeatures"
                    :key="feat"
                    :class="[$style.featureItem, gbtFeatures.includes(feat) && $style.featureItemChecked]"
                  >
                    <input
                      type="checkbox"
                      :class="$style.featureCheckbox"
                      :value="feat"
                      :checked="gbtFeatures.includes(feat)"
                      @change="(e) => toggleGbtFeature(feat, (e.target as HTMLInputElement).checked)"
                    />
                    <span :class="$style.featureLabel">{{ feat }}</span>
                  </label>
                </div>
              </div>

              <!-- Controls column -->
              <div :class="$style.controlsColumn">
                <!-- Target dropdown -->
                <div :class="$style.controlRow">
                  <div :class="$style.controlMeta">
                    <span :class="$style.controlLabel">Target</span>
                  </div>
                  <select :class="$style.select" v-model="gbtTarget">
                    <option value="" disabled>Select a target…</option>
                    <option v-for="opt in gbtTargetOptions" :key="opt" :value="opt">{{ opt }}</option>
                  </select>
                </div>

                <!-- Horizon slider -->
                <div :class="$style.controlRow">
                  <div :class="$style.controlMeta">
                    <span :class="$style.controlLabel">Target Horizon</span>
                    <span :class="$style.controlValue">{{ gbtTargetHorizon }} bar{{ gbtTargetHorizon === 1 ? '' : 's' }}</span>
                  </div>
                  <input
                    type="range"
                    :class="$style.slider"
                    min="2" max="36" step="1"
                    v-model.number="gbtTargetHorizon"
                  />
                  <div :class="$style.sliderTicks">
                    <span>2</span><span>36</span>
                  </div>
                </div>
              </div>
            </div>

            <button
              :class="[$style.actionBtn, $style.actionBtnPrimary]"
              :disabled="trainingGBT"
              @click="trainGBT"
            >
              <span v-if="trainingGBT" :class="$style.spinner" />
              <span>{{ trainingGBT ? 'Training…' : 'Train GBT' }}</span>
            </button>
          </div>
        </div>

      </div><!-- /modelsRow -->

    </div><!-- /container -->
  </div><!-- /panel -->
</template>