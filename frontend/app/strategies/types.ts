export type StrategyCatalogRow = {
  name: string;
  enabled: boolean;
  config: Record<string, unknown>;
  has_plot?: boolean;
  category?: string | null;
  subcategory?: string | null;
  description?: string | null;
  api_status?: string | null;
  start_date?: string | null;
  cagr?: number | string | null;
  sharpe?: number | string | null;
  alpha?: number | string | null;
  beta?: number | string | null;
  max_drawdown?: number | string | null;
  research_url?: string | null;
};
