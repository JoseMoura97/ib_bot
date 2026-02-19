import Link from "next/link";
import { Button } from "../../_components/ui/Button";
import { PageHeader } from "../../_components/PageHeader";
import { MetricsTable } from "../MetricsTable";

export default function MetricsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Detailed Metrics"
        description="Compare our strategy metrics against Quiver reference data"
        right={
          <Link href="/dashboard">
            <Button size="sm" variant="outline">
              Back to Dashboard
            </Button>
          </Link>
        }
      />
      <MetricsTable />
    </div>
  );
}
