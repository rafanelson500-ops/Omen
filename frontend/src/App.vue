<script setup lang="ts">
import { useBackend } from './composables/useBackend'
import { onMounted } from 'vue'
import Header from './components/Header.vue'
import AgentStrategy from './components/AgentStrategy.vue'
import ModelLab from './components/ModelLab.vue'

const { connect } = useBackend()

onMounted(() => {
  connect()
})
</script>

<template>
  <Header />
  <AgentStrategy />
  <ModelLab />
</template>
