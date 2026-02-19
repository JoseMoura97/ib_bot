"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import Link from "next/link";
import { PageHeader } from "../_components/PageHeader";
import { Button } from "../_components/ui/Button";
import { Card, CardContent } from "../_components/ui/Card";
import { Input } from "../_components/ui/Input";
import { Select } from "../_components/ui/Select";
import { Textarea } from "../_components/ui/Textarea";
import { Table, TableWrap, Td, Th } from "../_components/ui/Table";

type SaveState = "idle" | "saving" | "saved" | "error";

type Strategy = {
  name: string;
  enabled: boolean;
  config: Record<string, unknown>;
};

type PortfolioOut = {
  id: string;
  name: string;
  description: string | null;
  default_cash: number;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type PortfolioStrategyIn = {
  strategy_name: string;
  enabled: boolean;
  weight: number;
  overrides: Record<string, unknown>;
};

type PortfolioWithStrategies = PortfolioOut & {
  strategies: PortfolioStrategyIn[];
};

type Mode = "" | "holdings_union" | "nav_blend";

type OptMethod = "equal_weight" | "inverse_volatility" | "risk_parity" | "max_sharpe";

type OptStats = {
  annual_return: number;
  annual_vol: number;
  sharpe: number;
};

type OptResult = {
  method: string;
  weights: Record<string, number>;
  stats: OptStats;
  missing_strategies?: string[];
  available_strategies?: string[];
};

type CompareResult = {
  available_strategies: string[];
  missing_strategies: string[];
  methods: OptResult[];
};

function safeJsonParse(input: string): { ok: true; value: any } | { ok: false; error: string } {
  try {
    const v = JSON.parse(input);
    return { ok: true, value: v };
  } catch (e: any) {
    return { ok: false, error: String(e?.message || e) };
  }
}

async function fetchJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const res = await fetch(input, init);
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`API error ${res.status}${txt ? `: ${txt}` : ""}`);
  }
  return (await res.json()) as T;
}

function formatUsd(n: number): string {
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);
}

