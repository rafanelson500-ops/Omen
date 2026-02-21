<script setup lang="ts">
import { ref } from 'vue'

const chartContainer = ref<HTMLElement | null>(null)

defineProps<{
  currentTime: string
}>()

defineExpose({
  chartContainer
})
</script>

<template>
  <section class="chart-section">
    <div class="chart-header">
      <h2 class="chart-title">Chart</h2>
      <span class="chart-hint">{{ currentTime }}</span>
    </div>
    <div ref="chartContainer" class="chart" />
  </section>
</template>

<style scoped>
@import '../styles/variables.css';

.chart-section {
  min-height: 500px;
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
  min-height: 450px;
  width: 100%;
}
</style>
