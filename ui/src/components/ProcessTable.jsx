export default function ProcessTable({ processes = [] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-800">
      <table className="w-full text-sm">
        <thead className="bg-slate-800/60 text-left text-xs uppercase text-slate-400">
          <tr>
            <th className="px-4 py-2">PID</th>
            <th className="px-4 py-2">Name</th>
            <th className="px-4 py-2 text-right">RAM (MB)</th>
            <th className="px-4 py-2">State</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {processes.length === 0 ? (
            <tr>
              <td colSpan={4} className="px-4 py-6 text-center text-slate-500">
                no process data
              </td>
            </tr>
          ) : (
            processes.map((p) => (
              <tr key={p.pid} className="hover:bg-slate-800/40">
                <td className="px-4 py-2 font-mono text-slate-400">{p.pid}</td>
                <td className="px-4 py-2 text-slate-200">{p.name}</td>
                <td className="px-4 py-2 text-right font-mono text-slate-200">
                  {Number(p.ram_mb).toFixed(1)}
                </td>
                <td className="px-4 py-2">
                  <span className="rounded bg-slate-700 px-2 py-0.5 font-mono text-xs">
                    {p.state}
                  </span>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
