import { useCallback, useEffect, useState } from "react"
import { RefreshCw, Server } from "lucide-react"
import MetricCard from "../components/MetricCard.jsx"
import { useSocket } from "../hooks/useSocket.js"
import { getMachines, getStatus } from "../api/api.js"

export default function Overview() {
  const [machines, setMachines] = useState([])
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [m, s] = await Promise.all([getMachines(), getStatus()])
      setMachines(m)
      setStatus(s)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Live updates: patch the matching card in place.
  useSocket((metric) => {
    setMachines((prev) => {
      const idx = prev.findIndex((m) => m.machine_name === metric.machine_name)
      const patch = {
        machine_name: metric.machine_name,
        machine_id: metric.machine_id,
        cpu_percent: metric.cpu_percent,
        ram_used_mb: metric.ram_used_mb,
        ram_total_mb: metric.ram_total_mb,
        status: "ONLINE",
        last_seen: metric.timestamp,
      }
      if (idx === -1) return [...prev, patch].sort((a, b) => a.machine_name.localeCompare(b.machine_name))
      const copy = [...prev]
      copy[idx] = { ...copy[idx], ...patch }
      return copy
    })
  }, null)

  return (
    <div>
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Overview</h1>
          {status && (
            <p className="mt-1 text-sm text-slate-400">
              {status.connected_agents} agents · {status.record_count} records ·{" "}
              {status.page_count} pages · uptime {status.uptime_sec}s
            </p>
          )}
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-700"
        >
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {machines.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-slate-800 bg-slate-900 py-16 text-slate-500">
          <Server size={32} className="mb-2" />
          {loading ? "Loading machines…" : "No machines reporting yet."}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {machines.map((m) => (
            <MetricCard key={m.machine_name} {...m} />
          ))}
        </div>
      )}
    </div>
  )
}
