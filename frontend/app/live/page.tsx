import { PageHeader } from "../_components/PageHeader";
import { Badge } from "../_components/ui/Badge";
import { LiveAccountsClient } from "./LiveAccountsClient";

export default async function LivePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Live"
        description="Connect to IB Gateway/TWS to view accounts, balances, and positions. Live trading remains guarded."
        right={<Badge variant="outline">Protected</Badge>}
      />
      <LiveAccountsClient />
    </div>
  );
}
