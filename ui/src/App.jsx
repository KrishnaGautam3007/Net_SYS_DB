import { useCallback, useEffect, useRef, useState } from "react"
import { BrowserRouter, Route, Routes } from "react-router-dom"
import Navbar from "./components/Navbar.jsx"
import Toast from "./components/Toast.jsx"
import { useSocket } from "./hooks/useSocket.js"
import { getStatus } from "./api/api.js"
import Overview from "./pages/Overview.jsx"
import MachineDetail from "./pages/MachineDetail.jsx"
import QueryConsole from "./pages/QueryConsole.jsx"
import Alerts from "./pages/Alerts.jsx"
import Settings from "./pages/Settings.jsx"

export default function App() {
  const [toasts, setToasts] = useState([])
  const [openAlerts, setOpenAlerts] = useState(0)
  const idRef = useRef(0)

  const addToast = useCallback((toast) => {
    const id = ++idRef.current
    setToasts((prev) => [...prev, { ...toast, id }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 5000)
  }, [])

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  // Global alert handling: toast + badge refresh on every fired alert.
  useSocket(null, (alert) => {
    addToast({
      severity: alert.severity,
      title: `${alert.rule} on ${alert.machine}`,
      message: `${alert.severity} alert fired`,
    })
    setOpenAlerts((n) => n + 1)
  })

  const refreshStatus = useCallback(async () => {
    try {
      const s = await getStatus()
      setOpenAlerts(s.open_alerts)
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    refreshStatus()
    const id = setInterval(refreshStatus, 10000)
    return () => clearInterval(id)
  }, [refreshStatus])

  return (
    <BrowserRouter>
      <Navbar openAlerts={openAlerts} />
      <Toast toasts={toasts} onDismiss={dismiss} />
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Overview addToast={addToast} />} />
          <Route path="/machine/:name" element={<MachineDetail />} />
          <Route path="/query" element={<QueryConsole />} />
          <Route path="/alerts" element={<Alerts addToast={addToast} />} />
          <Route path="/settings" element={<Settings addToast={addToast} />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
