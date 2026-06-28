import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

const AXIS = "#64748b"
const GRID = "#1e293b"

/**
 * Reusable time-series chart. `type` is "line" or "area"; `series` is a list
 * of { key, color, name } describing the lines/areas to draw.
 */
export default function MetricChart({ data, type = "line", series, unit = "", height = 240 }) {
  const Chart = type === "area" ? AreaChart : LineChart

  return (
    <ResponsiveContainer width="100%" height={height}>
      <Chart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
        <XAxis dataKey="time" stroke={AXIS} tick={{ fontSize: 11 }} minTickGap={32} />
        <YAxis stroke={AXIS} tick={{ fontSize: 11 }} width={48} unit={unit} />
        <Tooltip
          contentStyle={{
            background: "#0f172a",
            border: "1px solid #334155",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "#94a3b8" }}
        />
        {series.map((s) =>
          type === "area" ? (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.name || s.key}
              stroke={s.color}
              fill={s.color}
              fillOpacity={0.2}
              strokeWidth={2}
              isAnimationActive={false}
              dot={false}
            />
          ) : (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.name || s.key}
              stroke={s.color}
              strokeWidth={2}
              isAnimationActive={false}
              dot={false}
            />
          )
        )}
      </Chart>
    </ResponsiveContainer>
  )
}
