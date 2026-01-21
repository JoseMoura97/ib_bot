import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "./_components/ui/Card";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Welcome</h1>
        <p className="text-sm text-muted-foreground">Control panel for backtests, strategies, portfolios, and trading status.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Dashboard</CardTitle>
          </CardHeader>
          <CardContent>
            <Link className="text-sm font-medium" href="/dashboard">
              Open dashboard →
            </Link>
          </CardContent>
        </Card>
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Strategies</CardTitle>
          </CardHeader>
          <CardContent>
            <Link className="text-sm font-medium" href="/strategies">
              Manage strategies →
            </Link>
          </CardContent>
        </Card>
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Portfolios</CardTitle>
          </CardHeader>
          <CardContent>
            <Link className="text-sm font-medium" href="/portfolios">
              View portfolios →
            </Link>
          </CardContent>
        </Card>
      </div>

      <Card className="shadow-none">
        <CardContent className="py-5">
          <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
            <Link href="/runs" className="font-medium text-foreground">
              Runs
            </Link>
            <span>·</span>
            <Link href="/paper" className="font-medium text-foreground">
              Paper
            </Link>
            <span>·</span>
            <Link href="/live" className="font-medium text-foreground">
              Live
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

