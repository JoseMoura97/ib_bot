import { RunDetailsClient } from "./RunDetailsClient";

export default async function RunDetailsPage(props: { params: Promise<{ runId: string }> }) {
  const { runId } = await props.params;
  return <RunDetailsClient runId={runId} />;
}

