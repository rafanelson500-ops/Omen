import type { IChartApi, ISeriesApi } from "lightweight-charts"
import { ref } from "vue"
import { CandlestickSeries, LineSeries } from "lightweight-charts"

export const useChartUtils = () => {
    const allCharts = ref<Record<number, IChartApi>>({})
    const allSeries = ref<Record<number, ISeriesApi<any>[]>>({})

    const registerChart = (chart: IChartApi, id: number) => {
        allCharts.value[id] = chart
        allSeries.value[id] = []
    }

    const cleanSeries = (data: any[], map: Record<string, [string, number]>) => {
        return data.map((item) => {
            const newItem: Record<string, any> = {}
            for (const new_key of Object.keys(map)) {
                const [src, scale] = map[new_key]!
                newItem[new_key] = item[src as keyof typeof item] * scale
            }
            return newItem
        })
    }

    const addSeries = (chartId: number, seriesType: typeof CandlestickSeries | typeof LineSeries, data: any[]) => {
        const chart = allCharts.value[chartId]
        if (!chart) return
        const series = chart.addSeries(seriesType)
        series.setData(data)
        allSeries.value[chartId]?.push(series)
        return series
    }

    const clearChart = (chartId: number) => {
        const chart = allCharts.value[chartId]
        if (!chart) return
        for (const series of allSeries.value[chartId] || []) {
            chart.removeSeries(series)
        }
        allSeries.value[chartId] = []
    }

    return { registerChart, cleanSeries, addSeries, clearChart }
}