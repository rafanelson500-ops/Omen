import { io } from 'socket.io-client'
import { ref } from 'vue'

let BACKEND_URL = import.meta.env.VITE_API_URL
if (window.location.hostname === '192.168.1.149') {
BACKEND_URL = 'http://192.168.1.149:8000'
}
const socket = io(BACKEND_URL)

// Shared singletons — all useBackend() callers read the same refs.
// socket.off() before socket.on() prevents duplicate listeners from HMR re-evaluation.
const connectionStatus = ref(false)
socket.off('connection_status')
socket.on('connection_status', (status: boolean) => {
    connectionStatus.value = status
})

export interface AgentReport {
    agent: string
    report: string
}

const agentReports = ref<AgentReport[]>([])
socket.off('agent_report')
socket.on('agent_report', (data: AgentReport) => {
    agentReports.value.push(data)
})

const clearAgentReports = () => { agentReports.value = [] }

export const useBackend = () => {
    const connect = () => {
        console.log('Connecting to backend...')
        socket.connect()
    }

    const request = async (event: string, data: any, timeout: number = 10000) => {
        socket.emit(event, data)
        return new Promise((resolve, reject) => {
            const handler = (response: any) => {
                clearTimeout(timeoutId)
                socket.off(event, handler)
                resolve(response)
            }
            socket.on(event, handler)
            const timeoutId = setTimeout(() => {
              socket.off(event, handler)
              reject(new Error(`Request timed out after ${timeout}ms`))
            }, timeout)
          })
    }
    
    return { connectionStatus, connect, request, agentReports, clearAgentReports }
}