import { useEffect, useState } from "react"
import { Save, Loader2 } from "lucide-react"
import { getSettings, updateSettings, getMachines } from "../api/api.js"

const fmt = (ts) => (ts ? new Date(ts * 1000).toLocaleTimeString() : "—")

export default function Settings({ addToast }) {
  const [rules, setRules] = useState([])
  const [machines, setMachines] = useState([])
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getSettings().then((d) => setRules(d.rules || []))
    getMachines().then(setMachines)
  }, [])

  function update(idx, field, value) {
    setRules((prev) => {
      const copy = [...prev]
      copy[idx] = { ...copy[idx], [field]: value }
      return copy
    })
  }

  async function save() {
    setSaving(true)
    try {
      // Coerce numeric fields back to numbers before sending.
      const payload = rules.map((r) => ({
        ...r,
        threshold: Number(r.threshold),
        window_sec: Number(r.window_sec),
      }))
      await updateSettings(payload)
      addToast?.({ severity: "info", title: "Settings saved", message: "Alert rules reloaded" })
    } catch (e) {
      addToast?.({ severity: "HIGH", title: "Save failed", message: e.message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold text-slate-100">Settings</h1>

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold uppercase text-slate-400">Alert rules</h2>
        <div className="overflow-hidden rounded-lg border border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/60 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Field</th>
                <th className="px-4 py-2">Threshold</th>
                <th className="px-4 py-2">Window (s)</th>
                <th className="px-4 py-2">Severity</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {rules.map((r, i) => (
                <tr key={r.name || i}>
                  <td className="px-4 py-2 font-mono text-slate-200">{r.name}</td>
                  <td className="px-4 py-2 font-mono text-slate-400">{r.field}</td>
                  <td className="px-4 py-2">
                    <input
                      type="number"
                      value={r.threshold}
                      onChange={(e) => update(i, "threshold", e.target.value)}
                      className="w-28 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200"
                    />
                  </td>
                  <td className="px-4 py-2">
                    <input
                      type="number"
                      value={r.window_sec}
                      onChange={(e) => update(i, "window_sec", e.target.value)}
                      className="w-24 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200"
                    />
                  </td>
                  <td className="px-4 py-2">
                    <select
                      value={r.severity}
                      onChange={(e) => update(i, "severity", e.target.value)}
                      className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200"
                    >
                      <option value="HIGH">HIGH</option>
                      <option value="MEDIUM">MEDIUM</option>
                      <option value="LOW">LOW</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button
          onClick={save}
          disabled={saving}
          className="mt-3 flex items-center gap-2 rounded-md bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-500 disabled:opacity-50"
        >
          {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
          Save rules
        </button>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase text-slate-400">Connected agents</h2>
        <div className="overflow-hidden rounded-lg border border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/60 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-2">Machine</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Last seen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {machines.map((m) => (
                <tr key={m.machine_name}>
                  <td className="px-4 py-2 font-mono text-slate-200">{m.machine_name}</td>
                  <td className="px-4 py-2">
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-semibold ${
                        m.status === "OFFLINE"
                          ? "bg-red-500/15 text-red-400"
                          : m.status === "ALERT"
                          ? "bg-amber-500/15 text-amber-400"
                          : "bg-green-500/15 text-green-400"
                      }`}
                    >
                      {m.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-slate-400">{fmt(m.last_seen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
