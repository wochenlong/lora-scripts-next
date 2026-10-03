import type { EngineRuntimeState } from "./catalog"

const ORDER_KEY = "nt.settings.engineOrder"
export type EngineFilter = "all" | "installed" | "not_installed"

export function normalizeOrder(saved: unknown, catalog: readonly string[]): string[] {
  const valid = Array.isArray(saved)
    ? saved.filter((id): id is string => typeof id === "string" && catalog.includes(id))
    : []
  return [...new Set([...valid, ...catalog])]
}

export function readEngineOrder(catalog: readonly string[]): string[] {
  try {
    return normalizeOrder(JSON.parse(localStorage.getItem(ORDER_KEY) || "[]"), catalog)
  } catch {
    return [...catalog]
  }
}

export function saveEngineOrder(order: readonly string[]): boolean {
  try {
    localStorage.setItem(ORDER_KEY, JSON.stringify(order))
    return true
  } catch {
    return false
  }
}

export function moveEngine(order: readonly string[], id: string, target: string, after = false): string[] {
  if (id === target || !order.includes(id) || !order.includes(target)) return [...order]
  const next = order.filter((item) => item !== id)
  next.splice(next.indexOf(target) + (after ? 1 : 0), 0, id)
  return next
}

export function matchesEngineFilter(text: string, state: EngineRuntimeState, query: string, filter: EngineFilter): boolean {
  const matchesStatus = filter === "all"
    || (filter === "installed" ? ["ready", "installed_unverified"].includes(state) : state === "not_installed")
  return matchesStatus && text.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
}
