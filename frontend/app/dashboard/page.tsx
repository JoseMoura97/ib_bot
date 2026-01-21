import Link from "next/link";

import { PageHeader } from "../_components/PageHeader";
import { Card, CardContent } from "../_components/ui/Card";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Quick entry point for strategy analytics, metrics, and recent runs."
        right={
          <Link href="/runs" className="text-sm text-muted-foreground hover:text-foreground">
            View runs →
          </Link>
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="shadow-none">
          <CardContent className="py-5">
            <div className="text-xs font-semibold text-muted-foreground">Strategies</div>
            <div className="mt-2 text-sm text-muted-foreground">
              Manage strategy enable flags and configs on <Link href="/strategies">Strategies</Link>.
            </div>
          </CardContent>
        </Card>
        <Card className="shadow-none">
          <CardContent className="py-5">
            <div className="text-xs font-semibold text-muted-foreground">Portfolios</div>
            <div className="mt-2 text-sm text-muted-foreground">
              Configure portfolio weights and overrides on <Link href="/portfolios">Portfolios</Link>.
            </div>
          </CardContent>
        </Card>
        <Card className="shadow-none">
          <CardContent className="py-5">
            <div className="text-xs font-semibold text-muted-foreground">Trading</div>
            <div className="mt-2 text-sm text-muted-foreground">
              Inspect <Link href="/paper">Paper</Link> and <Link href="/live">Live</Link> status.
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

