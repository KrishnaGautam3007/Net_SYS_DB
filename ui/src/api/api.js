import axios from "axios"

// In production the UI is served by Flask on the same origin, so an empty
// base resolves to relative /api/... requests. Override with VITE_API_URL in
// dev if the API runs elsewhere.
export const BASE = import.meta.env.VITE_API_URL || ""

const client = axios.create({ baseURL: BASE })

export async function getMachines() {
  const res = await client.get("/api/machines")
  return res.data
}

export async function getMachineMetrics(name) {
  const res = await client.get(`/api/machines/${encodeURIComponent(name)}/metrics`)
  return res.data
}

export async function getMachineProcs(name) {
  const res = await client.get(`/api/machines/${encodeURIComponent(name)}/procs`)
  return res.data
}

export async function runQuery(q) {
  const res = await client.post("/api/query", { q })
  return res.data
}

export async function getAlerts(params = {}) {
  const res = await client.get("/api/alerts", { params })
  return res.data
}

export async function getSettings() {
  const res = await client.get("/api/settings")
  return res.data
}

export async function updateSettings(rules) {
  const res = await client.post("/api/settings", { rules })
  return res.data
}

export async function getStatus() {
  const res = await client.get("/api/status")
  return res.data
}
