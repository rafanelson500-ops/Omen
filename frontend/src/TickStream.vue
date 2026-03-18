<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { Socket } from 'socket.io-client'

const props = defineProps<{
  socket: Socket
}>()

interface Tick {
  id: number
  price: string
  side: number
  size: number
}

const ticks = ref<Tick[]>([])
let counter = 0

onMounted(() => {
  props.socket.on('tick', (tick: any) => {
    ticks.value.unshift({
      id: counter++,
      price: (tick.price / 1_000_000_000).toFixed(2),
      side: tick.side,
      size: tick.size,
    })
    if (ticks.value.length > 200) ticks.value.splice(200)
  })
})
</script>

<template>
  <div class="stream">
    <div class="row header-row">
      <span>Side</span>
      <span>Price</span>
      <span class="align-right">Size</span>
    </div>
    <div class="rows">
      <div
        v-for="tick in ticks"
        :key="tick.id"
        class="row"
        :class="tick.side === 1 ? 'buy' : 'sell'"
      >
        <span class="side-label">{{ tick.side === 1 ? 'BUY' : 'SELL' }}</span>
        <span class="price">{{ tick.price }}</span>
        <span class="size align-right">{{ tick.size }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stream {
  display: flex;
  flex-direction: column;
  height: 100%;
  font-size: 11px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  overflow: hidden;
}

.rows {
  overflow-y: auto;
  flex: 1;
}

.rows::-webkit-scrollbar { width: 4px; }
.rows::-webkit-scrollbar-track { background: transparent; }
.rows::-webkit-scrollbar-thumb { background: rgba(148, 163, 184, 0.2); border-radius: 2px; }

.row {
  display: grid;
  grid-template-columns: 44px 1fr 1fr;
  align-items: center;
  padding: 3px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.06);
}

.header-row {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.07em;
  color: #475569;
  text-transform: uppercase;
  background: #111d2c;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  position: sticky;
  top: 0;
}

.buy  { color: #22c55e; }
.sell { color: #ef4444; }

.side-label {
  font-weight: 700;
  font-size: 9px;
  letter-spacing: 0.05em;
}

.price { font-weight: 500; }

.align-right { text-align: right; }

.size {
  color: #94a3b8;
}
</style>
