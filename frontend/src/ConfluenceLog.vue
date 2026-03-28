<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import type { Socket } from 'socket.io-client'

const props = defineProps<{
  socket: Socket
}>()

type ConfluenceEntry = {
  label: string
  time: number
}

const recent = ref<ConfluenceEntry[]>([])
const scrollRef = ref<HTMLElement | null>(null)
/** Keys of rows that just appeared (fade highlight via CSS). */
const newRowKeys = ref<Set<string>>(new Set())

function entryKey(row: ConfluenceEntry, index: number) {
  return `${row.time}|${row.label}|${index}`
}

function stableRowKey(row: ConfluenceEntry) {
  return `${row.time}|${row.label}`
}

function fmtTs(t: number) {
  return new Date(t * 1000).toISOString().replace('T', ' ').slice(0, 23)
}

function onConfluence(payload: { recent: ConfluenceEntry[] }) {
  const prev = recent.value
  const next = payload.recent.slice(-50)
  const prevKeySet = new Set(prev.map((r) => stableRowKey(r)))

  if (prev.length > 0) {
    const added = new Set<string>()
    for (const row of next) {
      const k = stableRowKey(row)
      if (!prevKeySet.has(k)) added.add(k)
    }
    newRowKeys.value = added
  } else {
    newRowKeys.value = new Set()
  }

  recent.value = next
  queueScroll()
}

function rowIsNew(row: ConfluenceEntry) {
  return newRowKeys.value.has(stableRowKey(row))
}

function onNewHighlightEnd(e: AnimationEvent, row: ConfluenceEntry) {
  if (e.animationName !== 'confluence-new-fade') return
  const k = stableRowKey(row)
  if (!newRowKeys.value.has(k)) return
  const next = new Set(newRowKeys.value)
  next.delete(k)
  newRowKeys.value = next
}

let scrollQueued = false
function queueScroll() {
  if (scrollQueued) return
  scrollQueued = true
  requestAnimationFrame(() => {
    scrollQueued = false
    const el = scrollRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function onInstantBacktest(batch: { confluence?: { recent: ConfluenceEntry[] } }) {
  if (batch.confluence) onConfluence(batch.confluence)
}

onMounted(() => {
  props.socket.on('confluence', onConfluence)
  props.socket.on('instant_backtest', onInstantBacktest)
})

onUnmounted(() => {
  props.socket.off('confluence', onConfluence)
  props.socket.off('instant_backtest', onInstantBacktest)
})
</script>

<template>
  <div class="confluence-log">
    <div class="confluence-header">
      <div class="confluence-titles">
        <span class="confluence-title">Confluence log</span>
        <span class="confluence-sub">Microstructure confluences (not trade signals)</span>
      </div>
      <span class="confluence-count">{{ recent.length }} / 50</span>
    </div>
    <div ref="scrollRef" class="confluence-body">
      <div v-if="recent.length === 0" class="empty">No confluences yet…</div>
      <template v-else>
        <div
          v-for="(row, i) in recent"
          :key="entryKey(row, i)"
          class="row"
          :class="{
            'row--plus': row.label.startsWith('+'),
            'row--minus': row.label.startsWith('-'),
            'row--new': rowIsNew(row),
          }"
          @animationend="onNewHighlightEnd($event, row)"
        >
          <span class="ts">{{ fmtTs(row.time) }}</span>
          <span class="label">{{ row.label }}</span>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.confluence-log {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  background: #111d2c;
}

.confluence-header {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px 6px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(15, 23, 42, 0.32);
}

.confluence-titles {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.confluence-title {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: #94a3b8;
  text-transform: uppercase;
}

.confluence-sub {
  font-size: 10px;
  color: #64748b;
  line-height: 1.3;
}

.confluence-count {
  font-size: 10px;
  font-weight: 700;
  color: #64748b;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.confluence-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  font-size: 12px;
  line-height: 1.45;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: #3d5169 #0d1520;
}

.confluence-body::-webkit-scrollbar {
  width: 9px;
}

.confluence-body::-webkit-scrollbar-track {
  background: #0d1520;
  border-radius: 6px;
  margin: 4px 0;
}

.confluence-body::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, #4a6282 0%, #3d5169 100%);
  border-radius: 6px;
  border: 2px solid #0d1520;
  min-height: 40px;
}

.empty {
  color: #64748b;
  padding: 12px;
  font-size: 12px;
}

.row {
  padding: 8px 10px;
  margin-bottom: 6px;
  border-radius: 6px;
  background: #1a2332;
  border: 1px solid #2d3f55;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

@keyframes confluence-new-fade {
  0% {
    background-color: rgba(250, 204, 21, 0.42);
    box-shadow: 0 0 0 1px rgba(250, 204, 21, 0.45), 0 0 18px rgba(250, 204, 21, 0.14);
  }
  100% {
    background-color: #1a2332;
    box-shadow: none;
  }
}

.row--new {
  animation: confluence-new-fade 2.4s ease-out forwards;
}

.row--plus {
  border-left: 3px solid #22c55e;
}

.row--minus {
  border-left: 3px solid #ef4444;
}

.ts {
  font-size: 10px;
  color: #64748b;
  font-variant-numeric: tabular-nums;
}

.label {
  color: #e2e8f0;
  font-weight: 600;
}
</style>
