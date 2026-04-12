<script setup lang="ts">
import { useBackend } from './useBackend'

const { socket, subscribe } = useBackend("http://192.168.1.149:8000")

subscribe("chart", (data) => {
  console.log(data)
})
</script>

<template>
  <h1>KBit Live Trading</h1>
</template>

<style scoped></style>
