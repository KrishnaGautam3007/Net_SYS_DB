import { useCallback, useEffect, useState } from "react"
import { getAlerts } from "../api/api"

/** Load alert history with optional filters and expose helpers to refresh. */
export function useAlerts(params = {}) {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const key = JSON.stringify(params)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getAlerts(JSON.parse(key))
      setAlerts(data)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  useEffect(() => {
    reload()
  }, [reload])

  const prepend = useCallback((alert) => {
    setAlerts((prev) => [alert, ...prev])
  }, [])

  return { alerts, loading, reload, prepend }
}
