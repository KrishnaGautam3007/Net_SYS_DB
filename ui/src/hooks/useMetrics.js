import { useCallback, useEffect, useState } from "react"
import { getMachineMetrics } from "../api/api"

/**
 * Load a machine's recent metric history and expose an append() to push live
 * points (from the WebSocket) while capping the series length.
 */
export function useMetrics(name, maxPoints = 360) {
  const [metrics, setMetrics] = useState([])
  const [loading, setLoading] = useState(true)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getMachineMetrics(name)
      setMetrics(data)
    } finally {
      setLoading(false)
    }
  }, [name])

  useEffect(() => {
    reload()
  }, [reload])

  const append = useCallback(
    (point) => {
      setMetrics((prev) => {
        const next = [...prev, point]
        return next.length > maxPoints ? next.slice(next.length - maxPoints) : next
      })
    },
    [maxPoints]
  )

  return { metrics, loading, append, reload }
}
