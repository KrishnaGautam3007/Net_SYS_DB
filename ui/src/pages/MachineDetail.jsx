import { useEffect, useMemo, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { ArrowLeft, Cpu, MemoryStick, HardDrive, ArrowUpFromLine } from "lucide-react"
import MetricChart from "../components/MetricChart.jsx"
import ProcessTable from "../components/ProcessTable.jsx"
import { useMetrics } from "../hooks/useMetrics.js"
import { useSocket } from "../hooks/useSocket.js"
import { getMachineProcs, getAlerts } from "../api/api.js"

const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString()

function toPoint(m) {
  return {
    time: fmtTime(m.timestamp),
    cpu_percent: Number((m.cpu_percent ?? 0).toFixed(2)),
    ram_used_mb: Math.round(m.ram_used_mb ?? 0),
    ram_available_mb: Math.round((m.ram_total_mb ?? 0) - (m.ram_used_mb ?? 0)),
    disk_write_kb: m.disk_write_kb ?? 0,
    net_tx_kb: m.net_tx_kb ?? 0,
  }
}

function Tile({ icon: Icon, label, value, unit, color }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="mb-2 flex items-center gap-2 text-xs text-slate-400">
        <Icon size={14} className={color} /> {label}
      </div>
      <div className="font-mono text-2xl font-bold text-slate-100">
        {value}
        <span className="ml-1 text-sm font-normal text-slate-500">{unit}</span>
      </div>
    </div>
  )
}

export default function MachineDetail() {
  const { name } = useParams()
  const { metrics, append } = useMetrics(name)
  const [procs, setProcs] = useState([])
  const [latest, setLatest] = useState(null)
  const [alerts, setAlerts] = useState([])

  useEffect(() => {
    getMachineProcs(name).then(setProcs)
    getAlerts({ machine: name }).then(setAlerts)
  }, [name])

  useEffect(() => {
    if (metrics.length) setLatest(metrics[metrics.length - 1])
  }, [metrics])

  useSocket((metric) => {
    if (metric.machine_name !== name) return
    append(metric)
    setLatest(metric)
    if (metric.processes) setProcs(metric.processes)
  }, null)

  const chartData = useMemo(() => metrics.map(toPoint), [metrics])

  return (
    <div>
      <Link to="/" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-400 hover:text-cyan-300">
        <ArrowLeft size={15} /> Back to overview
      </Link>
      <h1 className="mb-5 font-mono text-2xl font-bold text-slate-100">{name}</h1>

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Tile icon={Cpu} label="CPU" value={(latest?.cpu_percent ?? 0).toFixed(1)} unit="%" color="text-cyan-400" />
        <Tile icon={MemoryStick} label="RAM used" value={Math.round(latest?.ram_used_mb ?? 0)} unit="MB" color="text-violet-400" />
        <Tile icon={HardDrive} label="Disk write" value={latest?.disk_write_kb ?? 0} unit="KB/s" color="text-amber-400" />
        <Tile icon={ArrowUpFromLine} label="Net TX" value={latest?.net_tx_kb ?? 0} unit="KB/s" color="text-green-400" />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h2 className="mb-3 text-sm font-semibold text-slate-300">CPU %</h2>
          <MetricChart data={chartData} type="line" unit="%" series={[{ key: "cpu_percent", color: "#06b6d4", name: "CPU %" }]} />
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Memory (MB)</h2>
          <MetricChart
            data={chartData}
            type="area"
            series={[
              { key: "ram_used_mb", color: "#8b5cf6", name: "Used" },
              { key: "ram_available_mb", color: "#22c55e", name: "Available" },
            ]}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Top processes</h2>
          <ProcessTable processes={procs} />
        </div>
        <div>
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Alert history</h2>
          <div className="space-y-2">
            {alerts.length === 0 ? (
              <div className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-6 text-center text-sm text-slate-500">
                no alerts for this machine
              </div>
            ) : (
              alerts.map((a) => (
                <div key={a.id} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 px-4 py-2 text-sm">
                  <span className={`font-semibold ${a.severity === "HIGH" ? "text-red-400" : "text-amber-400"}`}>
                    {a.rule}
                  </span>
                  <span className="text-slate-500">{fmtTime(a.fired_at)}</span>
                  <span className={a.resolved_at ? "text-green-400" : "text-red-400"}>
                    {a.resolved_at ? "resolved" : "open"}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
