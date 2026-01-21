export type PaperAccount = {
  id: string;
  name?: string;
  currency?: string;
};

export type PaperBalance = {
  cash?: number;
  equity?: number;
  currency?: string;
  updated_at?: string;
};

export type PaperPosition = {
  symbol: string;
  quantity: number;
  avg_cost?: number;
  currency?: string;
  market_price?: number;
  market_value?: number;
  updated_at?: string;
};

export type PaperOrderSide = "BUY" | "SELL";

export type PaperOrder = {
  id?: string;
  created_at?: string;
  symbol: string;
  side: PaperOrderSide;
  quantity: number;
  type?: string;
  status?: string;
  avg_fill_price?: number;
};

export type PaperFill = {
  id?: string;
  timestamp?: string;
  symbol: string;
  side: PaperOrderSide;
  quantity: number;
  price?: number;
  value?: number;
  notes?: string;
};

type Json = Record<string, unknown>;

async function readErrorText(res: Response): Promise<string> {
  const txt = await res.text().catch(() => "");
  return txt?.trim() || "";
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { cache: "no-store", ...init });
  if (!res.ok) {
    const txt = await readErrorText(res);
    throw new Error(`API error ${res.status}${txt ? `: ${txt}` : ""}`);
  }
  return (await res.json()) as T;
}

async function tryJson<T>(url: string, init?: RequestInit): Promise<T | null> {
  try {
    return await fetchJson<T>(url, init);
  } catch {
    return null;
  }
}

function coerceNumber(v: unknown): number | undefined {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = Number(v);
    if (Number.isFinite(n)) return n;
  }
  return undefined;
}

function upperSymbol(s: string): string {
  return (s || "").trim().toUpperCase();
}

// ---- Public API (prefers Agent E endpoints, falls back to legacy ones) ----

export async function listPaperAccounts(): Promise<PaperAccount[]> {
  // Preferred (Agent E): GET /paper/accounts
  const a = await tryJson<any>("/api/paper/accounts");
  if (a) {
    const rows = Array.isArray(a) ? a : Array.isArray(a.accounts) ? a.accounts : null;
    if (Array.isArray(rows)) {
      return rows
        .map((r: any) => ({
          id: String(r.id ?? r.account_id ?? r.name ?? "default"),
          name: r.name ? String(r.name) : r.account_name ? String(r.account_name) : undefined,
          currency: r.currency ? String(r.currency) : undefined,
        }))
        .filter((x) => x.id);
    }
  }

  // Legacy fallback: single implicit account
  return [{ id: "default", name: "Paper (legacy)" }];
}

export async function getPaperSummary(accountId: string): Promise<{ balance: PaperBalance; positions: PaperPosition[] }> {
  const aid = accountId || "default";

  // Preferred: GET /paper/accounts/{id}/summary
  const s = await tryJson<any>(`/api/paper/accounts/${encodeURIComponent(aid)}/summary`);
  if (s) {
    const bal: PaperBalance = {
      cash: coerceNumber(s.cash ?? s.cash_balance ?? s.balance?.cash ?? s.balance?.cash_balance),
      equity: coerceNumber(s.equity ?? s.net_liquidation ?? s.balance?.equity ?? s.balance?.net_liquidation),
      currency: typeof s.currency === "string" ? s.currency : typeof s.balance?.currency === "string" ? s.balance.currency : undefined,
      updated_at: typeof s.updated_at === "string" ? s.updated_at : typeof s.balance?.updated_at === "string" ? s.balance.updated_at : undefined,
    };
    const positions = normalizePositions(s.positions ?? s.holdings ?? []);
    return { balance: bal, positions };
  }

  // Alternative: GET /paper/accounts/{id}
  const a = await tryJson<any>(`/api/paper/accounts/${encodeURIComponent(aid)}`);
  if (a) {
    const bal: PaperBalance = {
      cash: coerceNumber(a.cash ?? a.cash_balance ?? a.balance?.cash ?? a.balance?.cash_balance),
      equity: coerceNumber(a.equity ?? a.net_liquidation ?? a.balance?.equity ?? a.balance?.net_liquidation),
      currency: typeof a.currency === "string" ? a.currency : typeof a.balance?.currency === "string" ? a.balance.currency : undefined,
      updated_at: typeof a.updated_at === "string" ? a.updated_at : typeof a.balance?.updated_at === "string" ? a.balance.updated_at : undefined,
    };
    const positions = normalizePositions(a.positions ?? a.holdings ?? []);
    return { balance: bal, positions };
  }

  // Legacy: GET /paper/portfolio
  const legacy = await fetchJson<any>("/api/paper/portfolio");
  const cashBal = coerceNumber(legacy?.cash?.balance);
  const currency = typeof legacy?.cash?.currency === "string" ? legacy.cash.currency : undefined;
  const positions = normalizeLegacyPositions(legacy?.positions ?? []);
  return { balance: { cash: cashBal, currency, updated_at: legacy?.cash?.updated_at }, positions };
}

