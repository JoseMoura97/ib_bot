import { apiGet } from "../_lib/api";
import { PageHeader } from "../_components/PageHeader";
import { Card, CardContent } from "../_components/ui/Card";
import { CodeBlock } from "../_components/ui/CodeBlock";

export default async function StrategiesPage() {
  let data: unknown = null;
  let err: string | null = null;
  try {
    data = await apiGet("/strategies");
  } catch (e: any) {
    err = String(e?.message || e);
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Strategies" description="Toggle strategies and edit per-strategy config." />
      <Card className="shadow-none">
        <CardContent className="space-y-3">
          {err ? <div className="text-sm text-destructive">Error: {err}</div> : null}
          <div className="text-sm font-medium">API response</div>
          <CodeBlock value={data ?? { hint: "No data yet." }} />
        </CardContent>
      </Card>
    </div>
  );
}

