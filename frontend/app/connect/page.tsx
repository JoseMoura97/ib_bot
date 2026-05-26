import { PageHeader } from "../_components/PageHeader";
import { ConnectClient } from "./ConnectClient";

export default function ConnectPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Connect IB Account"
        description="Link your Interactive Brokers account to start automated trading. Takes about 2 minutes."
      />
      <ConnectClient />
    </div>
  );
}