export async function listPaperPositions(accountId: string): Promise<PaperPosition[]> {
  const aid = accountId || "default";

  const p1 = await tryJson<any>(`/api/paper/accounts/${encodeURIComponent(aid)}/positions`);
  if (p1) return normalizePositions(p1.positions ?? p1);

  const p2 = await tryJson<any>(`/api/paper/positions?account_id=${encodeURIComponent(aid)}`);
  if (p2) return normalizePositions(p2.positions ?? p2);

  const summary = await getPaperSummary(aid);
  return summary.positions;
}

export async function listPaperOrders(accountId: string, limit = 50): Promise<PaperOrder[]> {
  const aid = accountId || "default";

  const o1 = await tryJson<any>(`/api/paper/accounts/${encodeURIComponent(aid)}/orders?limit=${encodeURIComponent(String(limit))}`);
  if (o1) return normalizeOrders(o1.orders ?? o1);

  const o2 = await tryJson<any>(`/api/paper/orders?account_id=${encodeURIComponent(aid)}&limit=${encodeURIComponent(String(limit))}`);
  if (o2) return normalizeOrders(o2.orders ?? o2);

  return [];
}

export async function listPaperFills(accountId: string, limit = 50): Promise<PaperFill[]> {
  const aid = accountId || "default";

  const f1 = await tryJson<any>(`/api/paper/accounts/${encodeURIComponent(aid)}/fills?limit=${encodeURIComponent(String(limit))}`);
  if (f1) return normalizeFills(f1.fills ?? f1);

  const f2 = await tryJson<any>(`/api/paper/fills?account_id=${encodeURIComponent(aid)}&limit=${encodeURIComponent(String(limit))}`);
  if (f2) return normalizeFills(f2.fills ?? f2);

  // Legacy fallback: /paper/trades
  const legacy = await tryJson<any>(`/api/paper/trades?limit=${encodeURIComponent(String(limit))}`);
  if (legacy) return normalizeLegacyTrades(legacy);

  return [];
}

export async function fundPaperAccount(params: { accountId: string; amount: number; currency?: string }): Promise<void> {
  const accountId = params.accountId || "default";
  const body = JSON.stringify({ amount: params.amount, currency: params.currency });

  const r1 = await tryJson<any>(`/api/paper/accounts/${encodeURIComponent(accountId)}/fund`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  if (r1) return;

  const r2 = await tryJson<any>(`/api/paper/fund`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account_id: accountId, amount: params.amount, currency: params.currency }),
  });
  if (r2) return;

  throw new Error("Funding endpoint not available (expected /paper/accounts/{id}/fund or /paper/fund).");
}

export async function placePaperMarketOrder(params: {
  accountId: string;
  symbol: string;
  side: PaperOrderSide;
  quantity: number;
}): Promise<PaperOrder | null> {
  const accountId = params.accountId || "default";
  const payload = {
    symbol: upperSymbol(params.symbol),
    side: params.side,
    quantity: params.quantity,
    type: "MKT",
  };

  const r1 = await tryJson<any>(`/api/paper/accounts/${encodeURIComponent(accountId)}/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (r1) return normalizeOrders([r1])[0] ?? null;

  const r2 = await tryJson<any>(`/api/paper/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account_id: accountId, ...payload }),
  });
  if (r2) return normalizeOrders([r2])[0] ?? null;

  throw new Error("Order endpoint not available (expected /paper/accounts/{id}/orders or /paper/orders).");
}

export async function listPortfolios(): Promise<{ id: string; name: string }[]> {
  const res = await tryJson<any>("/api/portfolios");
  const rows = res ? (Array.isArray(res) ? res : Array.isArray(res.rows) ? res.rows : null) : null;
  if (!Array.isArray(rows)) return [];
  return rows
    .map((p: any) => ({ id: String(p.id), name: String(p.name ?? p.id) }))
    .filter((p) => p.id);
}

