import { RunDetailsClient } from "./RunDetailsClient";

export default function RunPage(props: { params: { id: string } }) {
  return <RunDetailsClient runId={props.params.id} />;
}

