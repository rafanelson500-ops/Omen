import { io, Socket } from "socket.io-client"

let socket: Socket | null = null

export const useBackend = (url: string | null = null) => {
    if (url) socket = io(url)

    socket?.on("connect", () => {
        console.log("Connected to backend")
    })

    const subscribe = (endpoint: string, callback: (data: any) => void) => {
        socket?.on(endpoint, callback)
    }

    return {
        socket,
        subscribe
    }
}