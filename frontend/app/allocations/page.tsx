import { PageHeader } from "../_components/PageHeader";
import { Card, CardContent } from "../_components/ui/Card";

export default function AllocationsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Allocations" description="Allocation UI is coming next; this page is a placeholder." />
      <Card className="shadow-none">
        <CardContent className="text-sm text-muted-foreground">
          Use the API endpoints under <code className="rounded bg-muted px-1.5 py-0.5">/api</code> for now.
        </CardContent>
      </Card>
    </div>
  );
}

