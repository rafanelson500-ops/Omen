import { ColorType, CrosshairMode } from "lightweight-charts"

export const chartTheme = {
    bg: '#1a2332',
    text: '#e2e8f0',
    muted: '#94a3b8',
    border: 'rgba(148, 163, 184, 0.22)',
    up: '#22c55e',
    down: '#ef4444',
    accent: '#fbbf24',
  }

export const candlestickSeriesOptions = {
  upColor: chartTheme.up,
  downColor: chartTheme.down,
  borderUpColor: chartTheme.up,
  borderDownColor: chartTheme.down,
  wickUpColor: chartTheme.up,
  wickDownColor: chartTheme.down,
}

export const chartOptions = {
  layout: {
    textColor: chartTheme.text,
    background: { type: ColorType.Solid, color: chartTheme.bg },
    fontFamily: '"Outfit", system-ui, sans-serif',
    fontSize: 11,
  },
  grid: {
    vertLines: { color: chartTheme.border },
    horzLines: { color: chartTheme.border },
  },
  crosshair: {
    vertLine: { color: 'rgba(241, 245, 249, 0.35)', labelBackgroundColor: '#0f172a' },
    horzLine: { color: 'rgba(241, 245, 249, 0.35)', labelBackgroundColor: '#0f172a' },
    mode: CrosshairMode.Magnet,
  },
  rightPriceScale: {
    borderColor: chartTheme.border,
    scaleMargins: { top: 0.08, bottom: 0.08 },
  },
  timeScale: {
    timeVisible: true,
    secondsVisible: true,
    borderColor: chartTheme.border,
  },
}

/** Slightly tighter for the secondary candle row */
export const compactChartOptions = {
  ...chartOptions,
  layout: {
    ...chartOptions.layout,
    fontSize: 10,
  },
  rightPriceScale: {
    ...chartOptions.rightPriceScale,
    scaleMargins: { top: 0.1, bottom: 0.1 },
  },
}