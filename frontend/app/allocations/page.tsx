import { apiGet } from "../_lib/api";
import { AllocationsClient } from "./AllocationsClient";

export default async function AllocationsPage() {
  const portfolios = await apiGet("/portfolios");
  return <AllocationsClient initialPortfolios={(portfolios as any) ?? []} />;
}

