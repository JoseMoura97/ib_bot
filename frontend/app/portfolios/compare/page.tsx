import { CompareClient } from "./CompareClient";

export default async function ComparePage(props: {
  searchParams: Promise<{ runs?: string | string[] }>;
}) {
  const sp = await props.searchParams;
  const raw = sp?.runs;
  const ids = (Array.isArray(raw) ? raw : raw ? raw.split(",") : [])
    .map((s) => s.trim())
    .filter(Boolean);
  return <CompareClient runIds={ids} />;
}
