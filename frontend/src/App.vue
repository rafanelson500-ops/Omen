<script setup lang="ts">
import { onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { io, Socket } from 'socket.io-client'
import Chart from './Chart.vue'

let url = 'http://localhost:8000'
if (window.location.hostname === 'play.nukesmp.com') {
  url = 'http://play.nukesmp.com:8000'
}

const socket = shallowRef<Socket | null>(null)
const connected = ref(false)

const backtest = () => {
  const d = prompt("enter date")
  socket.value?.emit('backtest', d)
}

onMounted(() => {
  const s = io(url)
  socket.value = s
  s.on('connect', () => {
    connected.value = true
  })
  s.on('disconnect', () => {
    connected.value = false
  })
})

onUnmounted(() => {
  socket.value?.disconnect()
})
</script>

<template>
  <div class="app">
    <button @click="backtest">Backtest</button>
    <Chart class="tick-chart" v-if="socket" :socket="socket" endpoint="tick" seriesType="line" />
  </div>
</template>

<style>
.tick-chart {
  width: 50vw;
  height: 50vh;
}
</style>
