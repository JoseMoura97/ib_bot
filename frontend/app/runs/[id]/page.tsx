import { RunDetailsClient } from "./RunDetailsClient";

export default async function RunPage(props: { params: Promise<{ id: string }> }) {
  const { id } = await props.params;
  return <RunDetailsClient runId={id} />;
}

