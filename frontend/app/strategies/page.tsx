import { apiGet } from "../_lib/api";
import { StrategiesClient } from "./StrategiesClient";
import type { StrategyCatalogRow } from "./types";

export default async function StrategiesPage() {
  const catalog = await apiGet<{ rows: StrategyCatalogRow[] }>("/strategies/catalog");
  const rows = (catalog?.rows || []).map((r) => ({
    name: r.name,
    enabled: !!r.enabled,
    config: (r.config || {}) as Record<string, unknown>,
    has_plot: !!r.has_plot,
    category: r.category ?? undefined,
    subcategory: r.subcategory ?? undefined,
    description: r.description ?? undefined,
    api_status: r.api_status ?? undefined,
    start_date: r.start_date ?? undefined,
    cagr: r.cagr ?? undefined,
    sharpe: r.sharpe ?? undefined,
    alpha: r.alpha ?? undefined,
    beta: r.beta ?? undefined,
    max_drawdown: r.max_drawdown ?? undefined,
    research_url: r.research_url ?? undefined,
  }));
  return <StrategiesClient initialStrategies={rows} />;
}
