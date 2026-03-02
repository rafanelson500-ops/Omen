<script setup lang="ts">
import { useBackend } from '../composables/useBackend'
import { ref } from 'vue'

interface TradeSignal {
  side: 'long' | 'short' | string
  entry_limit: number
  stop_loss: number
  take_profit: number
  size: number
}

interface BackendError {
  kind: 'error'
  message: string
}

type Result = TradeSignal | 'PASS' | BackendError

const { request, agentReports, clearAgentReports } = useBackend()
const loading = ref(false)
const result = ref<Result | null>(null)
const resultTimestamp = ref<string | null>(null)

const runAgenticStrategy = async () => {
  loading.value = true
  result.value = null
  resultTimestamp.value = null
  clearAgentReports()
  try {
    const raw = await request('run_agentic_strategy', null, 300000)
    result.value = parseResult(raw)
    resultTimestamp.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    console.log(result.value)
  } catch (err) {
    const message = err instanceof Error && err.message.toLowerCase().includes('timed out')
      ? 'Request timed out — the agent took too long to respond.'
      : `Unexpected error: ${err instanceof Error ? err.message : String(err)}`
    result.value = { kind: 'error', message }
  } finally {
    loading.value = false
  }
}

const parseResult = (raw: unknown): Result => {
  if (typeof raw !== 'string') return raw as TradeSignal
  const trimmed = raw.trim()
  if (trimmed === 'PASS') return 'PASS'
  if (trimmed.toLowerCase().startsWith('error:')) {
    return { kind: 'error', message: trimmed.slice(trimmed.indexOf(':') + 1).trim() }
  }
  // Convert Python dict string (single-quoted) to valid JSON
  const json = trimmed.replace(/'/g, '"')
  return JSON.parse(json) as TradeSignal
}

const isPass    = (r: Result | null): r is 'PASS'       => r === 'PASS'
const isError   = (r: Result | null): r is BackendError  => typeof r === 'object' && r !== null && 'kind' in r
const isTrade   = (r: Result | null): r is TradeSignal   => r !== null && r !== 'PASS' && !isError(r)
</script>

<template>
  <div :class="$style.panel">

    <!-- ── Panel header ── -->
    <div :class="$style.panelHeader">
      <span :class="$style.panelIcon">🤖</span>
      <span :class="$style.panelTitle">Agentic Strategy</span>
    </div>

    <div :class="$style.container">

    <!-- ── Run button ── -->
    <button
      :class="$style.runBtn"
      :disabled="loading"
      @click="runAgenticStrategy"
    >
      <span v-if="loading" :class="$style.spinner" />
      <span>{{ loading ? 'Analysing…' : 'Run Agentic Strategy' }}</span>
    </button>

    <!-- ── Agent reports feed ── -->
    <div v-if="agentReports.length > 0" :class="$style.reportsFeed">
      <div
        v-for="(item, i) in agentReports"
        :key="i"
        :class="$style.reportCard"
      >
        <div :class="$style.reportHeader">
          <span :class="$style.reportAgent">{{ item.agent }}</span>
          <span :class="$style.reportBadge">Report</span>
        </div>
        <p :class="$style.reportBody">{{ item.report }}</p>
      </div>
    </div>

    <!-- ── Error result ── -->
    <div v-if="isError(result)" :class="$style.errorCard">
      <span :class="$style.errorIcon">⚠️</span>
      <div :class="$style.errorMessage">{{ result.message }}</div>
    </div>

    <!-- ── PASS result ── -->
    <div v-else-if="isPass(result)" :class="$style.passCard">
      <div :class="$style.passLabel">PASS</div>
      <div :class="$style.passSubtext">No trade signal — staying flat.</div>
      <div v-if="resultTimestamp" :class="$style.timestamp">{{ resultTimestamp }}</div>
    </div>

    <!-- ── Trade signal result ── -->
    <div v-else-if="isTrade(result)" :class="$style.tradeCard">
      <div :class="$style.tradeHeader">
        <span :class="$style.tradeTitle">Trade Signal</span>
        <span
          :class="[
            $style.sideBadge,
            result.side.toLowerCase() === 'buy' ? $style.sideLong : $style.sideShort
          ]"
        >
          {{ result.side.toUpperCase() }}
        </span>
      </div>

      <div :class="$style.tradeBody">
        <div :class="$style.tradeRow">
          <span :class="$style.rowLabel">Entry Limit</span>
          <span :class="$style.rowValueAccent">{{ result.entry_limit }}</span>
        </div>
        <div :class="$style.tradeRow">
          <span :class="$style.rowLabel">Stop Loss</span>
          <span :class="$style.rowValueStop">{{ result.stop_loss }}</span>
        </div>
        <div :class="$style.tradeRow">
          <span :class="$style.rowLabel">Take Profit</span>
          <span :class="$style.rowValueTarget">{{ result.take_profit }}</span>
        </div>
        <div :class="$style.tradeRow">
          <span :class="$style.rowLabel">Size</span>
          <span :class="$style.rowValue">{{ result.size }}</span>
        </div>
        <div v-if="resultTimestamp" :class="[$style.tradeRow, $style.timestampRow]">
          <span :class="$style.rowLabel">Generated at</span>
          <span :class="$style.timestamp">{{ resultTimestamp }}</span>
        </div>
      </div>
    </div>

    <!-- ── Idle placeholder ── -->
    <div v-else :class="$style.idle">
      <span :class="$style.idleIcon">📊</span>
      <span :class="$style.idleText">Awaiting analysis</span>
    </div>

    </div><!-- /container -->
  </div><!-- /panel -->
</template>

<style module src="../styles/AgentStrategy.module.css" />