export function PortfoliosClient(props: { initialPortfolios: PortfolioOut[]; strategies: Strategy[] }) {
  const [portfolios, setPortfolios] = useState<PortfolioOut[]>(props.initialPortfolios || []);
  const [selectedId, setSelectedId] = useState<string | null>((props.initialPortfolios?.[0]?.id as string) || null);
  const [selected, setSelected] = useState<PortfolioWithStrategies | null>(null);

  const [metaName, setMetaName] = useState("");
  const [metaDesc, setMetaDesc] = useState("");
  const [metaDefaultCash, setMetaDefaultCash] = useState<string>("100000");
  const [settingsText, setSettingsText] = useState<string>("{}");
  const [mode, setMode] = useState<Mode>("");

  const [strategyRows, setStrategyRows] = useState<PortfolioStrategyIn[]>([]);
  const [addStrategyName, setAddStrategyName] = useState<string>("");

  const [editingOverridesFor, setEditingOverridesFor] = useState<string | null>(null);
  const [overridesText, setOverridesText] = useState<string>("{}");

  const [loadError, setLoadError] = useState<string | null>(null);
  const [metaSaveState, setMetaSaveState] = useState<SaveState>("idle");
  const [strategiesSaveState, setStrategiesSaveState] = useState<SaveState>("idle");
  const [infoMsg, setInfoMsg] = useState<string | null>(null);

  const [optMethod, setOptMethod] = useState<OptMethod>("max_sharpe");
  const [optMaxWeight, setOptMaxWeight] = useState("0.30");
  const [optMinWeight, setOptMinWeight] = useState("0.02");
  const [optResult, setOptResult] = useState<OptResult | null>(null);
  const [compareResults, setCompareResults] = useState<CompareResult | null>(null);
  const [optLoading, setOptLoading] = useState(false);

  function startNewPortfolio() {
    setSelectedId(null);
    setSelected(null);
    setMetaName("");
    setMetaDesc("");
    setMetaDefaultCash("100000");
    setSettingsText("{}");
    setMode("");
    setStrategyRows([]);
    setAddStrategyName("");
    setEditingOverridesFor(null);
    setOverridesText("{}");
    setLoadError(null);
    setInfoMsg(null);
    setMetaSaveState("idle");
    setStrategiesSaveState("idle");
  }

  const availableStrategyNames = useMemo(() => {
    const names = (props.strategies || []).map((s) => s.name).filter(Boolean);
    return names.sort((a, b) => a.localeCompare(b));
  }, [props.strategies]);

  const totalWeight = useMemo(() => strategyRows.reduce((sum, r) => sum + (Number.isFinite(r.weight) ? r.weight : 0), 0), [strategyRows]);

  async function refreshPortfolios() {
    const data = await fetchJson<PortfolioOut[]>("/api/portfolios", { cache: "no-store" });
    setPortfolios(data);
    if (selectedId && !data.some((p) => p.id === selectedId)) {
      setSelectedId(data[0]?.id ?? null);
    }
  }

  async function loadPortfolio(id: string) {
    setLoadError(null);
    setInfoMsg(null);
    setMetaSaveState("idle");
    setStrategiesSaveState("idle");
    try {
      const data = await fetchJson<PortfolioWithStrategies>(`/api/portfolios/${encodeURIComponent(id)}`, { cache: "no-store" });
      setSelected(data);
      setMetaName(data.name || "");
      setMetaDesc(data.description || "");
      setMetaDefaultCash(String(data.default_cash ?? 100000));
      const settingsObj = data.settings ?? {};
      setSettingsText(JSON.stringify(settingsObj, null, 2));
      const m = (settingsObj as any)?.mode;
      setMode(m === "holdings_union" || m === "nav_blend" ? m : "");
      setStrategyRows((data.strategies || []).map((s) => ({ ...s, overrides: s.overrides ?? {} })));
      setEditingOverridesFor(null);
      setOverridesText("{}");
    } catch (e: any) {
      setLoadError(String(e?.message || e));
      setSelected(null);
      setStrategyRows([]);
    }
  }

  useEffect(() => {
    refreshPortfolios().catch(() => {
      // ignore; SSR provided initial list
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setSelected(null);
      setStrategyRows([]);
      return;
    }
    loadPortfolio(selectedId).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  function onPickPortfolio(id: string) {
    setSelectedId(id);
  }

  function updateSettingsMode(next: Mode) {
    setMode(next);
    const parsed = safeJsonParse(settingsText);
    if (parsed.ok && typeof parsed.value === "object" && parsed.value && !Array.isArray(parsed.value)) {
      const copy = { ...(parsed.value as Record<string, unknown>) };
      if (!next) delete (copy as any).mode;
      else (copy as any).mode = next;
      setSettingsText(JSON.stringify(copy, null, 2));
    }
  }

  async function onCreatePortfolio() {
    setLoadError(null);
    setInfoMsg(null);
    setMetaSaveState("saving");
    const name = metaName.trim();
    if (!name) {
      setMetaSaveState("error");
      setLoadError("Name is required.");
      return;
    }
    const cash = Number(metaDefaultCash);
    if (!Number.isFinite(cash) || cash <= 0) {
      setMetaSaveState("error");
      setLoadError("Default cash must be a positive number.");
      return;
    }
    const parsed = safeJsonParse(settingsText);
    if ("error" in parsed) {
      setMetaSaveState("error");
      setLoadError(`Settings must be valid JSON. ${parsed.error}`);
      return;
    }
    if (typeof parsed.value !== "object" || parsed.value === null || Array.isArray(parsed.value)) {
      setMetaSaveState("error");
      setLoadError("Settings must be a JSON object.");
      return;
    }

    try {
      const created = await fetchJson<PortfolioOut>("/api/portfolios", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description: metaDesc.trim() ? metaDesc.trim() : null,
          default_cash: cash,
          settings: parsed.value,
        }),
      });
      setMetaSaveState("saved");
      setInfoMsg(`Created portfolio “${created.name}”.`);
      await refreshPortfolios();
      setSelectedId(created.id);
    } catch (e: any) {
      setMetaSaveState("error");
      setLoadError(String(e?.message || e));
    }
  }

  async function onSavePortfolioMeta() {
    if (!selected) return;
    setLoadError(null);
    setInfoMsg(null);
    setMetaSaveState("saving");

    const cash = Number(metaDefaultCash);
    if (!Number.isFinite(cash) || cash <= 0) {
      setMetaSaveState("error");
      setLoadError("Default cash must be a positive number.");
      return;
    }
    const parsed = safeJsonParse(settingsText);
    if ("error" in parsed) {
      setMetaSaveState("error");
      setLoadError(`Settings must be valid JSON. ${parsed.error}`);
      return;
    }
    if (typeof parsed.value !== "object" || parsed.value === null || Array.isArray(parsed.value)) {
      setMetaSaveState("error");
      setLoadError("Settings must be a JSON object.");
      return;
    }

    // Backend may or may not support PATCH/PUT for portfolio fields yet. Best-effort.
    try {
      const updated = await fetchJson<PortfolioOut>(`/api/portfolios/${encodeURIComponent(selected.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: metaName.trim() || selected.name,
          description: metaDesc.trim() ? metaDesc.trim() : null,
          default_cash: cash,
          settings: parsed.value,
        }),
      });
      setMetaSaveState("saved");
      setInfoMsg("Saved portfolio settings.");
      setPortfolios((prev) => prev.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)));
      setSelected((prev) => (prev ? { ...prev, ...updated, strategies: prev.strategies } : prev));
    } catch (e: any) {
      setMetaSaveState("error");
      setLoadError(
        String(e?.message || e) +
          " (If this says 404/405, the backend may not support editing portfolio fields yet; strategies can still be edited below.)",
      );
    }
  }

  function onAddStrategyRow() {
    const name = addStrategyName.trim();
    if (!name) return;
    if (strategyRows.some((r) => r.strategy_name === name)) return;
    setStrategyRows((prev) => [...prev, { strategy_name: name, enabled: true, weight: 0, overrides: {} }]);
    setAddStrategyName("");
    setStrategiesSaveState("idle");
  }

  function onRemoveStrategyRow(name: string) {
    setStrategyRows((prev) => prev.filter((r) => r.strategy_name !== name));
    if (editingOverridesFor === name) {
      setEditingOverridesFor(null);
      setOverridesText("{}");
    }
    setStrategiesSaveState("idle");
  }

  function onNormalizeWeights() {
    const rows = strategyRows.slice();
    const sum = rows.reduce((s, r) => s + (Number.isFinite(r.weight) ? r.weight : 0), 0);
    if (!rows.length) return;
    if (sum > 0) {
      setStrategyRows(rows.map((r) => ({ ...r, weight: r.weight / sum })));
    } else {
      const w = 1 / rows.length;
      setStrategyRows(rows.map((r) => ({ ...r, weight: w })));
    }
    setStrategiesSaveState("idle");
  }

  function onStartEditOverrides(name: string) {
    const row = strategyRows.find((r) => r.strategy_name === name);
    setEditingOverridesFor(name);
    setOverridesText(JSON.stringify(row?.overrides ?? {}, null, 2));
  }

  function onApplyOverrides() {
    if (!editingOverridesFor) return;
    const parsed = safeJsonParse(overridesText);
    if ("error" in parsed) {
      setLoadError(`Overrides must be valid JSON. ${parsed.error}`);
      return;
    }
    if (typeof parsed.value !== "object" || parsed.value === null || Array.isArray(parsed.value)) {
      setLoadError("Overrides must be a JSON object.");
      return;
    }
    setLoadError(null);
    setStrategyRows((prev) =>
      prev.map((r) => (r.strategy_name === editingOverridesFor ? { ...r, overrides: parsed.value as Record<string, unknown> } : r)),
    );
    setStrategiesSaveState("idle");
  }

  async function onOptimize() {
    if (!selected) return;
    setOptLoading(true);
    setOptResult(null);
    setCompareResults(null);
    setLoadError(null);
    try {
      const result = await fetchJson<OptResult>(`/api/portfolios/${encodeURIComponent(selected.id)}/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          method: optMethod,
          max_weight: Number(optMaxWeight) || 0.3,
          min_weight: Number(optMinWeight) || 0.02,
        }),
      });
      setOptResult(result);
    } catch (e: any) {
      setLoadError(String(e?.message || e));
    } finally {
      setOptLoading(false);
    }
  }

  async function onCompareAll() {
    if (!selected) return;
    setOptLoading(true);
    setOptResult(null);
    setCompareResults(null);
    setLoadError(null);
    try {
      const result = await fetchJson<CompareResult>(`/api/portfolios/${encodeURIComponent(selected.id)}/optimize/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          max_weight: Number(optMaxWeight) || 0.3,
          min_weight: Number(optMinWeight) || 0.02,
        }),
      });
      setCompareResults(result);
    } catch (e: any) {
      setLoadError(String(e?.message || e));
    } finally {
      setOptLoading(false);
    }
  }

  function onApplyOptWeights(weights: Record<string, number>) {
    setStrategyRows((prev) =>
      prev.map((r) => {
        const w = weights[r.strategy_name];
        if (w !== undefined) return { ...r, weight: w, enabled: w > 0 };
        return r;
      }),
    );
    setStrategiesSaveState("idle");
    setInfoMsg("Optimized weights applied. Click 'Save strategies' to persist.");
  }

  async function onSaveStrategies() {
    if (!selected) return;
    setLoadError(null);
    setInfoMsg(null);
    setStrategiesSaveState("saving");
    try {
      for (const r of strategyRows) {
        const w = Number(r.weight);
        if (!Number.isFinite(w) || w < 0 || w > 1) {
          setStrategiesSaveState("error");
          setLoadError(`Invalid weight for ${r.strategy_name}: must be between 0 and 1.`);
          return;
        }
      }
      const payload = strategyRows.map((r) => ({
        strategy_name: r.strategy_name,
        enabled: !!r.enabled,
        weight: Number(r.weight) || 0,
        overrides: r.overrides ?? {},
      }));
      const updated = await fetchJson<PortfolioWithStrategies>(`/api/portfolios/${encodeURIComponent(selected.id)}/strategies`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setStrategiesSaveState("saved");
      setInfoMsg("Saved portfolio strategies.");
      setSelected(updated);
      setStrategyRows((updated.strategies || []).map((s) => ({ ...s, overrides: s.overrides ?? {} })));
    } catch (e: any) {
      setStrategiesSaveState("error");
      setLoadError(String(e?.message || e));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Portfolios"
        description="Create portfolios and configure strategy weights."
        right={
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href="/allocations"
              className="inline-flex h-9 items-center justify-center gap-2 whitespace-nowrap rounded-md border bg-background px-4 text-sm font-medium shadow-sm transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              Allocations
            </Link>
            <Button onClick={() => startNewPortfolio()} variant="secondary">
              New portfolio
            </Button>
            <Button onClick={() => refreshPortfolios().catch((e) => setLoadError(String(e?.message || e)))} variant="outline">
              Refresh
            </Button>
          </div>
        }
      />

      {loadError ? (
        <Card className="border-destructive/30 bg-destructive/10 shadow-none">
          <CardContent className="py-4 text-sm text-destructive whitespace-pre-wrap">{loadError}</CardContent>
        </Card>
      ) : null}
      {infoMsg ? (
        <Card className="border-emerald-600/30 bg-emerald-600/10 shadow-none">
          <CardContent className="py-4 text-sm text-emerald-700 dark:text-emerald-300">{infoMsg}</CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[420px_1fr]">
        <Card className="shadow-none">
          <CardContent className="p-0">
            <div className="border-b px-4 py-3 text-sm font-semibold">{portfolios.length} portfolios</div>
            <div className="max-h-[680px] overflow-auto">
              {portfolios.map((p) => {
                const isSelected = p.id === selectedId;
                return (
                  <div
                    key={p.id}
                    onClick={() => onPickPortfolio(p.id)}
                    className={[
                      "cursor-pointer border-b px-4 py-3 transition-colors hover:bg-accent/40",
                      isSelected ? "bg-accent" : "",
                    ].join(" ")}
                  >
                    <div className="truncate text-sm font-semibold">{p.name}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Default cash: {formatUsd(Number(p.default_cash ?? 0))} · Updated:{" "}
                      {p.updated_at ? new Date(p.updated_at).toLocaleString() : "—"}
                    </div>
                  </div>
                );
              })}
              {portfolios.length === 0 ? (
                <div className="px-4 py-6 text-sm text-muted-foreground">No portfolios yet. Create one on the right.</div>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card className="shadow-none">
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3">
                <div className="text-sm font-semibold">{selected ? `Edit portfolio — ${selected.name}` : "Create portfolio"}</div>
                <div className="text-xs text-muted-foreground">
                  {metaSaveState === "saved" ? "Saved" : metaSaveState === "error" ? "Error" : ""}
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1.5">
                  <div className="text-xs font-medium text-muted-foreground">Name</div>
                  <Input value={metaName} onChange={(e) => setMetaName(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <div className="text-xs font-medium text-muted-foreground">Default cash</div>
                  <Input value={metaDefaultCash} onChange={(e) => setMetaDefaultCash(e.target.value)} inputMode="decimal" />
                </div>
                <div className="space-y-1.5 md:col-span-2">
                  <div className="text-xs font-medium text-muted-foreground">Description</div>
                  <Input value={metaDesc} onChange={(e) => setMetaDesc(e.target.value)} />
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-muted-foreground">Mode</span>
                  <Select value={mode} onChange={(e) => updateSettingsMode(e.target.value as Mode)} className="w-auto">
                    <option value="">(none)</option>
                    <option value="holdings_union">holdings_union</option>
                    <option value="nav_blend">nav_blend</option>
                  </Select>
                </div>
                <Button
                  onClick={selected ? onSavePortfolioMeta : onCreatePortfolio}
                  disabled={metaSaveState === "saving"}
                  variant="primary"
                >
                  {metaSaveState === "saving" ? "Saving…" : selected ? "Save portfolio" : "Create portfolio"}
                </Button>
              </div>

              <div className="space-y-1.5">
                <div className="text-xs font-medium text-muted-foreground">Settings (JSON)</div>
                <Textarea
                  value={settingsText}
                  onChange={(e) => {
                    setSettingsText(e.target.value);
                    setMetaSaveState("idle");
                  }}
                  spellCheck={false}
                  className="min-h-[180px] font-mono text-xs"
                />
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3">
                <div className="text-sm font-semibold">Strategies {selected ? "" : "(create a portfolio first)"}</div>
                <div className="text-xs text-muted-foreground">
                  {strategiesSaveState === "saved" ? "Saved" : strategiesSaveState === "error" ? "Error" : ""}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Select value={addStrategyName} onChange={(e) => setAddStrategyName(e.target.value)} disabled={!selected} className="min-w-64">
                  <option value="">Add strategy…</option>
                  {availableStrategyNames.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </Select>
                <Button onClick={onAddStrategyRow} disabled={!selected || !addStrategyName} size="sm" variant="outline">
                  Add
                </Button>
                <Button onClick={onNormalizeWeights} disabled={!selected || strategyRows.length === 0} size="sm" variant="outline">
                  Normalize weights
                </Button>
                <div className="text-xs text-muted-foreground">Total weight: {totalWeight.toFixed(4)}</div>
              </div>

              <TableWrap>
                <Table>
                  <thead>
                    <tr>
                      <Th>Strategy</Th>
                      <Th className="w-[110px]">Enabled</Th>
                      <Th className="w-[160px]">Weight</Th>
                      <Th className="w-[180px]">Overrides</Th>
                      <Th className="w-[120px]" />
                    </tr>
                  </thead>
                  <tbody>
                    {strategyRows.map((r) => (
                      <tr key={r.strategy_name} className="hover:bg-accent/40">
                        <Td className="whitespace-nowrap font-medium">{r.strategy_name}</Td>
                        <Td>
                          <input
                            type="checkbox"
                            checked={!!r.enabled}
                            onChange={(e) => {
                              setStrategyRows((prev) =>
                                prev.map((x) => (x.strategy_name === r.strategy_name ? { ...x, enabled: e.target.checked } : x)),
                              );
                              setStrategiesSaveState("idle");
                            }}
                            disabled={!selected}
                          />
                        </Td>
                        <Td>
                          <Input
                            value={String(r.weight)}
                            onChange={(e) => {
                              const v = Number(e.target.value);
                              setStrategyRows((prev) =>
                                prev.map((x) => (x.strategy_name === r.strategy_name ? { ...x, weight: Number.isFinite(v) ? v : 0 } : x)),
                              );
                              setStrategiesSaveState("idle");
                            }}
                            inputMode="decimal"
                            className="h-8 w-[140px] font-mono text-xs"
                            disabled={!selected}
                          />
                        </Td>
                        <Td>
                          <Button onClick={() => onStartEditOverrides(r.strategy_name)} size="sm" variant="outline" disabled={!selected}>
                            Edit JSON
                          </Button>
                        </Td>
                        <Td>
                          <Button
                            onClick={() => onRemoveStrategyRow(r.strategy_name)}
                            size="sm"
                            variant="ghost"
                            title="Remove from portfolio"
                            disabled={!selected}
                          >
                            Remove
                          </Button>
                        </Td>
                      </tr>
                    ))}
                    {strategyRows.length === 0 ? (
                      <tr>
                        <Td colSpan={5} className="py-6 text-sm text-muted-foreground">
                          No strategies yet. Add one above (weights are 0–1).
                        </Td>
                      </tr>
                    ) : null}
                  </tbody>
                </Table>
              </TableWrap>

              {editingOverridesFor ? (
                <Card className="shadow-none">
                  <CardContent className="space-y-3">
                    <div className="text-sm font-semibold">Overrides — {editingOverridesFor}</div>
                    <Textarea
                      value={overridesText}
                      onChange={(e) => {
                        setOverridesText(e.target.value);
                        setStrategiesSaveState("idle");
                      }}
                      spellCheck={false}
                      className="min-h-[180px] font-mono text-xs"
                    />
                    <div className="flex flex-wrap items-center gap-2">
                      <Button onClick={onApplyOverrides} size="sm" variant="secondary">
                        Apply overrides
                      </Button>
                      <Button
                        onClick={() => {
                          setEditingOverridesFor(null);
                          setOverridesText("{}");
                        }}
                        size="sm"
                        variant="outline"
                      >
                        Close
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ) : null}

              <div className="flex items-center gap-2">
                <Button onClick={onSaveStrategies} disabled={!selected || strategiesSaveState === "saving"} variant="primary">
                  {strategiesSaveState === "saving" ? "Saving…" : "Save strategies"}
                </Button>
              </div>
            </CardContent>
          </Card>

          {selected && strategyRows.length > 0 ? (
            <Card className="shadow-none">
              <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3">
                  <div className="text-sm font-semibold">Weight Optimizer</div>
                  {optLoading ? <div className="text-xs text-muted-foreground">Running...</div> : null}
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <div className="space-y-1">
                    <div className="text-xs font-medium text-muted-foreground">Method</div>
                    <Select value={optMethod} onChange={(e) => setOptMethod(e.target.value as OptMethod)} className="w-auto">
                      <option value="max_sharpe">Max Sharpe</option>
                      <option value="risk_parity">Risk Parity</option>
                      <option value="inverse_volatility">Inverse Volatility</option>
                      <option value="equal_weight">Equal Weight</option>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <div className="text-xs font-medium text-muted-foreground">Max weight</div>
                    <Input value={optMaxWeight} onChange={(e) => setOptMaxWeight(e.target.value)} className="h-9 w-20 font-mono text-xs" />
                  </div>
                  <div className="space-y-1">
                    <div className="text-xs font-medium text-muted-foreground">Min weight</div>
                    <Input value={optMinWeight} onChange={(e) => setOptMinWeight(e.target.value)} className="h-9 w-20 font-mono text-xs" />
                  </div>
                  <div className="flex items-end gap-2 self-end">
                    <Button onClick={onOptimize} disabled={optLoading} variant="primary" size="sm">
                      Optimize
                    </Button>
                    <Button onClick={onCompareAll} disabled={optLoading} variant="outline" size="sm">
                      Compare all
                    </Button>
                  </div>
                </div>

                {optResult ? (
                  <div className="space-y-3">
                    <div className="text-xs font-semibold">
                      {"Result: " + (optResult.method?.replace(/_/g, " ") ?? "")}
                      {optResult.stats?.sharpe != null ? ` | Sharpe ${optResult.stats.sharpe.toFixed(3)}` : ""}
                      {optResult.stats?.annual_return != null ? ` | Return ${(optResult.stats.annual_return * 100).toFixed(1)}%` : ""}
                      {optResult.stats?.annual_vol != null ? ` | Vol ${(optResult.stats.annual_vol * 100).toFixed(1)}%` : ""}
                    </div>
                    <TableWrap>
                      <Table>
                        <thead>
                          <tr>
                            <Th>Strategy</Th>
                            <Th className="w-[120px]">Current</Th>
                            <Th className="w-[120px]">Suggested</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(optResult.weights)
                            .sort(([, a], [, b]) => b - a)
                            .map(([name, w]) => {
                              const current = strategyRows.find((r) => r.strategy_name === name)?.weight ?? 0;
                              return (
                                <tr key={name} className="hover:bg-accent/40">
                                  <Td className="whitespace-nowrap font-medium">{name}</Td>
                                  <Td className="font-mono text-xs">{(current * 100).toFixed(1)}%</Td>
                                  <Td className="font-mono text-xs">{(w * 100).toFixed(1)}%</Td>
                                </tr>
                              );
                            })}
                        </tbody>
                      </Table>
                    </TableWrap>
                    <Button onClick={() => onApplyOptWeights(optResult.weights)} size="sm" variant="secondary">
                      Apply weights
                    </Button>
                  </div>
                ) : null}

                {compareResults ? (
                  <div className="space-y-3">
                    <div className="text-xs font-semibold">Comparison: all methods</div>
                    <TableWrap>
                      <Table>
                        <thead>
                          <tr>
                            <Th>Method</Th>
                            <Th className="w-[100px]">Sharpe</Th>
                            <Th className="w-[100px]">Return</Th>
                            <Th className="w-[100px]">Volatility</Th>
                            <Th className="w-[100px]" />
                          </tr>
                        </thead>
                        <tbody>
                          {compareResults.methods.map((m) => (
                            <tr key={m.method} className="hover:bg-accent/40">
                              <Td className="whitespace-nowrap font-medium">{m.method?.replace(/_/g, " ")}</Td>
                              <Td className="font-mono text-xs">{m.stats?.sharpe?.toFixed(3) ?? "-"}</Td>
                              <Td className="font-mono text-xs">{m.stats?.annual_return != null ? `${(m.stats.annual_return * 100).toFixed(1)}%` : "-"}</Td>
                              <Td className="font-mono text-xs">{m.stats?.annual_vol != null ? `${(m.stats.annual_vol * 100).toFixed(1)}%` : "-"}</Td>
                              <Td>
                                <Button onClick={() => onApplyOptWeights(m.weights)} size="sm" variant="outline">
                                  Apply
                                </Button>
                              </Td>
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    </TableWrap>
                    {compareResults.methods.length > 0 ? (
                      <div className="space-y-2">
                        <div className="text-xs font-semibold">Weight breakdown</div>
                        <TableWrap>
                          <Table>
                            <thead>
                              <tr>
                                <Th>Strategy</Th>
                                {compareResults.methods.map((m) => (
                                  <Th key={m.method} className="w-[100px]">{m.method?.replace(/_/g, " ")}</Th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {compareResults.available_strategies.sort().map((name) => (
                                <tr key={name} className="hover:bg-accent/40">
                                  <Td className="whitespace-nowrap font-medium">{name}</Td>
                                  {compareResults.methods.map((m) => (
                                    <Td key={m.method} className="font-mono text-xs">
                                      {m.weights[name] != null ? `${(m.weights[name] * 100).toFixed(1)}%` : "-"}
                                    </Td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </Table>
                        </TableWrap>
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {(optResult?.missing_strategies?.length ?? 0) > 0 || (compareResults?.missing_strategies?.length ?? 0) > 0 ? (
                  <div className="text-xs text-amber-600 dark:text-amber-400">
                    {"Missing curve data for: " + (optResult?.missing_strategies ?? compareResults?.missing_strategies ?? []).join(", ")}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          <Card className="shadow-none">
            <CardContent className="text-sm text-muted-foreground">
              Tip: If you want weights to sum to 1, click “Normalize weights”. Allocation records live in the allocation ledger (separate API), so
              once you allocate, you can always reconstruct current allocation from history.
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

