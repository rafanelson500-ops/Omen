import { ColorType, CrosshairMode } from "lightweight-charts"

const chartTheme = {
    bg: '#1a2332',
    text: '#e2e8f0',
    muted: '#94a3b8',
    border: 'rgba(148, 163, 184, 0.22)',
    up: '#22c55e',
    down: '#ef4444',
    accent: '#fbbf24',
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
      vertLine: { color: chartTheme.muted, labelBackgroundColor: chartTheme.accent },
      horzLine: { color: chartTheme.muted, labelBackgroundColor: chartTheme.accent },
      mode: CrosshairMode.Normal,
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