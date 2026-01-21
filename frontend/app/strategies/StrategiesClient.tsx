"use client";

import { useMemo, useState } from "react";
import { PageHeader } from "../_components/PageHeader";
import { Button } from "../_components/ui/Button";
import { Card, CardContent } from "../_components/ui/Card";
import { Input } from "../_components/ui/Input";
import { Textarea } from "../_components/ui/Textarea";

type Strategy = {
  name: string;
  enabled: boolean;
  config: Record<string, unknown>;
};

type SaveState = "idle" | "saving" | "saved" | "error";

function safeJsonParse(input: string): { ok: true; value: any } | { ok: false; error: string } {
  try {
    const v = JSON.parse(input);
    return { ok: true, value: v };
  } catch (e: any) {
    return { ok: false, error: String(e?.message || e) };
  }
}

export function StrategiesClient(props: { initialStrategies: Strategy[] }) {
  const [strategies, setStrategies] = useState<Strategy[]>(props.initialStrategies || []);
  const [filter, setFilter] = useState("");
  const [addName, setAddName] = useState("");

  const [selectedName, setSelectedName] = useState<string | null>(
    (props.initialStrategies && props.initialStrategies[0]?.name) || null,
  );
  const selected = useMemo(
    () => (selectedName ? strategies.find((s) => s.name === selectedName) || null : null),
    [selectedName, strategies],
  );

  const [configText, setConfigText] = useState<string>(() =>
    selected ? JSON.stringify(selected.config ?? {}, null, 2) : "{}",
  );
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return strategies;
    return strategies.filter((s) => s.name.toLowerCase().includes(q));
  }, [strategies, filter]);

  async function refresh() {
    const res = await fetch("/api/strategies", { cache: "no-store" });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    const data = (await res.json()) as Strategy[];
    setStrategies(data);
    // keep selection if possible
    if (selectedName && !data.some((s) => s.name === selectedName)) {
      setSelectedName(data[0]?.name ?? null);
    }
  }

  async function patchStrategy(name: string, patch: Partial<Pick<Strategy, "enabled" | "config">>) {
    const res = await fetch(`/api/strategies/${encodeURIComponent(name)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`API error ${res.status}${txt ? `: ${txt}` : ""}`);
    }
    const updated = (await res.json()) as Strategy;
    setStrategies((prev) => {
      const idx = prev.findIndex((s) => s.name === updated.name);
      if (idx >= 0) {
        const copy = prev.slice();
        copy[idx] = updated;
        return copy;
      }
      return [updated, ...prev].sort((a, b) => a.name.localeCompare(b.name));
    });
    return updated;
  }

  async function onToggleEnabled(name: string, enabled: boolean) {
    setErrorMsg(null);
    try {
      await patchStrategy(name, { enabled });
    } catch (e: any) {
      setErrorMsg(String(e?.message || e));
    }
  }

  async function onAddStrategy() {
    const name = addName.trim();
    if (!name) return;
    setErrorMsg(null);
    setSaveState("idle");
    try {
      const created = await patchStrategy(name, { enabled: true, config: {} });
      setAddName("");
      setSelectedName(created.name);
      setConfigText(JSON.stringify(created.config ?? {}, null, 2));
    } catch (e: any) {
      setErrorMsg(String(e?.message || e));
    }
  }

  function onSelect(name: string) {
    setSelectedName(name);
    const s = strategies.find((x) => x.name === name);
    setConfigText(JSON.stringify(s?.config ?? {}, null, 2));
    setSaveState("idle");
    setErrorMsg(null);
  }

  async function onSaveConfig() {
    if (!selected) return;
    setErrorMsg(null);
    setSaveState("saving");
    const parsed = safeJsonParse(configText);
    if (parsed.ok === false) {
      setSaveState("error");
      setErrorMsg(`Invalid JSON: ${parsed.error}`);
      return;
    }

    if (typeof parsed.value !== "object" || parsed.value === null || Array.isArray(parsed.value)) {
      setSaveState("error");
      setErrorMsg("Config must be a JSON object");
      return;
    }

    try {
      const updated = await patchStrategy(selected.name, { config: parsed.value });
      setSaveState("saved");
      setConfigText(JSON.stringify(updated.config ?? {}, null, 2));
    } catch (e: any) {
      setSaveState("error");
      setErrorMsg(String(e?.message || e));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Strategies" description="Toggle strategies on/off and edit per-strategy config (stored in Postgres)." />

      {errorMsg ? (
        <Card className="border-destructive/30 bg-destructive/10 shadow-none">
          <CardContent className="py-4 text-sm text-destructive">{errorMsg}</CardContent>
        </Card>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <div className="w-64">
          <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search strategies…" />
        </div>
        <div className="w-80">
          <Input value={addName} onChange={(e) => setAddName(e.target.value)} placeholder="Add strategy name (exact)…" />
        </div>
        <Button onClick={onAddStrategy} variant="secondary">
          Add + Enable
        </Button>
        <Button onClick={() => refresh().catch((e) => setErrorMsg(String(e?.message || e)))} variant="outline">
          Refresh
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[420px_1fr]">
        <Card className="shadow-none">
          <CardContent className="p-0">
            <div className="border-b px-4 py-3 text-sm font-semibold">{filtered.length} strategies</div>
            <div className="max-h-[620px] overflow-auto">
              {filtered.map((s) => {
                const isSelected = s.name === selectedName;
                return (
                  <div
                    key={s.name}
                    onClick={() => onSelect(s.name)}
                    className={[
                      "flex cursor-pointer items-center justify-between gap-3 border-b px-4 py-3 transition-colors hover:bg-accent/40",
                      isSelected ? "bg-accent" : "",
                    ].join(" ")}
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{s.name}</div>
                      <div className="text-xs text-muted-foreground">{s.enabled ? "Enabled" : "Disabled"}</div>
                    </div>
                    <label className="flex items-center gap-2 text-xs text-muted-foreground" onClick={(e) => e.stopPropagation()}>
                      <span>Enabled</span>
                      <input
                        type="checkbox"
                        checked={!!s.enabled}
                        onChange={(e) => onToggleEnabled(s.name, e.target.checked)}
                      />
                    </label>
                  </div>
                );
              })}
              {filtered.length === 0 ? (
                <div className="px-4 py-6 text-sm text-muted-foreground">
                  No strategies found. Use “Add + Enable” above (e.g. <code>Congress Buys</code>).
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3">
              <div className="text-sm font-semibold">Config {selected ? `— ${selected.name}` : ""}</div>
              <div className="text-xs text-muted-foreground">
                {saveState === "saved" ? "Saved" : saveState === "error" ? "Error" : ""}
              </div>
            </div>

            {selected ? (
              <>
                <Textarea
                  value={configText}
                  onChange={(e) => {
                    setConfigText(e.target.value);
                    setSaveState("idle");
                  }}
                  spellCheck={false}
                  className="min-h-[460px] font-mono text-xs"
                />
                <div className="flex items-center gap-2">
                  <Button onClick={onSaveConfig} disabled={saveState === "saving"} variant="primary">
                    {saveState === "saving" ? "Saving…" : "Save config"}
                  </Button>
                </div>
              </>
            ) : (
              <div className="text-sm text-muted-foreground">Select a strategy to edit config.</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

