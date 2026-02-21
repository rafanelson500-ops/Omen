<script setup lang="ts">
defineProps<{
  logs: Array<{ timestamp: string; message: string }>
  loadingLogs: boolean
}>()

defineEmits<{
  refresh: []
}>()
</script>

<template>
  <section class="logs-section">
    <div class="logs-header">
      <h2 class="logs-title">Logs</h2>
      <button 
        type="button" 
        class="refresh-logs" 
        @click="$emit('refresh')"
        :disabled="loadingLogs"
      >
        {{ loadingLogs ? "Loading..." : "Refresh" }}
      </button>
    </div>
    <div class="logs-container">
      <div v-if="logs.length === 0 && !loadingLogs" class="logs-empty">
        No logs available
      </div>
      <div v-else class="logs-list">
        <div 
          v-for="(log, index) in logs" 
          :key="index" 
          class="log-entry"
        >
          <span class="log-timestamp">{{ log.timestamp }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
@import '../styles/variables.css';

.logs-section {
  flex-shrink: 0;
  width: 320px;
  min-width: 320px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.logs-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border);
}

.logs-title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
}

.refresh-logs {
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}

.refresh-logs:hover:not(:disabled) {
  background: var(--surface-hover);
  border-color: rgba(148, 163, 184, 0.3);
}

.refresh-logs:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.logs-container {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0.5rem;
}

.logs-container::-webkit-scrollbar {
  width: 8px;
}

.logs-container::-webkit-scrollbar-track {
  background: var(--bg);
}

.logs-container::-webkit-scrollbar-thumb {
  background: var(--surface-hover);
  border-radius: 4px;
}

.logs-container::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.3);
}

.logs-empty {
  padding: 2rem 1rem;
  text-align: center;
  color: var(--muted);
  font-size: 0.875rem;
}

.logs-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.log-entry {
  padding: 0.625rem 0.75rem;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.8125rem;
  line-height: 1.5;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  transition: border-color 0.2s;
}

.log-entry:hover {
  border-color: rgba(148, 163, 184, 0.3);
}

.log-timestamp {
  font-family: "JetBrains Mono", monospace;
  font-size: 0.75rem;
  color: var(--muted);
}

.log-message {
  color: var(--text);
  word-break: break-word;
}
</style>
