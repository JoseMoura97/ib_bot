import { apiGet } from "../_lib/api";
import { PortfoliosClient } from "./PortfoliosClient";

export default async function PortfoliosPage() {
  const [portfolios, strategies] = await Promise.all([apiGet("/portfolios"), apiGet("/strategies")]);
  return <PortfoliosClient initialPortfolios={(portfolios as any) ?? []} strategies={(strategies as any) ?? []} />;
}
