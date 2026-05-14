"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "../_components/ui/Button";
import { Card, CardContent } from "../_components/ui/Card";
import { Input } from "../_components/ui/Input";
import { Select } from "../_components/ui/Select";
import { Table, TableWrap, Td, Th } from "../_components/ui/Table";
import { cn } from "../_components/cn";

type IbAccount = { account_id: string };

type Snapshot = {
  account_id: string;
  host: string;
  port: number;
  cash_by_currency: Record<string, number>;
  key: Record<string, Record<string, number>>;
  positions: Array<{
    position: number;
    avgCost: number;
    contract: { symbol?: string; localSymbol?: string; secType?: string; currency?: string; exchange?: string };
  }>;
};

type IbStatus = { connected: boolean; host: string; port: number; accounts?: string[]; error?: string };
type PortfolioOption = { id: string; name: string };
type RebalancePreview = {
  allocation_amount: number;
  estimated_notional: number;
  legs: Array<{
    ticker: string;
    side: string;
    delta_quantity: number;
    price: number;
    target_weight: number;
  }>;
};
type LiveAuditRow = {
  id: string;
  created_at: string;
  action: string;
  status: string;
  error?: string | null;
  account_id?: string | null;
  portfolio_id?: string | null;
  allocation_amount?: number | null;
  max_notional_usd?: number | null;
  max_percent_nlv?: number | null;
  max_orders?: number | null;
  allow_short?: boolean;
};

function fmtNum(v: any, digits = 2): string {
  const x = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(x)) return "—";
  return x.toFixed(digits);
}

