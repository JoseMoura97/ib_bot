import { apiGet } from "../_lib/api";
import { PageHeader } from "../_components/PageHeader";
import { Card, CardContent } from "../_components/ui/Card";
import { CodeBlock } from "../_components/ui/CodeBlock";

export default async function PaperPage() {
  let portfolio: unknown = null;
  let trades: unknown = null;
  let err: string | null = null;
  try {
    [portfolio, trades] = await Promise.all([apiGet("/paper/portfolio"), apiGet("/paper/trades?limit=10")]);
  } catch (e: any) {
    err = String(e?.message || e);
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Paper" description="Paper trading state pulled from the API." />
      {err ? <div className="text-sm text-destructive">Error: {err}</div> : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="shadow-none">
          <CardContent className="space-y-3">
            <div className="text-sm font-medium">Portfolio</div>
            <CodeBlock value={portfolio ?? { hint: "No data yet." }} />
          </CardContent>
        </Card>
        <Card className="shadow-none">
          <CardContent className="space-y-3">
            <div className="text-sm font-medium">Recent trades</div>
            <CodeBlock value={trades ?? { hint: "No data yet." }} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

