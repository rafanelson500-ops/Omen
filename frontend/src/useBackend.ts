import { ref } from "vue"
import { io, type Socket } from "socket.io-client"

const BACKEND_URL = import.meta.env.VITE_API_URL

export const useBackend = () => {
  const socket = ref<Socket | null>(null)
  const connected = ref(false)

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
    })
  }

  const sendMessage = (data: any) => {
    if (socket.value) {
      console.log("Sending message: ", data)
      socket.value.emit("message", data)
    }
  }

  const request = async (data: any, id: number) => {
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
          reject(new Error("Request timed out after 5s"))
        }, 5000)
      })
    }
  }

  return { connect, connected, sendMessage, request }
}