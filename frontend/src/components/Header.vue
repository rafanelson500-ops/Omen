<script setup lang="ts">
defineProps<{
  connected: boolean
  botEnabled: boolean
  currentPosition: number
}>()

defineEmits<{
  toggleBot: []
}>()
</script>

<template>
  <header class="header">
    <h1 class="title">
      <span class="title-icon">◈</span>
      Cheese Trading Bot - {{ connected ? "Connected" : "Disconnected" }}
    </h1>
    <div class="header-actions">
      <div class="position-info">
        <span class="status-label">Position</span>
        <span class="position-value" :class="{ positive: currentPosition > 0, negative: currentPosition < 0 }">
          {{ currentPosition }}
        </span>
      </div>
      <span class="status-label">Bot</span>
      <button
        type="button"
        class="toggle"
        :class="{ on: botEnabled }"
        :aria-pressed="botEnabled"
        @click="$emit('toggleBot')"
      >
        <span class="toggle-track">
          <span class="toggle-thumb" />
        </span>
      </button>
      <span class="status-value" :class="{ active: botEnabled }">
        {{ botEnabled ? "ON" : "OFF" }}
      </span>
    </div>
  </header>
</template>

<style scoped>
@import '../styles/variables.css';

.header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}

.title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.title-icon {
  color: var(--accent);
  font-size: 1rem;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}

.toggle {
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
  display: block;
}

.toggle-track {
  display: flex;
  align-items: center;
  width: 2.75rem;
  height: 1.25rem;
  border-radius: 999px;
  background: var(--surface-hover);
  border: 1px solid var(--border);
  transition: background 0.2s, border-color 0.2s;
}

.toggle.on .toggle-track {
  background: var(--on-dim);
  border-color: var(--on);
}

.toggle-thumb {
  width: 1rem;
  height: 1rem;
  border-radius: 50%;
  background: var(--muted);
  margin-left: 0.15rem;
  transition: transform 0.2s, background 0.2s;
}

.toggle.on .toggle-thumb {
  transform: translateX(1.5rem);
  background: var(--on);
}

.status-value {
  font-family: "JetBrains Mono", monospace;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted);
  min-width: 2rem;
}

.status-value.active {
  color: var(--on);
}

.position-info {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.2rem;
  margin-right: 1rem;
}

.position-value {
  font-family: "JetBrains Mono", monospace;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--muted);
}

.position-value.positive {
  color: var(--on);
}

.position-value.negative {
  color: #ef4444;
}
</style>
