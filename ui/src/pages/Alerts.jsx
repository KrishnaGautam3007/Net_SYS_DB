import { useMemo, useState } from "react"
import AlertBanner from "../components/AlertBanner.jsx"
import { useAlerts } from "../hooks/useAlerts.js"
import { useSocket } from "../hooks/useSocket.js"

const fmt = (ts) => (ts ? new Date(ts * 1000).toLocaleString() : "—")
const duration = (a) => {
  if (!a.resolved_at) return "ongoing"
  const s = Math.max(0, Math.round(a.resolved_at - a.fired_at))
  return `${s}s`
}

export default function Alerts({ addToast }) {
  const { alerts, prepend, reload } = useAlerts()
  const [machine, setMachine] = useState("")
  const [severity, setSeverity] = useState("")

  useSocket(null, (alert) => {
    prepend(alert)
    addToast?.({ severity: alert.severity, title: `${alert.rule} on ${alert.machine}`, message: "alert fired" })
  })

  const machines = useMemo(() => [...new Set(alerts.map((a) => a.machine))].sort(), [alerts])

  const filtered = useMemo(() => {
    return alerts
      .filter((a) => (machine ? a.machine === machine : true))
      .filter((a) => (severity ? a.severity === severity : true))
      .sort((a, b) => b.fired_at - a.fired_at)
  }, [alerts, machine, severity])

  const openCount = useMemo(() => alerts.filter((a) => !a.resolved_at).length, [alerts])

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold text-slate-100">Alerts</h1>
      <AlertBanner count={openCount} />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          value={machine}
          onChange={(e) => setMachine(e.target.value)}
          className="rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-300"
        >
          <option value="">all machines</option>
          {machines.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-300"
        >
          <option value="">all severities</option>
          <option value="HIGH">HIGH</option>
          <option value="MEDIUM">MEDIUM</option>
        </select>
        <button
          onClick={reload}
          className="rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-700"
        >
          Refresh
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-800/60 text-left text-xs uppercase text-slate-400">
            <tr>
              <th className="px-4 py-2">Machine</th>
              <th className="px-4 py-2">Rule</th>
              <th className="px-4 py-2">Severity</th>
              <th className="px-4 py-2">Fired</th>
              <th className="px-4 py-2">Resolved</th>
              <th className="px-4 py-2">Duration</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-500">
                  no alerts
                </td>
              </tr>
            ) : (
              filtered.map((a) => (
                <tr key={a.id} className="hover:bg-slate-800/40">
                  <td className="px-4 py-2 font-mono text-slate-200">{a.machine}</td>
                  <td className="px-4 py-2 text-slate-200">{a.rule}</td>
                  <td className="px-4 py-2">
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-semibold ${
                        a.severity === "HIGH"
                          ? "bg-red-500/15 text-red-400"
                          : "bg-amber-500/15 text-amber-400"
                      }`}
                    >
                      {a.severity}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-slate-400">{fmt(a.fired_at)}</td>
                  <td className="px-4 py-2 text-slate-400">{fmt(a.resolved_at)}</td>
                  <td className="px-4 py-2 text-slate-400">{duration(a)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
