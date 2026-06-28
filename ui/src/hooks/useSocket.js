import { useEffect, useRef } from "react"
import { io } from "socket.io-client"
import { BASE } from "../api/api"

/**
 * Subscribe to live collector events. onMetric is called for every
 * "metric_update" and onAlert for every "alert_fired". Callbacks are kept in
 * refs so passing new inline functions does not reconnect the socket.
 */
export function useSocket(onMetric, onAlert) {
  const metricRef = useRef(onMetric)
  const alertRef = useRef(onAlert)
  metricRef.current = onMetric
  alertRef.current = onAlert

  useEffect(() => {
    const socket = BASE ? io(BASE) : io()
    socket.on("metric_update", (data) => metricRef.current && metricRef.current(data))
    socket.on("alert_fired", (data) => alertRef.current && alertRef.current(data))
    return () => socket.disconnect()
  }, [])
}
