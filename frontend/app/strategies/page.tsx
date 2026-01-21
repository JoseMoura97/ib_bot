import { apiGet } from "../_lib/api";
import { StrategiesClient } from "./StrategiesClient";

export default async function StrategiesPage() {
  const strategies = await apiGet("/strategies");
  return <StrategiesClient initialStrategies={strategies as any} />;
}
