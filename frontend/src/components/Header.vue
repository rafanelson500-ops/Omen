<script setup lang="ts">
import { useBackend } from '../composables/useBackend'

const { connectionStatus } = useBackend()
</script>

<template>
  <header :class="$style.header">
    <div :class="$style.logo">
      <span :class="$style.logoIcon">🧀</span>
      <span :class="$style.logoText">Cheese Trading</span>
    </div>

    <div :class="$style.statusBadge">
      <span :class="connectionStatus ? $style.dotConnected : $style.dotDisconnected" />
      <span :class="connectionStatus ? $style.statusTextConnected : $style.statusTextDisconnected">
        {{ connectionStatus ? 'Connected' : 'Disconnected' }}
      </span>
    </div>
  </header>
  <div :class="$style.headerSpacer" />
</template>

<style module src="../styles/Header.module.css" />
