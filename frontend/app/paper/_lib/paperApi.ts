export type PaperAccount = {
  id: number;
  name: string;
  balance: number;
  currency: string;
  updated_at?: string;
};

export type PaperPosition = {
  ticker: string;
  quantity: number;
  avg_cost: number;
  currency: string;
  updated_at?: string;
};

export type PaperOrderSide = "BUY" | "SELL";

export type PaperOrder = {
  id: string;
  created_at?: string;
  ticker: string;
  action: PaperOrderSide;
  quantity: number;
  status: string;
  fill_price: number;
  value: number;
};

export type PaperTrade = {
  timestamp?: string;
  ticker: string;
  action: PaperOrderSide;
  quantity: number;
  price: number;
  value: number;
  notes?: string | null;
  order_id?: string | null;
};

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { cache: "no-store", ...init });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`API error ${res.status}${txt ? `: ${txt}` : ""}`);
  }
  return (await res.json()) as T;
}

export async function listPaperAccounts(): Promise<PaperAccount[]> {
  const rows = await fetchJson<PaperAccount[]>("/api/paper/accounts");
  // If no accounts exist yet, the backend endpoints generally default to account 1.
  return rows.length ? rows : [{ id: 1, name: "Paper Account", balance: 0, currency: "USD" }];
}

export async function fundPaperAccount(accountId: number, amount: number): Promise<PaperAccount> {
  return await fetchJson<PaperAccount>(`/api/paper/accounts/${encodeURIComponent(String(accountId))}/fund`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ amount }),
  });
}

export async function getPaperSummary(accountId: number): Promise<{
  cash: number;
  equity: number;
  currency: string;
  updated_at?: string;
  positions: PaperPosition[];
}> {
  return await fetchJson(`/api/paper/accounts/${encodeURIComponent(String(accountId))}/summary`);
}

export async function listPaperPositions(accountId: number): Promise<PaperPosition[]> {
  return await fetchJson<PaperPosition[]>(`/api/paper/accounts/${encodeURIComponent(String(accountId))}/positions`);
}

export async function listPaperOrders(accountId: number, limit = 50): Promise<PaperOrder[]> {
  return await fetchJson<PaperOrder[]>(
    `/api/paper/accounts/${encodeURIComponent(String(accountId))}/orders?limit=${encodeURIComponent(String(limit))}`,
  );
}

export async function listPaperFills(accountId: number, limit = 50): Promise<PaperTrade[]> {
  return await fetchJson<PaperTrade[]>(
    `/api/paper/accounts/${encodeURIComponent(String(accountId))}/fills?limit=${encodeURIComponent(String(limit))}`,
  );
}

export async function placePaperMarketOrder(params: {
  accountId: number;
  ticker: string;
  side: PaperOrderSide;
  quantity: number;
}): Promise<{
  order: PaperOrder;
  trade: PaperTrade;
  account: PaperAccount;
  position: PaperPosition;
}> {
  const payload = {
    symbol: params.ticker.trim().toUpperCase(),
    side: params.side,
    quantity: params.quantity,
  };
  return await fetchJson(`/api/paper/accounts/${encodeURIComponent(String(params.accountId))}/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function listPortfolios(): Promise<Array<{ id: string; name: string }>> {
  const rows = await fetchJson<any>("/api/portfolios");
  const arr = Array.isArray(rows) ? rows : Array.isArray(rows?.rows) ? rows.rows : [];
  return arr.map((p: any) => ({ id: String(p.id), name: String(p.name ?? p.id) }));
}

export async function paperRebalancePreview(params: { accountId: number; portfolioId: string; allocationUsd: number }) {
  return await fetchJson("/api/paper/rebalance/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      account_id: params.accountId,
      portfolio_id: params.portfolioId,
      allocation_usd: params.allocationUsd,
    }),
  });
}

export async function paperRebalanceExecute(params: { accountId: number; portfolioId: string; allocationUsd: number }) {
  return await fetchJson("/api/paper/rebalance/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      account_id: params.accountId,
      portfolio_id: params.portfolioId,
      allocation_usd: params.allocationUsd,
    }),
  });
}

