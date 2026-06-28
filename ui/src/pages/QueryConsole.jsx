import { useMemo, useState } from "react"
import { Play, Loader2, History } from "lucide-react"
import { runQuery } from "../api/api.js"

const HISTORY_KEY = "netsysdb_query_history"

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []
  } catch {
    return []
  }
}

function saveHistory(list) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, 20)))
  } catch {
    /* ignore */
  }
}

const now = () => Math.floor(Date.now() / 1000)

const PRESETS = [
  {
    label: "Top CPU last hour",
    q: () =>
      `SELECT machine_name, max(cpu_percent) FROM metrics WHERE timestamp BETWEEN ${now() - 3600} AND ${now()} GROUP BY machine_name`,
  },
  { label: "All HIGH alerts today", q: () => `SELECT * FROM alerts WHERE severity = 'HIGH'` },
  {
    label: "RAM trend node-1",
    q: () =>
      `SELECT timestamp, ram_used_mb FROM metrics WHERE machine_name = 'node-1' ORDER BY timestamp DESC LIMIT 50`,
  },
]

export default function QueryConsole() {
  const [query, setQuery] = useState("SELECT * FROM metrics ORDER BY timestamp DESC LIMIT 10")
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState(loadHistory)
  const [sort, setSort] = useState({ col: null, dir: "asc" })

  async function run(q = query) {
    setLoading(true)
    setError(null)
    try {
      const result = await runQuery(q)
      setRows(result)
      const next = [q, ...history.filter((h) => h !== q)].slice(0, 20)
      setHistory(next)
      saveHistory(next)
    } catch (e) {
      setError(e.response?.data?.error || e.message)
      setRows(null)
    } finally {
      setLoading(false)
    }
  }

  const columns = useMemo(() => {
    if (!rows || rows.length === 0) return []
    const cols = []
    rows.forEach((r) => Object.keys(r).forEach((k) => !cols.includes(k) && cols.push(k)))
    return cols
  }, [rows])

  const sortedRows = useMemo(() => {
    if (!rows || !sort.col) return rows
    const copy = [...rows]
    copy.sort((a, b) => {
      const x = a[sort.col]
      const y = b[sort.col]
      if (x === y) return 0
      const cmp = x > y ? 1 : -1
      return sort.dir === "asc" ? cmp : -cmp
    })
    return copy
  }, [rows, sort])

  function toggleSort(col) {
    setSort((s) =>
      s.col === col ? { col, dir: s.dir === "asc" ? "desc" : "asc" } : { col, dir: "asc" }
    )
  }

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold text-slate-100">Query Console</h1>

      <div className="mb-3 flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => {
              const q = p.q()
              setQuery(q)
              run(q)
            }}
            className="rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-700"
          >
            {p.label}
          </button>
        ))}
      </div>

      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        rows={3}
        spellCheck={false}
        className="w-full rounded-lg border border-slate-700 bg-slate-950 p-3 font-mono text-sm text-cyan-200 outline-none focus:border-cyan-500"
      />

      <div className="mt-2 flex items-center gap-3">
        <button
          onClick={() => run()}
          disabled={loading}
          className="flex items-center gap-2 rounded-md bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-500 disabled:opacity-50"
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
          Run
        </button>

        {history.length > 0 && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <History size={14} />
            <select
              onChange={(e) => e.target.value && setQuery(e.target.value)}
              className="max-w-md rounded border border-slate-700 bg-slate-800 px-2 py-1 text-slate-300"
              value=""
            >
              <option value="">recent queries…</option>
              {history.map((h, i) => (
                <option key={i} value={h}>
                  {h.length > 70 ? h.slice(0, 70) + "…" : h}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {rows && !error && (
        <div className="mt-4 overflow-x-auto rounded-lg border border-slate-800">
          {rows.length === 0 ? (
            <div className="px-4 py-6 text-center text-slate-500">(no rows)</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-slate-800/60 text-left text-xs uppercase text-slate-400">
                <tr>
                  {columns.map((c) => (
                    <th
                      key={c}
                      onClick={() => toggleSort(c)}
                      className="cursor-pointer select-none px-4 py-2 hover:text-cyan-300"
                    >
                      {c}
                      {sort.col === c ? (sort.dir === "asc" ? " ▲" : " ▼") : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {sortedRows.map((r, i) => (
                  <tr key={i} className="hover:bg-slate-800/40">
                    {columns.map((c) => (
                      <td key={c} className="px-4 py-2 font-mono text-slate-200">
                        {String(r[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="px-4 py-2 text-xs text-slate-500">{rows.length} row(s)</div>
        </div>
      )}
    </div>
  )
}