export async function paperRebalancePreview(params: { accountId: string; portfolioId: string; allocationUsd: number }): Promise<Json> {
  const body = JSON.stringify({
    account_id: params.accountId,
    portfolio_id: params.portfolioId,
    allocation_usd: params.allocationUsd,
  });
  const r = await tryJson<Json>("/api/paper/rebalance/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  if (!r) throw new Error("Rebalance preview endpoint not available (expected /paper/rebalance/preview).");
  return r;
}

export async function paperRebalanceExecute(params: { accountId: string; portfolioId: string; allocationUsd: number }): Promise<Json> {
  const body = JSON.stringify({
    account_id: params.accountId,
    portfolio_id: params.portfolioId,
    allocation_usd: params.allocationUsd,
  });
  const r = await tryJson<Json>("/api/paper/rebalance/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  if (!r) throw new Error("Rebalance execute endpoint not available (expected /paper/rebalance/execute).");
  return r;
}

// ---- Normalizers ----

function normalizePositions(input: any): PaperPosition[] {
  const rows = Array.isArray(input) ? input : [];
  return rows
    .map((r: any) => {
      const symbol = upperSymbol(String(r.symbol ?? r.ticker ?? r.contract?.symbol ?? ""));
      const quantity = coerceNumber(r.quantity ?? r.qty ?? r.position) ?? 0;
      const avg_cost = coerceNumber(r.avg_cost ?? r.avgCost ?? r.average_cost ?? r.averageCost);
      const market_price = coerceNumber(r.market_price ?? r.marketPrice ?? r.last_price ?? r.lastPrice ?? r.price);
      const market_value = coerceNumber(r.market_value ?? r.marketValue ?? r.value);
      const currency = typeof r.currency === "string" ? r.currency : undefined;
      const updated_at = typeof r.updated_at === "string" ? r.updated_at : typeof r.timestamp === "string" ? r.timestamp : undefined;
      return { symbol, quantity, avg_cost, currency, market_price, market_value, updated_at };
    })
    .filter((p) => p.symbol);
}

function normalizeLegacyPositions(input: any): PaperPosition[] {
  const rows = Array.isArray(input) ? input : [];
  return rows
    .map((p: any) => ({
      symbol: upperSymbol(String(p.ticker ?? p.symbol ?? "")),
      quantity: coerceNumber(p.quantity) ?? 0,
      avg_cost: coerceNumber(p.avg_cost ?? p.avgCost),
      currency: typeof p.currency === "string" ? p.currency : undefined,
      updated_at: typeof p.updated_at === "string" ? p.updated_at : undefined,
    }))
    .filter((p) => p.symbol);
}

function normalizeOrders(input: any): PaperOrder[] {
  const rows = Array.isArray(input) ? input : [];
  return rows
    .map((o: any) => {
      const symbol = upperSymbol(String(o.symbol ?? o.ticker ?? o.contract?.symbol ?? ""));
      const side = String(o.side ?? o.action ?? "").toUpperCase() as PaperOrderSide;
      const quantity = coerceNumber(o.quantity ?? o.qty ?? o.totalQuantity) ?? 0;
      const type = typeof o.type === "string" ? o.type : typeof o.order_type === "string" ? o.order_type : typeof o.orderType === "string" ? o.orderType : undefined;
      const status = typeof o.status === "string" ? o.status : undefined;
      const created_at = typeof o.created_at === "string" ? o.created_at : typeof o.timestamp === "string" ? o.timestamp : undefined;
      const avg_fill_price = coerceNumber(o.avg_fill_price ?? o.avgFillPrice ?? o.avgFill);
      return { id: o.id != null ? String(o.id) : undefined, created_at, symbol, side, quantity, type, status, avg_fill_price };
    })
    .filter((o) => o.symbol && (o.side === "BUY" || o.side === "SELL"));
}

function normalizeFills(input: any): PaperFill[] {
  const rows = Array.isArray(input) ? input : [];
  return rows
    .map((f: any) => {
      const symbol = upperSymbol(String(f.symbol ?? f.ticker ?? f.contract?.symbol ?? ""));
      const side = String(f.side ?? f.action ?? "").toUpperCase() as PaperOrderSide;
      const quantity = coerceNumber(f.quantity ?? f.qty ?? f.shares ?? f.filled) ?? 0;
      const price = coerceNumber(f.price ?? f.fill_price ?? f.fillPrice);
      const value = coerceNumber(f.value ?? f.notional);
      const timestamp = typeof f.timestamp === "string" ? f.timestamp : typeof f.time === "string" ? f.time : undefined;
      const notes = typeof f.notes === "string" ? f.notes : undefined;
      return { id: f.id != null ? String(f.id) : undefined, timestamp, symbol, side, quantity, price, value, notes };
    })
    .filter((f) => f.symbol && (f.side === "BUY" || f.side === "SELL"));
}

function normalizeLegacyTrades(input: any): PaperFill[] {
  const rows = Array.isArray(input) ? input : [];
  return rows
    .map((t: any) => {
      const symbol = upperSymbol(String(t.ticker ?? t.symbol ?? ""));
      const side = String(t.action ?? t.side ?? "").toUpperCase() as PaperOrderSide;
      const quantity = coerceNumber(t.quantity) ?? 0;
      const price = coerceNumber(t.price);
      const value = coerceNumber(t.value);
      const timestamp = typeof t.timestamp === "string" ? t.timestamp : undefined;
      const notes = typeof t.notes === "string" ? t.notes : undefined;
      return { timestamp, symbol, side, quantity, price, value, notes };
    })
    .filter((f) => f.symbol && (f.side === "BUY" || f.side === "SELL"));
}