export function LiveAccountsClient() {
  const [status, setStatus] = useState<IbStatus | null>(null);
  const [accounts, setAccounts] = useState<IbAccount[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [host, setHost] = useState<string>("");
  const [port, setPort] = useState<string>("");
  const [extraAccounts, setExtraAccounts] = useState<string>("");

  const [portfolios, setPortfolios] = useState<PortfolioOption[]>([]);
  const [portfolioId, setPortfolioId] = useState<string>("");
  const [allocationAmount, setAllocationAmount] = useState<string>("10000");
  const [maxNotionalUsd, setMaxNotionalUsd] = useState<string>("25000");
  const [maxPercentNlv, setMaxPercentNlv] = useState<string>("0.2");
  const [maxOrders, setMaxOrders] = useState<string>("25");
  const [allowShort, setAllowShort] = useState(false);
  const [confirmExecute, setConfirmExecute] = useState(false);
  const [preview, setPreview] = useState<RebalancePreview | null>(null);
  const [rebalanceErr, setRebalanceErr] = useState<string | null>(null);
  const [rebalanceBusy, setRebalanceBusy] = useState<string | null>(null);
  const [auditRows, setAuditRows] = useState<LiveAuditRow[]>([]);

  const [halted, setHalted] = useState(false);
  const [dryRunResult, setDryRunResult] = useState<any>(null);
  const [checklistResult, setChecklistResult] = useState<any>(null);
  const [safetyBusy, setSafetyBusy] = useState<string | null>(null);
  const [connOpen, setConnOpen] = useState(true);
  const [posFilter, setPosFilter] = useState("");

  async function onHalt() {
    setSafetyBusy("halt");
    try {
      const res = await fetch("/api/live/halt", { method: "POST" });
      const data = await res.json();
      setHalted(data.halted ?? true);
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setSafetyBusy(null);
    }
  }

  async function onResume() {
    setSafetyBusy("resume");
    try {
      const res = await fetch("/api/live/resume", { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setHalted(data.halted ?? false);
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setSafetyBusy(null);
    }
  }

  async function onDryRun() {
    if (!selected || !portfolioId) return;
    setSafetyBusy("dryrun");
    setDryRunResult(null);
    try {
      const body = {
        account_id: selected,
        portfolio_id: portfolioId,
        allocation_amount: Number(allocationAmount) || 0,
        max_notional_usd: parseFloatSafe(maxNotionalUsd),
        max_percent_nlv: parseFloatSafe(maxPercentNlv),
        max_orders: Number(maxOrders) || 25,
        allow_short: allowShort,
        confirm: false,
      };
      const res = await fetch("/api/live/rebalance/dry-run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      setDryRunResult(await res.json());
      await loadAudit();
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setSafetyBusy(null);
    }
  }

  async function onRunChecklist() {
    if (!selected || !portfolioId) return;
    setSafetyBusy("checklist");
    setChecklistResult(null);
    try {
      const body = {
        account_id: selected,
        portfolio_id: portfolioId,
        allocation_amount: Number(allocationAmount) || 0,
        max_notional_usd: parseFloatSafe(maxNotionalUsd),
        max_percent_nlv: parseFloatSafe(maxPercentNlv),
        max_orders: Number(maxOrders) || 25,
        allow_short: allowShort,
        confirm: false,
      };
      const res = await fetch("/api/live/checklist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      setChecklistResult(await res.json());
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setSafetyBusy(null);
    }
  }

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("ib.extraAccounts") || "";
      if (saved) setExtraAccounts(saved);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem("ib.extraAccounts", extraAccounts);
    } catch {
      // ignore
    }
  }, [extraAccounts]);

  const extraQuery = extraAccounts.trim() ? `?extra_accounts=${encodeURIComponent(extraAccounts.trim())}` : "";

  async function loadStatusAndAccounts() {
    setErr(null);
    setLoading(true);
    try {
      const sRes = await fetch(`/api/ib/status${extraQuery}`, { cache: "no-store" });
      const s = (await sRes.json()) as IbStatus;
      setStatus(s);
      setHost(String(s.host ?? ""));
      setPort(String(s.port ?? ""));

      try {
        const liveStatusRes = await fetch("/api/live/status", { cache: "no-store" });
        const liveStatus = await liveStatusRes.json();
        setHalted(!!liveStatus.halted);
      } catch {
        // ignore
      }

      const aRes = await fetch(`/api/ib/accounts${extraQuery}`, { cache: "no-store" });
      if (!aRes.ok) throw new Error(`IB accounts error ${aRes.status}`);
      const a = (await aRes.json()) as IbAccount[];
      setAccounts(a || []);

      const first = (a || [])[0]?.account_id || "";
      setSelected((cur) => cur || first);
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function loadSnapshot(accountId: string) {
    if (!accountId) return;
    setErr(null);
    setLoading(true);
    try {
      const res = await fetch(`/api/ib/accounts/${encodeURIComponent(accountId)}/snapshot`, { cache: "no-store" });
      if (!res.ok) throw new Error(`IB snapshot error ${res.status}`);
      const data = (await res.json()) as Snapshot;
      setSnapshot(data);
    } catch (e: any) {
      setSnapshot(null);
      setErr(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function loadPortfolios() {
    try {
      const res = await fetch("/api/portfolios", { cache: "no-store" });
      if (!res.ok) throw new Error(`Portfolios error ${res.status}`);
      const rows = (await res.json()) as Array<{ id: string; name: string }>;
      setPortfolios(rows || []);
      if (!portfolioId && rows?.[0]?.id) setPortfolioId(rows[0].id);
    } catch {
      // ignore
    }
  }

  async function loadAudit() {
    try {
      const res = await fetch("/api/live/audit?limit=20", { cache: "no-store" });
      if (!res.ok) throw new Error(`Live audit error ${res.status}`);
      const rows = (await res.json()) as LiveAuditRow[];
      setAuditRows(rows || []);
    } catch {
      // ignore
    }
  }

  function parseFloatSafe(v: string): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  async function previewRebalance() {
    if (!selected || !portfolioId) return;
    setRebalanceErr(null);
    setPreview(null);
    setRebalanceBusy("preview");
    try {
      const body = {
        account_id: selected,
        portfolio_id: portfolioId,
        allocation_amount: Number(allocationAmount) || 0,
        max_notional_usd: parseFloatSafe(maxNotionalUsd),
        max_percent_nlv: parseFloatSafe(maxPercentNlv),
        max_orders: Number(maxOrders) || 25,
        allow_short: allowShort,
        confirm: false,
      };
      const res = await fetch("/api/live/rebalance/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as RebalancePreview;
      setPreview(data);
      await loadAudit();
    } catch (e: any) {
      setRebalanceErr(String(e?.message || e));
    } finally {
      setRebalanceBusy(null);
    }
  }

  async function executeRebalance() {
    if (!selected || !portfolioId) return;
    setRebalanceErr(null);
    setRebalanceBusy("execute");
    try {
      const body = {
        account_id: selected,
        portfolio_id: portfolioId,
        allocation_amount: Number(allocationAmount) || 0,
        max_notional_usd: parseFloatSafe(maxNotionalUsd),
        max_percent_nlv: parseFloatSafe(maxPercentNlv),
        max_orders: Number(maxOrders) || 25,
        allow_short: allowShort,
        confirm: confirmExecute,
      };
      const idempotencyKey = crypto.randomUUID();
      const res = await fetch("/api/live/rebalance/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as RebalancePreview;
      setPreview(data);
      await loadAudit();
      setConfirmExecute(false);
    } catch (e: any) {
      setRebalanceErr(String(e?.message || e));
    } finally {
      setRebalanceBusy(null);
    }
  }

  async function connectToIb() {
    setErr(null);
    setLoading(true);
    try {
      const res = await fetch("/api/ib/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ host: String(host || "").trim(), port: Number(port) }),
      });
      const s = (await res.json()) as IbStatus;
      setStatus(s);
      await loadStatusAndAccounts();
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStatusAndAccounts();
  }, []);

  useEffect(() => {
    if (status?.connected) setConnOpen(false);
  }, [status?.connected]);

  useEffect(() => {
    if (selected) loadSnapshot(selected);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  useEffect(() => {
    loadPortfolios();
    loadAudit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const cashRows = useMemo(() => {
    const c = snapshot?.cash_by_currency || {};
    return Object.keys(c)
      .sort()
      .map((ccy) => ({ ccy, val: c[ccy] }));
  }, [snapshot]);

  const keyRows = useMemo(() => {
    const k = snapshot?.key || {};
    const tags = Object.keys(k).sort();
    const out: Array<{ tag: string; ccy: string; val: number }> = [];
    for (const tag of tags) {
      const byCcy = k[tag] || {};
      for (const ccy of Object.keys(byCcy).sort()) {
        out.push({ tag, ccy, val: byCcy[ccy] });
      }
    }
    return out;
  }, [snapshot]);

  const noAccountData =
    !!snapshot && cashRows.length === 0 && keyRows.length === 0 && (snapshot.positions?.length || 0) === 0;

  const nlv = useMemo(() => {
    const k = snapshot?.key?.NetLiquidation || snapshot?.key?.["NetLiquidation"];
    if (k && typeof k === "object") {
      const usd = (k as Record<string, number>).USD;
      if (typeof usd === "number" && Number.isFinite(usd)) return usd;
      const first = Object.values(k as Record<string, number>)[0];
      if (typeof first === "number") return first;
    }
    return undefined;
  }, [snapshot]);

  const cashUsd = snapshot?.cash_by_currency?.USD;

  const filteredPositions = useMemo(() => {
    const rows = snapshot?.positions || [];
    const q = posFilter.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((p) => {
      const sym = (p.contract?.symbol || p.contract?.localSymbol || "").toLowerCase();
      return sym.includes(q);
    });
  }, [snapshot?.positions, posFilter]);

  return (
    <section className="space-y-4">
      <header className="sticky top-0 z-30 -mx-1 flex flex-wrap items-center justify-between gap-3 border-b bg-background/90 px-1 py-3 backdrop-blur-md">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <span
            className={cn("h-2.5 w-2.5 shrink-0 rounded-full", status?.connected ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]" : "bg-red-500")}
            title={status?.connected ? "Connected" : "Disconnected"}
          />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{status?.connected ? "IB connected" : "IB disconnected"}</div>
            <div className="truncate text-xs text-muted-foreground">
              {status ? `${status.host}:${status.port}` : "…"}
              {selected ? ` · ${selected}` : ""}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={selected} onChange={(e) => setSelected(e.target.value)} className="min-w-[140px]">
            {(accounts || []).map((a) => (
              <option key={a.account_id} value={a.account_id}>
                {a.account_id}
              </option>
            ))}
            {!accounts.length ? <option value="">No accounts</option> : null}
          </Select>
          {!halted ? (
            <Button size="sm" variant="secondary" className="bg-red-600 text-white hover:bg-red-700" onClick={onHalt} disabled={safetyBusy === "halt"}>
              {safetyBusy === "halt" ? "…" : "Halt"}
            </Button>
          ) : (
            <Button size="sm" variant="outline" onClick={onResume} disabled={safetyBusy === "resume"}>
              Resume
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => loadSnapshot(selected)} disabled={loading || !selected}>
            Refresh
          </Button>
        </div>
      </header>

      <details className="rounded-xl border bg-card shadow-none" open={connOpen} onToggle={(e) => setConnOpen((e.target as HTMLDetailsElement).open)}>
        <summary className="cursor-pointer px-4 py-3 text-sm font-semibold">Connection &amp; session</summary>
        <div className="space-y-3 border-t px-4 py-4">
          <p className="text-xs text-muted-foreground">
            {status
              ? status.connected
                ? `Connected to ${status.host}:${status.port}`
                : `Not connected — ${status.error ?? "configure host/port and connect"}`
              : "Loading status…"}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Input value={host} onChange={(e) => setHost(e.target.value)} placeholder="Host" className="w-40" disabled={loading} />
            <Input value={port} onChange={(e) => setPort(e.target.value)} placeholder="Port" inputMode="numeric" className="w-24" disabled={loading} />
            <Input
              value={extraAccounts}
              onChange={(e) => setExtraAccounts(e.target.value)}
              placeholder="Extra accounts (comma-separated)"
              className="min-w-[200px] flex-1"
              disabled={loading}
            />
            <Button size="sm" variant="primary" onClick={() => connectToIb()} disabled={loading || !host || !port}>
              Connect
            </Button>
            <Button size="sm" variant="outline" onClick={() => loadStatusAndAccounts()} disabled={loading}>
              Reload accounts
            </Button>
          </div>
        </div>
      </details>

      {err ? (
        <Card className="shadow-none">
          <CardContent className="py-4 text-sm text-destructive">{err}</CardContent>
        </Card>
      ) : null}

      {noAccountData ? (
        <Card className="shadow-none">
          <CardContent className="py-4 text-sm text-muted-foreground">
            IB returned no balances/positions for this account. This usually means the current API session ({host}:{port})
            doesn’t have access to that account. Try connecting to the IB instance/port that owns it (e.g. Live/TWS), or
            log in with the correct user that has permission.
          </CardContent>
        </Card>
      ) : null}

      {snapshot ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {(cashUsd != null && Number.isFinite(cashUsd)) || (nlv != null && Number.isFinite(nlv)) ? (
            <Card className="shadow-none lg:col-span-2">
              <CardContent className="grid gap-4 py-4 sm:grid-cols-2">
                <div>
                  <div className="text-xs font-medium text-muted-foreground">Net liquidation</div>
                  <div className="mt-1 text-2xl font-bold tabular-nums">{nlv != null ? `$${fmtNum(nlv, 2)}` : "—"}</div>
                </div>
                <div>
                  <div className="text-xs font-medium text-muted-foreground">Cash (USD)</div>
                  <div className="mt-1 text-2xl font-bold tabular-nums">{cashUsd != null ? `$${fmtNum(cashUsd, 2)}` : "—"}</div>
                </div>
              </CardContent>
            </Card>
          ) : null}

          <Card className="shadow-none">
            <CardContent className="space-y-3 py-4">
              <div className="text-sm font-semibold">Cash by currency</div>
              <TableWrap>
                <Table>
                  <thead>
                    <tr>
                      <Th>Currency</Th>
                      <Th className="text-right">TotalCashValue</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {cashRows.map((r) => (
                      <tr key={r.ccy}>
                        <Td className="font-semibold">{r.ccy}</Td>
                        <Td className="text-right font-mono">{fmtNum(r.val, 2)}</Td>
                      </tr>
                    ))}
                    {!cashRows.length ? (
                      <tr>
                        <Td colSpan={2} className="text-muted-foreground">
                          No cash rows returned (IB may not provide TotalCashValue by currency for this account).
                        </Td>
                      </tr>
                    ) : null}
                  </tbody>
                </Table>
              </TableWrap>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardContent className="space-y-3 py-4">
              <div className="text-sm font-semibold">Key balances</div>
              <TableWrap>
                <Table>
                  <thead>
                    <tr>
                      <Th>Tag</Th>
                      <Th>Currency</Th>
                      <Th className="text-right">Value</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {keyRows.map((r, i) => (
                      <tr key={`${r.tag}:${r.ccy}:${i}`}>
                        <Td className="font-semibold">{r.tag}</Td>
                        <Td>{r.ccy}</Td>
                        <Td className="text-right font-mono">{fmtNum(r.val, 2)}</Td>
                      </tr>
                    ))}
                    {!keyRows.length ? (
                      <tr>
                        <Td colSpan={3} className="text-muted-foreground">
                          No key balances returned.
                        </Td>
                      </tr>
                    ) : null}
                  </tbody>
                </Table>
              </TableWrap>
            </CardContent>
          </Card>

          <Card className="shadow-none lg:col-span-2">
            <CardContent className="space-y-3 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="text-sm font-semibold">Positions</div>
                <Input
                  value={posFilter}
                  onChange={(e) => setPosFilter(e.target.value)}
                  placeholder="Filter symbol…"
                  className="h-8 max-w-xs text-sm"
                />
              </div>
              <TableWrap>
                <Table>
                  <thead>
                    <tr>
                      <Th>Symbol</Th>
                      <Th>Type</Th>
                      <Th>Currency</Th>
                      <Th className="text-right">Position</Th>
                      <Th className="text-right">Avg cost</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPositions.map((p, idx) => (
                      <tr key={idx}>
                        <Td className={cn("font-semibold", p.position > 0 && "text-emerald-600", p.position < 0 && "text-red-600")}>
                          {p.contract?.symbol || p.contract?.localSymbol || "—"}
                        </Td>
                        <Td className="text-muted-foreground">{p.contract?.secType || "—"}</Td>
                        <Td className="text-muted-foreground">{p.contract?.currency || "—"}</Td>
                        <Td className="text-right font-mono">{fmtNum(p.position, 4)}</Td>
                        <Td className="text-right font-mono">{fmtNum(p.avgCost, 4)}</Td>
                      </tr>
                    ))}
                    {!filteredPositions.length ? (
                      <tr>
                        <Td colSpan={5} className="text-muted-foreground">
                          {snapshot.positions?.length ? "No matches." : "No positions."}
                        </Td>
                      </tr>
                    ) : null}
                  </tbody>
                </Table>
              </TableWrap>
            </CardContent>
          </Card>
        </div>
      ) : null}

      <Card className={`shadow-none ${halted ? "border-red-500/50 bg-red-500/5" : ""}`}>
        <CardContent className="space-y-3 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">Pre-flight checks</div>
              <div className="text-xs text-muted-foreground">
                {halted
                  ? "Trading is halted — resume from the top bar when ready."
                  : "Validate the book and simulate orders before any live rebalance."}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" onClick={onRunChecklist} disabled={safetyBusy === "checklist" || !selected || !portfolioId}>
                {safetyBusy === "checklist" ? "Running…" : "Run checklist"}
              </Button>
              <Button size="sm" variant="outline" onClick={onDryRun} disabled={safetyBusy === "dryrun" || !selected || !portfolioId}>
                {safetyBusy === "dryrun" ? "Running…" : "Dry run"}
              </Button>
            </div>
          </div>

          {checklistResult ? (
            <div className="space-y-2">
              <div className={`text-xs font-semibold ${checklistResult.all_pass ? "text-emerald-600" : "text-red-500"}`}>
                Checklist: {checklistResult.all_pass ? "ALL PASS" : "FAILED"}
              </div>
              <TableWrap>
                <Table>
                  <thead>
                    <tr>
                      <Th>Check</Th>
                      <Th className="w-[80px]">Status</Th>
                      <Th>Detail</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {(checklistResult.checks || []).map((c: any, i: number) => (
                      <tr key={i} className="hover:bg-accent/40">
                        <Td className="font-medium">{c.check?.replace(/_/g, " ")}</Td>
                        <Td className={c.pass ? "text-emerald-600 font-semibold" : "text-red-500 font-semibold"}>
                          {c.pass ? "PASS" : "FAIL"}
                        </Td>
                        <Td className="text-xs text-muted-foreground">{c.detail || ""}</Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </TableWrap>
            </div>
          ) : null}

          {dryRunResult ? (
            <div className="space-y-2">
              <div className="text-xs font-semibold text-amber-600">
                DRY RUN: {dryRunResult.orders?.length || 0} orders, notional=$
                {fmtNum(dryRunResult.estimated_notional, 2)}
              </div>
              <TableWrap>
                <Table>
                  <thead>
                    <tr>
                      <Th>Symbol</Th>
                      <Th>Side</Th>
                      <Th className="text-right">Qty</Th>
                      <Th className="text-right">Price</Th>
                      <Th className="text-right">Notional</Th>
                      <Th>Status</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {(dryRunResult.orders || []).map((o: any, i: number) => (
                      <tr key={i} className="hover:bg-accent/40">
                        <Td className="font-semibold">{o.ticker}</Td>
                        <Td>{o.side}</Td>
                        <Td className="text-right font-mono">{o.quantity}</Td>
                        <Td className="text-right font-mono">{fmtNum(o.price, 2)}</Td>
                        <Td className="text-right font-mono">{fmtNum(o.notional, 2)}</Td>
                        <Td className="text-amber-600 font-semibold">{o.status}</Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </TableWrap>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="shadow-none">
        <CardContent className="space-y-4 py-4">
          <div>
            <div className="text-sm font-semibold">Live rebalance</div>
            <p className="mt-1 text-xs text-muted-foreground">
              Requires <code className="rounded bg-muted px-1">ENABLE_LIVE_TRADING=1</code>. Preview only simulates; execute sends real orders after you confirm.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-2">
              <div className="text-xs text-muted-foreground">Portfolio</div>
              <Select value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)}>
                {(portfolios || []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
                {!portfolios.length ? <option value="">No portfolios</option> : null}
              </Select>
            </div>
            <div className="space-y-2">
              <div className="text-xs text-muted-foreground">Allocation amount (USD)</div>
              <Input value={allocationAmount} onChange={(e) => setAllocationAmount(e.target.value)} inputMode="decimal" />
            </div>
            <div className="space-y-2">
              <div className="text-xs text-muted-foreground">Max orders</div>
              <Input value={maxOrders} onChange={(e) => setMaxOrders(e.target.value)} inputMode="numeric" />
            </div>
            <div className="space-y-2">
              <div className="text-xs text-muted-foreground">Max notional (USD)</div>
              <Input value={maxNotionalUsd} onChange={(e) => setMaxNotionalUsd(e.target.value)} inputMode="decimal" />
            </div>
            <div className="space-y-2">
              <div className="text-xs text-muted-foreground">Max % of NLV (0-1)</div>
              <Input value={maxPercentNlv} onChange={(e) => setMaxPercentNlv(e.target.value)} inputMode="decimal" />
            </div>
            <div className="flex items-end gap-2">
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <input type="checkbox" checked={allowShort} onChange={(e) => setAllowShort(e.target.checked)} />
                Allow short
              </label>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" onClick={previewRebalance} disabled={rebalanceBusy === "preview"}>
              {rebalanceBusy === "preview" ? "Previewing…" : "Preview"}
            </Button>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input type="checkbox" checked={confirmExecute} onChange={(e) => setConfirmExecute(e.target.checked)} />
              Confirm execute
            </label>
            <Button
              size="sm"
              variant="destructive"
              onClick={executeRebalance}
              disabled={rebalanceBusy === "execute" || !confirmExecute}
            >
              {rebalanceBusy === "execute" ? "Executing…" : "Execute live"}
            </Button>
          </div>

          {rebalanceErr ? (
            <Card className="border-destructive/30 bg-destructive/10 shadow-none">
              <CardContent className="py-4 text-sm text-destructive">{rebalanceErr}</CardContent>
            </Card>
          ) : null}

          {preview ? (
            <TableWrap>
              <Table>
                <thead>
                  <tr>
                    <Th>Symbol</Th>
                    <Th>Side</Th>
                    <Th className="text-right">Qty</Th>
                    <Th className="text-right">Price</Th>
                    <Th className="text-right">Target weight</Th>
                  </tr>
                </thead>
                <tbody>
                  {preview.legs.map((l, i) => (
                    <tr key={`${l.ticker}-${i}`} className="hover:bg-accent/40">
                      <Td className="font-semibold">{l.ticker}</Td>
                      <Td>{l.side}</Td>
                      <Td className="text-right font-mono">{fmtNum(l.delta_quantity, 0)}</Td>
                      <Td className="text-right font-mono">{fmtNum(l.price, 2)}</Td>
                      <Td className="text-right font-mono">{(l.target_weight * 100).toFixed(1)}%</Td>
                    </tr>
                  ))}
                  {!preview.legs.length ? (
                    <tr>
                      <Td colSpan={5} className="text-muted-foreground">
                        No orders in preview.
                      </Td>
                    </tr>
                  ) : null}
                </tbody>
              </Table>
            </TableWrap>
          ) : null}
        </CardContent>
      </Card>

      <details className="rounded-xl border bg-card shadow-none">
        <summary className="cursor-pointer px-4 py-3 text-sm font-semibold">Audit log ({auditRows.length})</summary>
        <CardContent className="space-y-3 border-t py-4">
          <div className="flex justify-end">
            <Button size="sm" variant="outline" onClick={() => loadAudit()}>
              Reload
            </Button>
          </div>
          <div className="space-y-3">
            {(auditRows || []).map((r) => (
              <div key={r.id} className="flex flex-wrap gap-x-4 gap-y-1 border-b border-border/60 pb-3 text-sm last:border-0">
                <div className="text-xs text-muted-foreground">{r.created_at ? new Date(r.created_at).toLocaleString() : "—"}</div>
                <div className="font-semibold">{r.action}</div>
                <div className="text-xs">{r.status}</div>
                <div className="font-mono text-xs text-muted-foreground">{r.account_id || "—"}</div>
                <div className="ml-auto font-mono text-xs">{r.allocation_amount ? `$${fmtNum(r.allocation_amount, 2)}` : "—"}</div>
              </div>
            ))}
            {!auditRows.length ? <p className="text-sm text-muted-foreground">No audit records yet.</p> : null}
          </div>
        </CardContent>
      </details>
    </section>
  );
}

