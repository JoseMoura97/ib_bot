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

import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "./_components/ui/Card";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Welcome</h1>
        <p className="text-sm text-muted-foreground">Use the sidebar to navigate. Start with Paper Trading.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Paper Trading</CardTitle>
          </CardHeader>
          <CardContent>
            <Link className="text-sm font-medium hover:underline" href="/paper">
              Open paper dashboard →
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./_components/ui/Card";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1>Welcome</h1>
        <p className="text-sm text-muted-foreground">
          FastAPI + Next.js control panel for backtests, strategies, portfolios, and trading status.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Dashboard</CardTitle>
              <CardDescription>Compare strategy curves and metrics.</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <Link className="text-sm font-medium" href="/dashboard">
              Open dashboard →
            </Link>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Strategies</CardTitle>
              <CardDescription>Enable/disable and edit per-strategy config.</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <Link className="text-sm font-medium" href="/strategies">
              Manage strategies →
            </Link>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Portfolios</CardTitle>
              <CardDescription>Inspect portfolios from the API.</CardDescription>
            </div>
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
