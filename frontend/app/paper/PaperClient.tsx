"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { PageHeader } from "../_components/PageHeader";
import { Button } from "../_components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "../_components/ui/Card";
import { Input } from "../_components/ui/Input";

import type { PaperOrderSide } from "./_lib/paperApi";
import {
  fundPaperAccount,
  getPaperSummary,
  listPaperAccounts,
  listPaperFills,
  listPaperOrders,
  listPaperPositions,
  listPortfolios,
  paperRebalanceExecute,
  paperRebalancePreview,
  placePaperMarketOrder,
} from "./_lib/paperApi";

function fmtMoney(n: number | undefined, currency = "USD"): string {
  if (n == null || !Number.isFinite(n)) return "—";
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(n);
  } catch {
    return `${n.toFixed(2)} ${currency}`;
  }
}

function fmtTime(s: string | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleString();
}

export function PaperClient() {
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [accounts, setAccounts] = useState<Array<{ id: number; name: string; balance: number; currency: string }>>([]);
  const [accountId, setAccountId] = useState<number>(1);

  const [summary, setSummary] = useState<any>(null);
  const [positions, setPositions] = useState<any[]>([]);
  const [orders, setOrders] = useState<any[]>([]);
  const [fills, setFills] = useState<any[]>([]);

  const currency = summary?.currency || accounts.find((a) => a.id === accountId)?.currency || "USD";
  const cash = typeof summary?.cash === "number" ? summary.cash : undefined;
  const equity = typeof summary?.equity === "number" ? summary.equity : undefined;
  const updatedAt = summary?.updated_at as string | undefined;

  const [fundAmount, setFundAmount] = useState<string>("10000");
  const [ticker, setTicker] = useState<string>("AAPL");
  const [side, setSide] = useState<PaperOrderSide>("BUY");
  const [quantity, setQuantity] = useState<string>("1");

  const computedEquity = useMemo(() => {
    if (typeof equity === "number" && Number.isFinite(equity)) return equity;
    const cashPart = typeof cash === "number" && Number.isFinite(cash) ? cash : 0;
    const mv = (positions || []).reduce((acc, p) => acc + Number(p.quantity || 0) * Number(p.avg_cost || 0), 0);
    return cashPart + mv;
  }, [cash, equity, positions]);

  // Optional rebalance
  const [portfolios, setPortfolios] = useState<Array<{ id: string; name: string }>>([]);
  const [portfolioId, setPortfolioId] = useState<string>("");
  const [allocationUsd, setAllocationUsd] = useState<string>("10000");
  const [rebalancePreview, setRebalancePreview] = useState<any>(null);
  const [rebalanceErr, setRebalanceErr] = useState<string | null>(null);

  async function refreshAll(id: number) {
    setError(null);
    try {
      const [s, p, o, f] = await Promise.all([
        getPaperSummary(id),
        listPaperPositions(id),
        listPaperOrders(id, 50),
        listPaperFills(id, 50),
      ]);
      if (!mountedRef.current) return;
      setSummary(s);
      setPositions(p);
      setOrders(o);
      setFills(f);
    } catch (e: any) {
      if (!mountedRef.current) return;
      setError(String(e?.message || e));
    }
  }

  useEffect(() => {
    async function boot() {
      setError(null);
      try {
        const acct = await listPaperAccounts();
        if (!mountedRef.current) return;
        setAccounts(acct);
        const first = acct[0]?.id ?? 1;
        setAccountId(first);
        await refreshAll(first);
      } catch (e: any) {
        if (!mountedRef.current) return;
        setError(String(e?.message || e));
      }
    }
    boot();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    listPortfolios()
      .then((rows) => {
        if (!mountedRef.current) return;
        setPortfolios(rows);
        if (!portfolioId && rows[0]?.id) setPortfolioId(rows[0].id);
      })
      .catch(() => {
        // ignore
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onChangeAccount(nextId: number) {
    setAccountId(nextId);
    setRebalancePreview(null);
    setRebalanceErr(null);
    await refreshAll(nextId);
  }

  async function onFund() {
    const amt = Number(fundAmount);
    if (!Number.isFinite(amt) || amt <= 0) return;
    setBusy("fund");
    setError(null);
    try {
      await fundPaperAccount(accountId, amt);
      await refreshAll(accountId);
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setBusy(null);
    }
  }

  async function onSubmitOrder() {
    const qty = Number(quantity);
    const sym = ticker.trim().toUpperCase();
    if (!sym || !Number.isFinite(qty) || qty <= 0) return;

    setBusy("order");
    setError(null);
    const submittedAt = new Date();
    try {
      await placePaperMarketOrder({ accountId, ticker: sym, side, quantity: qty });

      // Poll a bit to ensure the trade is visible and balances update.
      for (let i = 0; i < 8; i++) {
        // eslint-disable-next-line no-await-in-loop
        await refreshAll(accountId);
        const newest = fills?.[0];
        const newestTs = newest?.timestamp ? new Date(newest.timestamp) : null;
        if (newest?.ticker === sym && newestTs && newestTs >= submittedAt) break;
        // eslint-disable-next-line no-await-in-loop
        await new Promise((r) => setTimeout(r, 400));
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setBusy(null);
    }
  }

  async function onPreviewRebalance() {
    const amt = Number(allocationUsd);
    if (!portfolioId || !Number.isFinite(amt) || amt <= 0) return;
    setBusy("rebalance-preview");
    setRebalanceErr(null);
    setRebalancePreview(null);
    try {
      const out = await paperRebalancePreview({ accountId, portfolioId, allocationUsd: amt });
      setRebalancePreview(out);
    } catch (e: any) {
      setRebalanceErr(String(e?.message || e));
    } finally {
      setBusy(null);
    }
  }

  async function onExecuteRebalance() {
    const amt = Number(allocationUsd);
    if (!portfolioId || !Number.isFinite(amt) || amt <= 0) return;
    setBusy("rebalance-exec");
    setRebalanceErr(null);
    try {
      const out = await paperRebalanceExecute({ accountId, portfolioId, allocationUsd: amt });
      setRebalancePreview(out);
      await refreshAll(accountId);
    } catch (e: any) {
      setRebalanceErr(String(e?.message || e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Paper Trading"
        description="Fund a paper account, place market orders, and see fills update cash & positions."
        right={
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs text-muted-foreground">
              Account{" "}
              <select
                className="ml-1 h-9 rounded-md border bg-background px-3 text-sm"
                value={accountId}
                onChange={(e) => onChangeAccount(Number(e.target.value))}
              >
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} (#{a.id})
                  </option>
                ))}
              </select>
            </label>
            <Button onClick={() => refreshAll(accountId)} disabled={!!busy}>
              Refresh
            </Button>
          </div>
        }
      />

      {error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">{error}</div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-4">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Cash</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-semibold">{fmtMoney(cash, currency)}</CardContent>
        </Card>
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Equity</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-semibold">{fmtMoney(computedEquity, currency)}</CardContent>
        </Card>
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Positions</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-semibold">{positions.length}</CardContent>
        </Card>
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Updated</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">{fmtTime(updatedAt)}</CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Fund account</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-2">
            <Input value={fundAmount} onChange={(e) => setFundAmount(e.target.value)} inputMode="decimal" className="max-w-[180px]" />
            <div className="text-sm text-muted-foreground">{currency}</div>
            <Button onClick={onFund} disabled={busy === "fund"}>
              {busy === "fund" ? "Funding…" : "Add cash"}
            </Button>
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Order ticket (market)</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-2">
            <Input value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} className="max-w-[180px]" />
            <select className="h-9 rounded-md border bg-background px-3 text-sm" value={side} onChange={(e) => setSide(e.target.value as PaperOrderSide)}>
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
            </select>
            <Input value={quantity} onChange={(e) => setQuantity(e.target.value)} inputMode="decimal" className="max-w-[140px]" />
            <Button onClick={onSubmitOrder} disabled={busy === "order"}>
              {busy === "order" ? "Submitting…" : "Submit"}
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Positions</CardTitle>
          </CardHeader>
          <CardContent className="overflow-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-3">Ticker</th>
                  <th className="py-2 pr-3">Qty</th>
                  <th className="py-2 pr-3">Avg cost</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.ticker} className="border-b">
                    <td className="py-2 pr-3 font-semibold">{p.ticker}</td>
                    <td className="py-2 pr-3">{Number(p.quantity).toFixed(4)}</td>
                    <td className="py-2 pr-3">{fmtMoney(Number(p.avg_cost), p.currency || currency)}</td>
                  </tr>
                ))}
                {!positions.length ? (
                  <tr>
                    <td colSpan={3} className="py-3 text-sm text-muted-foreground">
                      No positions.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Fills / trades</CardTitle>
          </CardHeader>
          <CardContent className="overflow-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-3">Time</th>
                  <th className="py-2 pr-3">Ticker</th>
                  <th className="py-2 pr-3">Side</th>
                  <th className="py-2 pr-3">Qty</th>
                  <th className="py-2 pr-3">Price</th>
                </tr>
              </thead>
              <tbody>
                {fills.map((t, idx) => (
                  <tr key={`${t.order_id ?? "t"}-${idx}`} className="border-b">
                    <td className="py-2 pr-3 text-xs text-muted-foreground">{fmtTime(t.timestamp)}</td>
                    <td className="py-2 pr-3 font-semibold">{t.ticker}</td>
                    <td className="py-2 pr-3">{t.action}</td>
                    <td className="py-2 pr-3">{Number(t.quantity).toFixed(4)}</td>
                    <td className="py-2 pr-3">{fmtMoney(Number(t.price), currency)}</td>
                  </tr>
                ))}
                {!fills.length ? (
                  <tr>
                    <td colSpan={5} className="py-3 text-sm text-muted-foreground">
                      No fills yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>

      <Card className="shadow-none">
        <CardHeader>
          <CardTitle>Orders</CardTitle>
        </CardHeader>
        <CardContent className="overflow-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="py-2 pr-3">Time</th>
                <th className="py-2 pr-3">Ticker</th>
                <th className="py-2 pr-3">Side</th>
                <th className="py-2 pr-3">Qty</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 pr-3">Fill</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} className="border-b">
                  <td className="py-2 pr-3 text-xs text-muted-foreground">{fmtTime(o.created_at)}</td>
                  <td className="py-2 pr-3 font-semibold">{o.ticker}</td>
                  <td className="py-2 pr-3">{o.action}</td>
                  <td className="py-2 pr-3">{Number(o.quantity).toFixed(4)}</td>
                  <td className="py-2 pr-3">{o.status}</td>
                  <td className="py-2 pr-3">{fmtMoney(Number(o.fill_price), currency)}</td>
                </tr>
              ))}
              {!orders.length ? (
                <tr>
                  <td colSpan={6} className="py-3 text-sm text-muted-foreground">
                    No orders yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {portfolios.length ? (
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Optional: Allocate to portfolio (rebalance)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <select className="h-9 min-w-[260px] rounded-md border bg-background px-3 text-sm" value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)}>
                {portfolios.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <Input
                value={allocationUsd}
                onChange={(e) => setAllocationUsd(e.target.value)}
                inputMode="decimal"
                className="max-w-[180px]"
              />
              <Button onClick={onPreviewRebalance} disabled={busy === "rebalance-preview"}>
                {busy === "rebalance-preview" ? "Previewing…" : "Preview"}
              </Button>
              <Button onClick={onExecuteRebalance} disabled={busy === "rebalance-exec"}>
                {busy === "rebalance-exec" ? "Executing…" : "Execute"}
              </Button>
            </div>
            {rebalanceErr ? <div className="text-sm text-destructive">{rebalanceErr}</div> : null}
            {rebalancePreview ? (
              <pre className="overflow-auto rounded-lg border bg-muted/40 p-4 text-xs">{JSON.stringify(rebalancePreview, null, 2)}</pre>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

