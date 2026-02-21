<script setup lang="ts">
import { ref } from 'vue'

const chartContainer = ref<HTMLElement | null>(null)

defineProps<{
  loadingBacktest: boolean
}>()

defineExpose({
  chartContainer
})
</script>

<template>
  <section class="backtest-section">
    <div class="backtest-header">
      <h2 class="backtest-title">Backtest</h2>
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
}

.backtest-title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
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
