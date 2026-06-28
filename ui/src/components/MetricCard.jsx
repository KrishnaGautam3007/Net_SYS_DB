import { useNavigate } from "react-router-dom"
import { Cpu, MemoryStick, Circle } from "lucide-react"

function Bar({ pct, color }) {
  const clamped = Math.max(0, Math.min(100, pct || 0))
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-700">
      <div
        className={`h-full rounded-full ${color} transition-all duration-500`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  )
}

const STATUS = {
  ONLINE: { dot: "text-green-500", label: "ONLINE", badge: "bg-green-500/15 text-green-400" },
  OFFLINE: { dot: "text-red-500", label: "OFFLINE", badge: "bg-red-500/15 text-red-400" },
  ALERT: { dot: "text-amber-500", label: "ALERT", badge: "bg-amber-500/15 text-amber-400" },
}

export default function MetricCard({
  machine_name,
  cpu_percent,
  ram_used_mb,
  ram_total_mb,
  status = "ONLINE",
  last_seen,
}) {
  const navigate = useNavigate()
  const s = STATUS[status] || STATUS.ONLINE
  const ramPct = ram_total_mb ? (ram_used_mb / ram_total_mb) * 100 : 0
  const seenAgo = last_seen ? `${Math.max(0, Math.round(Date.now() / 1000 - last_seen))}s ago` : "—"

  const base =
    "cursor-pointer rounded-xl border p-4 transition-all hover:scale-[1.02] hover:shadow-lg"
  const tone =
    status === "OFFLINE"
      ? "border-red-500/40 bg-red-950/30"
      : status === "ALERT"
      ? "border-amber-500/60 bg-slate-900 animate-pulse"
      : "border-slate-800 bg-slate-900"

  return (
    <div
      className={`${base} ${tone}`}
      onClick={() => navigate(`/machine/${encodeURIComponent(machine_name)}`)}
    >
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Circle size={10} className={`${s.dot} fill-current`} />
          <span className="font-mono font-bold text-slate-100">{machine_name}</span>
        </div>
        <span className={`rounded px-2 py-0.5 text-xs font-semibold ${s.badge}`}>{s.label}</span>
      </div>

      <div className="space-y-3">
        <div>
          <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
            <span className="flex items-center gap-1">
              <Cpu size={12} /> CPU
            </span>
            <span className="font-mono text-slate-200">{(cpu_percent ?? 0).toFixed(1)}%</span>
          </div>
          <Bar pct={cpu_percent} color="bg-cyan-500" />
        </div>

        <div>
          <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
            <span className="flex items-center gap-1">
              <MemoryStick size={12} /> RAM
            </span>
            <span className="font-mono text-slate-200">
              {Math.round(ram_used_mb ?? 0)} / {Math.round(ram_total_mb ?? 0)} MB
            </span>
          </div>
          <Bar pct={ramPct} color="bg-violet-500" />
        </div>
      </div>

      <div className="mt-3 text-right text-xs text-slate-500">last seen {seenAgo}</div>
    </div>
  )
}
