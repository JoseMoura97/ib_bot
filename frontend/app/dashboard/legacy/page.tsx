"use client";

import { useState } from "react";

export default function LegacyDashboardPage() {
  const [refreshing, setRefreshing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function refreshPlotData() {
    setRefreshing(true);
    setMsg(null);
    try {
      const res = await fetch("/api/plot-data/refresh?force=true&max_age_hours=0", { method: "POST" });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      setMsg("Queued plot-data refresh. It may take a while; reload the iframe after it finishes.");
    } catch (e: any) {
      setMsg(String(e?.message || e));
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <main style={{ padding: 0 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Strategy Dashboard (Legacy)</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            onClick={refreshPlotData}
            disabled={refreshing}
            style={{
              padding: "8px 10px",
              borderRadius: 8,
              border: "1px solid #ddd",
              cursor: refreshing ? "not-allowed" : "pointer",
              background: "white",
            }}
          >
            {refreshing ? "Queuing…" : "Refresh plot data"}
          </button>
          <a href="/api/dashboard/strategy-dashboard" target="_blank" rel="noreferrer">
            Open in new tab
          </a>
        </div>
      </div>
      {msg ? (
        <div
          style={{
            marginBottom: 10,
            padding: "10px 12px",
            borderRadius: 10,
            border: "1px solid #eee",
            background: "#fafafa",
            color: "#333",
          }}
        >
          {msg}
        </div>
      ) : null}
      <iframe
        title="Strategy Dashboard"
        src="/api/dashboard/strategy-dashboard"
        style={{
          width: "100%",
          height: "calc(100vh - 140px)",
          border: "1px solid #eee",
          borderRadius: 10,
          background: "white",
        }}
      />
    </main>
  );
}

