import { apiGet } from "../_lib/api";
import { PageHeader } from "../_components/PageHeader";
import { Badge } from "../_components/ui/Badge";
import { Card, CardContent } from "../_components/ui/Card";
import { CodeBlock } from "../_components/ui/CodeBlock";

export default async function LivePage() {
  const status = await apiGet("/live/status");
  return (
    <div className="space-y-6">
      <PageHeader
        title="Live"
        description="Live trading is guarded and disabled by default."
        right={<Badge variant="outline">Protected</Badge>}
      />
      <Card className="shadow-none">
        <CardContent className="space-y-3">
          <div className="text-sm font-medium">Status</div>
          <CodeBlock value={status} />
        </CardContent>
      </Card>
    </div>
  );
}
