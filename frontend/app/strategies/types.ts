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
};
