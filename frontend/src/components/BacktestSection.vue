<script setup lang="ts">
import { ref } from 'vue'

const chartContainer = ref<HTMLElement | null>(null)

defineProps<{
  loadingBacktest: boolean
  dataLength: number
  selectMode: 'none' | 'start' | 'end'
  rangeStartLabel: string
  rangeEndLabel: string
}>()

const emit = defineEmits<{
  (e: 'load'): void
  (e: 'startSelect'): void
  (e: 'reset'): void
}>()

defineExpose({
  chartContainer
})
</script>

<template>
  <section class="backtest-section">
    <div class="backtest-header">
      <h2 class="backtest-title">Backtest</h2>
      <div class="range-controls" v-if="dataLength > 0">
        <button
          class="range-button select-button"
          :class="{ active: selectMode !== 'none' }"
          @click="emit('startSelect')"
        >
          <template v-if="selectMode === 'none'">
            &#9986; Slice
          </template>
          <template v-else-if="selectMode === 'start'">
            Click start&hellip;
          </template>
          <template v-else>
            Click end&hellip;
          </template>
        </button>
        <span class="range-badge" v-if="rangeStartLabel">
          {{ rangeStartLabel }} &rarr; {{ rangeEndLabel || '…' }}
        </span>
        <button class="range-button reset-button" @click="emit('reset')">Reset</button>
      </div>
      <button 
        class="load-button"
        :disabled="loadingBacktest"
        @click="$emit('load')"
      >
        {{ loadingBacktest ? 'Loading...' : 'Load Backtest' }}
      </button>
    </div>
    <div ref="chartContainer" class="chart" :class="{ 'chart-selecting': selectMode !== 'none' }" />
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

.range-button {
  padding: 0.3rem 0.6rem;
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}

.range-button:hover {
  background: var(--bg);
}

.select-button.active {
  color: var(--accent, #fbbf24);
  border-color: var(--accent, #fbbf24);
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.range-badge {
  font-size: 0.75rem;
  color: var(--muted);
  padding: 0.2rem 0.5rem;
  background: var(--bg);
  border-radius: 4px;
  white-space: nowrap;
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

.chart-selecting {
  cursor: crosshair;
}
</style>
