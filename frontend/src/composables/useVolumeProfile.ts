import { PRICE_SCALE, type RawCandle } from './useChart'

// Accumulated volume profile: raw price int -> [buy_vol, sell_vol]
type ProfileMap = Map<number, [number, number]>

export const useVolumeProfile = () => {
  const profileMap: ProfileMap = new Map()

  // Accumulate price_levels from a finalized candle
  const addCandle = (candle: RawCandle) => {
    for (const [priceStr, [buy, sell]] of Object.entries(candle.price_levels)) {
      const price = Number(priceStr)
      const existing = profileMap.get(price) ?? [0, 0]
      profileMap.set(price, [existing[0] + buy, existing[1] + sell])
    }
  }

  /**
   * Render the volume profile onto a canvas element.
   *
   * @param canvas        - The overlay canvas (sized to the chart container)
   * @param priceToCoord  - Converts a dollar price to a logical-px y-coordinate
   * @param rightOffset   - Width of the price scale (px); bars are drawn to the left of it
   */
  const draw = (
    canvas: HTMLCanvasElement,
    priceToCoord: (price: number) => number | null,
    rightOffset: number,
  ) => {
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    const logicalW = canvas.width / dpr
    const logicalH = canvas.height / dpr

    ctx.clearRect(0, 0, canvas.width, canvas.height)

    const entries = Array.from(profileMap.entries())
    if (entries.length === 0) return

    const maxVol = Math.max(...entries.map(([, [b, s]]) => b + s))
    if (maxVol === 0) return

    // Scale context to logical pixels
    ctx.save()
    ctx.scale(dpr, dpr)

    // Max bar width: smaller of 100px or 12% of chart width
    const maxBarWidth = Math.min(100, logicalW * 0.12)
    // Right edge = chart right minus the price scale
    const rightEdge = logicalW - rightOffset

    // Estimate bar height from the spacing between adjacent price ticks
    const sortedPrices = entries.map(([p]) => p).sort((a, b) => a - b)
    let tickH = 3
    if (sortedPrices.length >= 2) {
      const y0 = priceToCoord(sortedPrices[0] / PRICE_SCALE)
      const y1 = priceToCoord(sortedPrices[1] / PRICE_SCALE)
      if (y0 !== null && y1 !== null) {
        tickH = Math.max(1, Math.abs(y1 - y0) - 1)
      }
    }

    for (const [rawPrice, [buyVol, sellVol]] of entries) {
      const y = priceToCoord(rawPrice / PRICE_SCALE)
      if (y === null || y < 0 || y > logicalH) continue

      const totalVol = buyVol + sellVol
      const totalW = (totalVol / maxVol) * maxBarWidth
      const buyW = totalVol > 0 ? (buyVol / totalVol) * totalW : 0
      const sellW = totalW - buyW
      const yTop = y - tickH / 2

      // Sell volume — red, left portion
      if (sellW > 0) {
        ctx.fillStyle = 'rgba(239, 68, 68, 0.55)'
        ctx.fillRect(rightEdge - totalW, yTop, sellW, tickH)
      }

      // Buy volume — green, right portion (closer to price scale)
      if (buyW > 0) {
        ctx.fillStyle = 'rgba(34, 197, 94, 0.55)'
        ctx.fillRect(rightEdge - buyW, yTop, buyW, tickH)
      }
    }

    ctx.restore()
  }

  return { addCandle, draw }
}
