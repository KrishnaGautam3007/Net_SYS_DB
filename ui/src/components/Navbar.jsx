import { NavLink } from "react-router-dom"
import { LayoutDashboard, Terminal, Bell, Settings as SettingsIcon, Activity } from "lucide-react"

const links = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/query", label: "Query Console", icon: Terminal },
  { to: "/alerts", label: "Alerts", icon: Bell },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
]

export default function Navbar({ openAlerts = 0 }) {
  return (
    <nav className="flex items-center gap-1 border-b border-slate-800 bg-slate-900/80 px-4 py-3 backdrop-blur">
      <div className="mr-6 flex items-center gap-2 font-mono text-lg font-bold text-cyan-400">
        <Activity size={20} />
        NetSysDB
      </div>
      {links.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            `relative flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors ${
              isActive
                ? "bg-cyan-500/15 text-cyan-300"
                : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            }`
          }
        >
          <Icon size={16} />
          {label}
          {label === "Alerts" && openAlerts > 0 && (
            <span className="ml-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-xs font-bold text-white">
              {openAlerts}
            </span>
          )}
        </NavLink>
      ))}
      <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
        <span className="h-2 w-2 animate-pulse rounded-full bg-green-500" />
        live
      </div>
    </nav>
  )
}
