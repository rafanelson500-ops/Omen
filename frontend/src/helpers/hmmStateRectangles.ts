import type { ISeriesApi } from 'lightweight-charts'
import type { Time } from 'lightweight-charts'
import { SimpleRectangle, type Point } from './simpleRectangle'

export interface HmmStateRegion {
  startTime: Time
  endTime: Time
  state: number
}

// State colors (3 states: 0, 1, 2) - hex colors without #
const DEFAULT_STATE_COLORS: Record<number, string> = {
  0: 'C9B718',   // State 0: Blue
  1: 'AB18C9',    // State 1: Red
  2: 'C9B718',    // State 2: Green
}

// Pre-computed color cache to avoid repeated parsing
const colorCache = new Map<string, { r: number; g: number; b: number }>()

/**
 * Converts hex color to rgba string (with caching)
 */
function hexToRgba(hex: string, alpha: number): string {
  // Remove # if present
  hex = hex.replace('#', '')
  
  // Check cache first
  let rgb = colorCache.get(hex)
  if (!rgb) {
    rgb = {
      r: parseInt(hex.substring(0, 2), 16),
      g: parseInt(hex.substring(2, 4), 16),
      b: parseInt(hex.substring(4, 6), 16),
    }
    colorCache.set(hex, rgb)
  }
  
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`
}

/**
 * Converts chart data with hmm_state into regions
 */
export function extractHmmStateRegions(
  data: Array<{ time: number; hmm_state: number }>
): HmmStateRegion[] {
  if (!data || data.length === 0 || !data[0] || data[0].hmm_state === undefined) {
    return []
  }

  const regions: HmmStateRegion[] = []
  const firstItem = data[0]
  if (!firstItem || firstItem.hmm_state === undefined) return []
  
  let currentState = firstItem.hmm_state
  let regionStart = 0

  for (let i = 1; i < data.length; i++) {
    const item = data[i]
    if (!item) continue
    const state = item.hmm_state
    if (state !== currentState) {
      // State changed, create region for previous state
      if (i > regionStart) {
        const startItem = data[regionStart]
        const endItem = data[i - 1]
        if (startItem && endItem) {
          regions.push({
            startTime: (startItem.time / 1000) as Time,
            endTime: (endItem.time / 1000) as Time,
            state: currentState,
          })
        }
      }
      currentState = state
      regionStart = i
    }
  }

  // Add final region
  if (regionStart < data.length) {
    const startItem = data[regionStart]
    const endItem = data[data.length - 1]
    if (startItem && endItem) {
      regions.push({
        startTime: (startItem.time / 1000) as Time,
        endTime: (endItem.time / 1000) as Time,
        state: currentState,
      })
    }
  }

  return regions
}

/**
 * Calculates the price range from chart data in a single pass (more efficient)
 */
function getPriceRange(data: Array<{ low?: number; high?: number }>): { min: number; max: number } {
  if (data.length === 0) {
    return { min: 0, max: 100 }
  }
  
  let minPrice = Infinity
  let maxPrice = -Infinity
  
  // Single pass through data - more efficient than flatMap + reduce
  for (let i = 0; i < data.length; i++) {
    const item = data[i]
    if (item?.low !== undefined) {
      minPrice = Math.min(minPrice, item.low)
      maxPrice = Math.max(maxPrice, item.low)
    }
    if (item?.high !== undefined) {
      minPrice = Math.min(minPrice, item.high)
      maxPrice = Math.max(maxPrice, item.high)
    }
  }
  
  if (minPrice === Infinity || maxPrice === -Infinity) {
    return { min: 0, max: 100 }
  }
  
  const priceRange = maxPrice - minPrice
  const padding = priceRange * 0.1 // 10% padding
  
  return {
    min: minPrice - padding,
    max: maxPrice + padding,
  }
}

/**
 * Adds HMM state rectangles to a chart using a simplified rectangle primitive
 * Optimized for performance - only renders pane view, no axis views
 */
export function addHmmStateRectangles(
  priceSeries: ISeriesApi<'Candlestick'>,
  data: Array<{ time: number; hmm_state: number; low?: number; high?: number }>,
  customColors?: Record<number, string>
): SimpleRectangle[] {
  if (!data || data.length === 0) {
    return []
  }

  const stateColors = customColors || DEFAULT_STATE_COLORS
  const { min: bottomPrice, max: topPrice } = getPriceRange(data)
  
  // Pre-compute color strings for each state to avoid repeated conversions
  const stateColorCache = new Map<number, string>()
  
  const getColorForState = (state: number): string => {
    let fillColor = stateColorCache.get(state)
    if (!fillColor) {
      const colorHex = stateColors[state] || '808080'
      fillColor = hexToRgba(colorHex, 0.2) // 20% opacity
      stateColorCache.set(state, fillColor)
    }
    return fillColor
  }
  
  const regions = extractHmmStateRegions(data)
  if (regions.length === 0) {
    return []
  }
  
  const rectangles: SimpleRectangle[] = []
  rectangles.length = regions.length // Pre-allocate array size

  // Use for loop instead of forEach for better performance
  for (let i = 0; i < regions.length; i++) {
    const region = regions[i]!
    const fillColor = getColorForState(region.state)
    
    // Create points for the rectangle
    const p1: Point = {
      time: region.startTime,
      price: topPrice,
    }
    
    const p2: Point = {
      time: region.endTime,
      price: bottomPrice,
    }
    
    // Create and attach simplified rectangle (no axis views = better performance)
    const rectangle = new SimpleRectangle(p1, p2, fillColor)
    priceSeries.attachPrimitive(rectangle)
    
    rectangles[i] = rectangle
  }

  return rectangles
}
