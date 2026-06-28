import { X } from "lucide-react"

const COLORS = {
  HIGH: "bg-red-600 border-red-400",
  MEDIUM: "bg-amber-500 border-amber-300",
  info: "bg-sky-600 border-sky-400",
}

export default function Toast({ toasts, onDismiss }) {
  return (
    <div className="pointer-events-none fixed right-4 top-16 z-50 flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-start gap-2 rounded-lg border px-4 py-3 text-sm text-white shadow-lg animate-slide-in ${
            COLORS[t.severity] || COLORS.info
          }`}
        >
          <div className="flex-1">
            <div className="font-semibold">{t.title}</div>
            {t.message && <div className="text-white/90">{t.message}</div>}
          </div>
          <button
            onClick={() => onDismiss(t.id)}
            className="text-white/80 hover:text-white"
            aria-label="dismiss"
          >
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  )
}
