import { AlertTriangle } from "lucide-react"

export default function AlertBanner({ count }) {
  if (!count) return null
  return (
    <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-red-300">
      <AlertTriangle size={18} />
      <span className="font-semibold">
        {count} open alert{count !== 1 ? "s" : ""}
      </span>
      <span className="text-red-400/70">— investigate affected machines.</span>
    </div>
  )
}
