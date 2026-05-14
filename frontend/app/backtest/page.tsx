import { apiGet } from "../_lib/api";
import { BacktestClient } from "./BacktestClient";
import type { StrategyCatalogRow } from "../strategies/types";

type RunRow = {
  id: string;
  type: string;
  status: string;
  created_at?: string;
  error?: string | null;
};

export default async function BacktestPage() {
  const [catalog, runs] = await Promise.all([
    apiGet<{ rows: StrategyCatalogRow[] }>("/strategies/catalog"),
    apiGet<RunRow[]>("/runs?limit=20"),
  ]);

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
  }));

  const runRows = (runs || []).map((r) => ({
    id: String(r.id),
    type: r.type,
    status: r.status,
    created_at: r.created_at,
    error: r.error,
  }));

  return <BacktestClient initialCatalog={rows} initialRuns={runRows} />;
}
