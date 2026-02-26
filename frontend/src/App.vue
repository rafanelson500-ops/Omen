<script setup lang="ts">
import CandleChart from './components/CandleChart.vue'
import styles from './App.module.css'

let BACKEND_URL = import.meta.env.VITE_API_URL
if (window.location.hostname === '192.168.1.149') {
  BACKEND_URL = 'http://192.168.1.149:8000'
}
</script>

<template>
  <div :class="styles.layout">
    <CandleChart :backend-url="BACKEND_URL" :class="styles.mainChart" />
  </div>
</template>
