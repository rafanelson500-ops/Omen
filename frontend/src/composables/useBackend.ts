import { ref } from "vue"
import { io, type Socket } from "socket.io-client"


export const useBackend = () => {
  let BACKEND_URL = import.meta.env.VITE_API_URL
  if (window.location.hostname === "192.168.1.149") {
    BACKEND_URL = "http://192.168.1.149:8000"
  }
  const socket = ref<Socket | null>(null)
  const connected = ref(false)
  const onUpdateAllCallback = ref<(() => void) | null>(null)

  const setUpdateAllCallback = (callback: () => void) => {
    onUpdateAllCallback.value = callback
  }

  const connect = () => {
    console.log(`Connecting to backend (${ BACKEND_URL })...`)
    socket.value = io(BACKEND_URL)
    socket.value?.on("connect", () => {
      connected.value = true
      console.log("Connected to backend")
    })
    socket.value?.on("disconnect", () => {
      connected.value = false
      console.log("Disconnected from backend")
    })
    socket.value?.on("message", (data: any) => {
      console.log("Message received: ", data)
      if (data.id === -1 && onUpdateAllCallback.value) {
        onUpdateAllCallback.value()
      }
    })
  }

  const sendMessage = (data: any) => {
    if (socket.value) {
      console.log("Sending message: ", data)
      socket.value.emit("message", data)
    }
  }

  const request = async (data: any, id: number, timeout: number = 5000) => {
    data.id = id
    if (socket.value) {
      console.log("Sending request: ", data)
      socket.value.emit("message", data)
      return new Promise((resolve, reject) => {
        const handler = (response: any) => {
          if (response.id === id) {
            clearTimeout(timeoutId)
            socket.value?.off("message", handler)
            resolve(response.data)
          }
        }
        socket.value?.on("message", handler)
        const timeoutId = setTimeout(() => {
          socket.value?.off("message", handler)
          reject(new Error(`Request timed out after ${timeout}ms`))
        }, timeout)
      })
    }
  }

  const loadLogs = async (): Promise<Array<{ timestamp: string; message: string }>> => {
    try {
      const logsText = await request({ action: "get_logs" }, 6) as string
      if (logsText) {
        const lines = logsText.trim().split('\n').filter(line => line.trim())
        lines.reverse()
        return lines.map(line => {
          const match = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (.+)$/)
          if (match && match[1] && match[2]) {
            return { timestamp: match[1], message: match[2] }
          }
          return { timestamp: '', message: line }
        })
      }
      return []
    } catch (error) {
      console.error('Failed to load logs:', error)
      return []
    }
  }

  const updateDashboard = async () => {
    const botData = await request({ action: "get_all" }, 1) as any
    const currentPosition = await request({ action: "get_current_position" }, 2) as any
    const logs = await loadLogs()
    return {
      botData: {
        enabled: botData.enabled as boolean,
        session: botData.session,
        lots_size: botData.lots_size,
        confidence_threshold: botData.confidence_threshold,
        mode: botData.mode,
        current_position: currentPosition.current_position
      },
      logs
    }
  }

  const trainModels = async (): Promise<void> => {
    try {
      await request({ action: "train_models" }, 7, 300000) // 5 minute timeout for training
    } catch (error) {
      console.error('Failed to train models:', error)
      throw error
    }
  }

  const getBacktestData = async (): Promise<any[]> => {
    try {
      const backtestData = await request({ action: "backtest" }, 8, 60000) // 1 minute timeout
      return JSON.parse(backtestData as string)
    } catch (error) {
      console.error('Failed to get backtest data:', error)
      throw error
    }
  }

  const getMonteCarloData = async (): Promise<any> => {
    try {
      const data = await request({ action: "monte_carlo" }, 9, 300000) // 5 minute timeout
      return JSON.parse(data as string)
    } catch (error) {
      console.error('Failed to get Monte Carlo data:', error)
      throw error
    }
  }

  return { connect, connected, sendMessage, request, loadLogs, updateDashboard, setUpdateAllCallback, trainModels, getBacktestData, getMonteCarloData }
}