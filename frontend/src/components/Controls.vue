<script setup lang="ts">
const sessionOptions = [
  { value: "ETH" as const, label: "ETH" },
  { value: "RTH" as const, label: "RTH" },
  { value: "ALL" as const, label: "ALL" },
]

defineProps<{
  session: "ETH" | "RTH" | "ALL"
  lotsSize: number
  confidenceThreshold: number
  paper: boolean
}>()

defineEmits<{
  'update:session': [value: "ETH" | "RTH" | "ALL"]
  'update:lotsSize': [value: number]
  'update:confidenceThreshold': [value: number]
  'update:paper': [value: boolean]
  'session-change': []
  'lots-size-change': []
  'confidence-threshold-change': []
  'paper-change': []
}>()
</script>

<template>
  <aside class="controls">
    <h2 class="controls-title">Trading Settings</h2>

    <div class="field">
      <label class="label">Trading session</label>
      <select 
        :value="session" 
        class="select" 
        @change="$emit('update:session', ($event.target as HTMLSelectElement).value as 'ETH' | 'RTH' | 'ALL'); $emit('session-change')"
      >
        <option
          v-for="opt in sessionOptions"
          :key="opt.value"
          :value="opt.value"
        >
          {{ opt.label }}
        </option>
      </select>
    </div>

    <div class="field">
      <label class="label">Lots size</label>
      <input
        :value="lotsSize"
        @input="$emit('update:lotsSize', Number(($event.target as HTMLInputElement).value)); $emit('lots-size-change')"
        type="number"
        class="input"
        min="1"
        step="1"
      />
    </div>

    <div class="field">
      <label class="label">Confidence threshold</label>
      <input
        :value="confidenceThreshold"
        @input="$emit('update:confidenceThreshold', Number(($event.target as HTMLInputElement).value)); $emit('confidence-threshold-change')"
        type="number"
        class="input"
        min="0"
        max="1"
        step="0.01"
      />
    </div>

    <div class="field">
      <label class="label">Paper trading</label>
      <select 
        :value="paper ? 'true' : 'false'"
        class="select" 
        @change="$emit('update:paper', ($event.target as HTMLSelectElement).value === 'true'); $emit('paper-change')"
      >
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    </div>
  </aside>
</template>

<style scoped>
@import '../styles/variables.css';

.controls {
  flex-shrink: 0;
  width: 280px;
  min-width: 280px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1.25rem;
  overflow-y: auto;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.controls-title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
}

.controls .field {
  margin: 0;
}

.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.field-row .field {
  min-width: 0;
}

.label {
  display: block;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--muted);
  margin-bottom: 0.4rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.select,
.input {
  width: 100%;
  min-width: 0;
  padding: 0.5rem 0.75rem;
  font-family: "JetBrains Mono", monospace;
  font-size: 0.875rem;
  color: var(--text);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
  box-sizing: border-box;
}

.select:hover,
.input:hover {
  border-color: rgba(148, 163, 184, 0.3);
}

.select:focus,
.input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-dim);
}

.input[type="number"] {
  -moz-appearance: textfield;
  appearance: textfield;
}

.input[type="number"]::-webkit-outer-spin-button,
.input[type="number"]::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
</style>
