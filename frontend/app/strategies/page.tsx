import { apiGet } from "../_lib/api";
import { StrategiesClient } from "./StrategiesClient";

export default async function StrategiesPage() {
  const catalog = await apiGet<{ rows: Array<{ name: string; enabled: boolean; config: Record<string, unknown> }> }>(
    "/strategies/catalog",
  );
  const strategies = (catalog?.rows || []).map((r) => ({ name: r.name, enabled: !!r.enabled, config: r.config || {} }));
  return <StrategiesClient initialStrategies={strategies as any} />;
}
