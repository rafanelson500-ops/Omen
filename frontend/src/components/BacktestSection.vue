<script setup lang="ts">
import { ref, watch } from 'vue'

const chartContainer = ref<HTMLElement | null>(null)

const props = defineProps<{
  loadingBacktest: boolean
  dataLength: number
}>()

const emit = defineEmits<{
  (e: 'load'): void
  (e: 'rangeChange', start: number, end: number): void
  (e: 'reset'): void
}>()

const rangeStart = ref(0)
const rangeEnd = ref(0)

watch(() => props.dataLength, (len) => {
  rangeEnd.value = len
})

const applyRange = () => {
  const s = Math.max(0, Math.min(rangeStart.value, props.dataLength - 1))
  const e = Math.max(s + 1, Math.min(rangeEnd.value, props.dataLength))
  rangeStart.value = s
  rangeEnd.value = e
  emit('rangeChange', s, e)
}

const resetRange = () => {
  rangeStart.value = 0
  rangeEnd.value = props.dataLength
  emit('reset')
}

defineExpose({
  chartContainer
})
</script>

<template>
  <section class="backtest-section">
    <div class="backtest-header">
      <h2 class="backtest-title">Backtest</h2>
      <div class="range-controls" v-if="dataLength > 0">
        <label class="range-label">
          Start
          <input
            type="number"
            class="range-input"
            v-model.number="rangeStart"
            :min="0"
            :max="dataLength - 1"
            @keyup.enter="applyRange"
          />
        </label>
        <label class="range-label">
          End
          <input
            type="number"
            class="range-input"
            v-model.number="rangeEnd"
            :min="1"
            :max="dataLength"
            @keyup.enter="applyRange"
          />
        </label>
        <button class="range-button" @click="applyRange">Apply</button>
        <button class="range-button reset-button" @click="resetRange">Reset</button>
      </div>
      <button 
        class="load-button"
        :disabled="loadingBacktest"
        @click="$emit('load')"
      >
        {{ loadingBacktest ? 'Loading...' : 'Load Backtest' }}
      </button>
    </div>
    <div ref="chartContainer" class="chart" />
  </section>
</template>

<style scoped>
@import '../styles/variables.css';

.backtest-section {
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.backtest-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border);
  gap: 0.75rem;
  flex-wrap: wrap;
}

.backtest-title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
}

.range-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.range-label {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.8rem;
  color: var(--muted);
}

.range-input {
  width: 70px;
  padding: 0.3rem 0.5rem;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.8rem;
  font-family: inherit;
}

.range-input:focus {
  outline: none;
  border-color: var(--accent, #fbbf24);
}

.range-button {
  padding: 0.3rem 0.6rem;
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.range-button:hover {
  background: var(--bg);
}

.reset-button {
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.3);
}

.reset-button:hover {
  background: rgba(239, 68, 68, 0.1);
}

.load-button {
  padding: 0.5rem 1rem;
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s;
}

.load-button:hover:not(:disabled) {
  background: var(--bg);
}

.load-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.chart {
  flex: 1;
  min-height: 500px;
  width: 100%;
}
</style>
