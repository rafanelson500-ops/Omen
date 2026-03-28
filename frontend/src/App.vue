<script setup lang="ts">
import { onMounted, onUnmounted, shallowRef } from 'vue'
import { io, Socket } from 'socket.io-client'
import Chart from './Chart.vue'
import ConfluenceLog from './ConfluenceLog.vue'
import StrategyPanel from './StrategyPanel.vue'

let url = 'http://localhost:8000'
if (window.location.hostname === 'play.nukesmp.com') {
  url = 'http://play.nukesmp.com:8000'
}

const socket = shallowRef<Socket | null>(null)

onMounted(() => {
  socket.value = io(url)
})

onUnmounted(() => {
  socket.value?.disconnect()
})
</script>

<template>
  <div class="app">
    <header class="header">
      <span class="title">Strategy dashboard</span>
      <span class="live-badge">
        <span class="live-dot" />
        LIVE
      </span>
    </header>
    <main class="main">
      <div class="left-panel">
        <div class="panel-label">1-tick · 10-tick · 100-tick</div>
        <div class="chart-wrap">
          <Chart v-if="socket" :socket="socket" />
        </div>
      </div>
      <div class="right-panel">
        <div class="strategy-wrap">
          <StrategyPanel v-if="socket" :socket="socket" />
        </div>
        <div class="log-wrap">
          <ConfluenceLog v-if="socket" :socket="socket" />
        </div>
      </div>
    </main>
  </div>
</template>

<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: #0d1520;
  color: #e2e8f0;
  font-family: 'Outfit', system-ui, sans-serif;
  overflow: hidden;
}
</style>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  width: 100vw;
  height: 100vh;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  height: 42px;
  background: #111d2c;
  border-bottom: 2px solid #2d3f55;
  flex-shrink: 0;
}

.title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.03em;
  color: #f1f5f9;
}

.live-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: #22c55e;
}

.live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 6px #22c55e;
  animation: pulse 1.8s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.main {
  display: grid;
  grid-template-columns: 65fr 35fr;
  flex: 1;
  min-height: 0;
  gap: 8px;
  padding: 8px;
  background: #0d1520;
}

.left-panel {
  display: flex;
  flex-direction: column;
  background: #1a2332;
  min-height: 0;
  border: 1px solid #2d3f55;
  border-radius: 10px;
  overflow: hidden;
}

.right-panel {
  display: flex;
  flex-direction: column;
  background: transparent;
  min-height: 0;
  min-width: 0;
  gap: 8px;
}

.panel-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: #94a3b8;
  text-transform: uppercase;
  padding: 5px 10px 4px;
  background: #111d2c;
  border-bottom: 2px solid #2d3f55;
  flex-shrink: 0;
}

.chart-wrap {
  flex: 1;
  min-height: 0;
  position: relative;
}

.left-panel > .panel-label { flex-shrink: 0; }
.left-panel > .chart-wrap  { flex: 1; }

.tick-wrap {
  min-height: 0;
  overflow: hidden;
}

.strategy-wrap {
  flex: 0.62;
  min-height: 0;
  border: 1px solid #2d3f55;
  border-radius: 10px;
  overflow: hidden;
  background: #101928;
}

.log-wrap {
  flex: 0.38;
  min-height: 0;
  border: 1px solid #2d3f55;
  border-radius: 10px;
  overflow: hidden;
  background: #111d2c;
}

@media (max-width: 1200px) {
  .main {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(0, 1.2fr) minmax(0, 1fr);
  }

  .right-panel {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }

  .strategy-wrap,
  .log-wrap {
    min-height: 280px;
  }
}

@media (max-width: 860px) {
  .header {
    padding: 0 12px;
    height: 40px;
  }

  .title {
    font-size: 13px;
  }

  .main {
    padding: 6px;
    gap: 6px;
  }

  .right-panel {
    grid-template-columns: 1fr;
  }
}
</style>
