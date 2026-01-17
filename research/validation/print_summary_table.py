import json
from pathlib import Path


def pct_to_float(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip()
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except Exception:
        return None


def fp(x):
    return "N/A" if x is None else f"{x:.2f}%"


def ff(x):
    return "N/A" if x is None else f"{x:.3f}"


def fn(x):
    return "N/A" if x is None else f"{x:.3f}"


def fi(x):
    return "N/A" if x is None else str(int(x))


def main() -> None:
    cache = json.loads(Path(".cache/quiver_strategies_site.json").read_text(encoding="utf-8"))["strategies"]

    # Prefer latest computed results if available
    our = {}
    last_path = Path(".cache/last_validation_results.json")
    if last_path.exists():
        try:
            payload = json.loads(last_path.read_text(encoding="utf-8"))
            our = payload.get("strategies", {}) or {}
        except Exception:
            our = {}

    order = [
        "Congress Buys",
        "Congress Sells",
        "Congress Long-Short",
        "U.S. House Long-Short",
        "Transportation and Infra. Committee (House)",
        "Energy and Commerce Committee (House)",
        "Homeland Security Committee (Senate)",
        "Top Lobbying Spenders",
        "Lobbying Spending Growth",
        "Top Gov Contract Recipients",
        "Sector Weighted DC Insider",
        "Nancy Pelosi",
        "Dan Meuser",
        "Josh Gottheimer",
        "Donald Beyer",
        "Sheldon Whitehouse",
        "Insider Purchases",
    ]

    print(
        "| Strategy | Status | Q Start | Q_CAGR | Our_CAGR | Diff | Q_Sharpe | Our_Sharpe | Diff | Q_MaxDD | Our_MaxDD | Diff | Our_Beta | Our_Alpha | Our_IR | Our_Treynor | Our_WinRate | Our_Trades |"
    )
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")

    for name in order:
        q = cache.get(name, {})
        q_start = q.get("start_date") or "—"
        q_cagr = pct_to_float(q.get("cagr"))
        q_dd = pct_to_float(q.get("max_drawdown"))
        q_sh = q.get("sharpe") if isinstance(q.get("sharpe"), (int, float)) else None

        o = our.get(name)
        if o is None:
            print(
                f"| {name} | running | {q_start} | {fp(q_cagr)} | N/A | N/A | {ff(q_sh)} | N/A | N/A | {fp(q_dd)} | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |"
            )
            continue

        # Our payload is already in percent units for CAGR/MaxDD/WinRate; sharpe/etc in raw
        o_cagr = o.get("cagr")
        o_sh = o.get("sharpe")
        o_dd = o.get("max_drawdown")
        o_beta = o.get("beta")
        o_alpha = o.get("alpha")
        o_ir = o.get("info_ratio")
        o_treyn = o.get("treynor")
        o_wr = o.get("win_rate")
        o_trades = o.get("trades")

        d_cagr = (o_cagr - q_cagr) if (q_cagr is not None and isinstance(o_cagr, (int, float))) else None
        d_sh = (o_sh - q_sh) if (q_sh is not None and isinstance(o_sh, (int, float))) else None
        d_dd = (o_dd - q_dd) if (q_dd is not None and isinstance(o_dd, (int, float))) else None

        print(
            f"| {name} | done | {q_start} | {fp(q_cagr)} | {fp(o_cagr)} | {fp(d_cagr)} | "
            f"{ff(q_sh)} | {ff(o_sh)} | {ff(d_sh)} | {fp(q_dd)} | {fp(o_dd)} | {fp(d_dd)} | "
            f"{fn(o_beta)} | {fn(o_alpha)} | {fn(o_ir)} | {fn(o_treyn)} | {fp(o_wr)} | {fi(o_trades)} |"
        )


if __name__ == "__main__":
    main()

