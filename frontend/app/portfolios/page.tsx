import Link from "next/link";

import { apiGet } from "../_lib/api";
import { PageHeader } from "../_components/PageHeader";
import { Card, CardContent } from "../_components/ui/Card";
import { CodeBlock } from "../_components/ui/CodeBlock";

export default async function PortfoliosPage() {
  let portfolios: unknown = null;
  let strategies: unknown = null;
  let err: string | null = null;
  try {
    [portfolios, strategies] = await Promise.all([apiGet("/portfolios"), apiGet("/strategies")]);
  } catch (e: any) {
    err = String(e?.message || e);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Portfolios"
        description={
          <>
            Configure portfolio strategy weights and overrides. Then allocate capital on{" "}
            <Link href="/allocations" className="font-medium text-foreground">
              allocations
            </Link>
            .
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="shadow-none">
          <CardContent className="space-y-3">
            <div className="text-sm font-medium">Portfolios</div>
            {err ? <div className="text-sm text-destructive">Error: {err}</div> : null}
            <CodeBlock value={portfolios ?? { hint: "No data yet." }} />
          </CardContent>
        </Card>
        <Card className="shadow-none">
          <CardContent className="space-y-3">
            <div className="text-sm font-medium">Strategies (for building portfolios)</div>
            <CodeBlock value={strategies ?? { hint: "No data yet." }} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

