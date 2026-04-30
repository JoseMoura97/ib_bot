#!/usr/bin/env python3
"""Generate the week plan PDF for the IB Bot production push."""

from fpdf import FPDF
from datetime import datetime


class PlanPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, "IB Bot - Production Week Plan", align="L")
        self.cell(0, 6, f"Generated {datetime.now().strftime('%Y-%m-%d')}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title, bg=(41, 98, 255)):
        self.set_fill_color(*bg)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 9, f"  {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def sub_title(self, title):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(41, 98, 255)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def body_text(self, text):
        self.set_font("Helvetica", "", 9.5)
        self.multi_cell(0, 5, text)
        self.ln(1)

    def bullet(self, text, indent=10):
        self.set_font("Helvetica", "", 9.5)
        self.set_x(self.l_margin + indent)
        w = self.w - self.r_margin - self.get_x() - 4
        self.cell(4, 5, "-")
        self.multi_cell(w, 5, text)

    def check_item(self, text, checked=False, indent=10):
        self.set_font("Helvetica", "", 9.5)
        self.set_x(self.l_margin + indent)
        mark = "[x] " if checked else "[ ] "
        w = self.w - self.r_margin - self.get_x() - 8
        self.cell(8, 5, mark)
        self.multi_cell(w, 5, text)

    def kv_line(self, key, value, indent=10):
        self.set_font("Helvetica", "B", 9.5)
        self.cell(indent)
        self.cell(40, 5, key + ":")
        self.set_font("Helvetica", "", 9.5)
        self.cell(0, 5, str(value), new_x="LMARGIN", new_y="NEXT")

    def divider(self):
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def day_header(self, day_num, day_name, title, color=(41, 98, 255)):
        self.add_page()
        r, g, b = color
        self.set_fill_color(r, g, b)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 12, f"  DAY {day_num} ({day_name}) - {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(4)


def build_pdf():
    pdf = PlanPDF(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ══════════════════════════════════════════════════════════════════════
    # COVER / OVERVIEW
    # ══════════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.ln(20)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(41, 98, 255)
    pdf.cell(0, 14, "IB Bot", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 10, "Production Week Plan", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "February 7 - 13, 2026", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    pdf.set_draw_color(41, 98, 255)
    pdf.line(60, pdf.get_y(), 150, pdf.get_y())
    pdf.ln(8)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, (
        "This plan covers 7 days of focused work to bring the IB Bot trading system "
        "from its current state to production readiness. Each day is designed for "
        "~1 hour of your time with Cursor agents doing the heavy lifting.\n\n"
        "Goal: Full backtesting suite, portfolio optimizer, and live trading system "
        "ready for deployment on a VM with Interactive Brokers."
    ), align="C")

    pdf.ln(10)
    pdf.section_title("Current State (Day 1 Complete)")
    pdf.kv_line("Strategies", "22 total, 20 enabled, ALL 20 backtested LIVE")
    pdf.kv_line("Price Cache", "2,424 IB tickers + 1,743 YF tickers")
    pdf.kv_line("SEC EDGAR", "3 fund filings fully cached (Burry 32, Ackman 41, Marks 103)")
    pdf.kv_line("QuiverQuant", "LIVE - API key active, 17 strategies using fresh signals")
    pdf.kv_line("Unified Runner", "run_all_backtests.py - single source of truth")
    pdf.kv_line("Data Quality", "Insider Purchases anomaly RESOLVED (296% -> 21% CAGR)")

    pdf.ln(4)
    pdf.section_title("Critical Constraints")
    pdf.bullet("1 hour/day of your time - Cursor agents handle all coding")
    pdf.bullet("Real money at stake (5% NW) - safety checks are non-negotiable")
    pdf.bullet("VM migration needed for IB Gateway - requires your manual setup")

    pdf.ln(4)
    pdf.section_title("Week Overview")
    days = [
        ("Day 1", "Sat", "Backtest Foundation", "DONE", (46, 160, 67)),
        ("Day 2", "Sun", "Stats Validation & Regression Tests", "TODO", (41, 98, 255)),
        ("Day 3", "Mon", "UI: Real Data, No Synthetic Charts", "TODO", (41, 98, 255)),
        ("Day 4", "Tue", "Portfolio Optimizer", "TODO", (41, 98, 255)),
        ("Day 5", "Wed", "Paper Trading Automation", "TODO", (41, 98, 255)),
        ("Day 6", "Thu", "Live Trading Safety & IB Integration", "TODO", (41, 98, 255)),
        ("Day 7", "Fri", "Integration Testing & Go-Live", "TODO", (41, 98, 255)),
    ]
    for day, weekday, title, status, color in days:
        done = status == "DONE"
        pdf.check_item(f"{day} ({weekday}): {title}", checked=done)

    # ══════════════════════════════════════════════════════════════════════
    # DAY 1 - COMPLETED
    # ══════════════════════════════════════════════════════════════════════
    pdf.day_header(1, "Saturday", "BACKTEST FOUNDATION", color=(46, 160, 67))
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(46, 160, 67)
    pdf.cell(0, 7, "STATUS: COMPLETED", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    pdf.sub_title("Deliverables")
    pdf.check_item("Unified backtest runner (run_all_backtests.py)", checked=True)
    pdf.check_item("Strategy registry - canonical list of all 22 strategies", checked=True)
    pdf.check_item("Data coverage report with date ranges + quality flags", checked=True)
    pdf.check_item("Extended metrics: Sharpe, Sortino, Calmar, DD duration, profit factor", checked=True)
    pdf.check_item("Cache fallback - works offline when QuiverQuant is down", checked=True)
    pdf.check_item("ALL 20 enabled strategies backtested with fresh live data", checked=True)
    pdf.check_item("Data quality flags (Insider Purchases anomaly RESOLVED)", checked=True)
    pdf.check_item("SEC EDGAR cache fully populated (Oaktree 103 filings)", checked=True)
    pdf.check_item("Fixed sec13F fallback loop (no more Quiver premium errors)", checked=True)
    pdf.check_item("Howard Marks backtest working (was hanging, now 0.4s)", checked=True)

    pdf.divider()
    pdf.sub_title("All 20 Strategies - Fresh Live Data (sorted by CAGR)")
    pdf.set_font("Courier", "", 7.5)
    header = f"{'Strategy':<40} {'CAGR':>6} {'Shrp':>5} {'Sort':>5} {'MaxDD':>7} {'Alpha':>6} {'Beta':>5} {'WinR':>5}"
    pdf.cell(0, 4, header, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(150, 150, 150)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(1)
    pdf.set_font("Courier", "", 7.5)
    rows = [
        ("Michael Burry", "44.3%", "1.31", "2.03", "-39.7%", "57.1%", "0.05", "53.4%"),
        ("Congress Long-Short", "29.1%", "0.91", "1.28", "-35.4%", "26.9%", "0.03", "53.7%"),
        ("Transport. & Infra. Cmte", "28.5%", "1.15", "1.64", "-31.4%", "21.9%", "0.03", "54.8%"),
        ("U.S. House Long-Short", "26.2%", "1.06", "1.64", "-32.2%", "20.3%", "0.04", "54.4%"),
        ("Energy & Commerce Cmte", "23.7%", "0.98", "1.44", "-33.8%", "18.6%", "0.02", "53.2%"),
        ("Sector Weighted DC Insider", "22.8%", "1.22", "1.72", "-18.0%", "17.7%", "0.01", "55.3%"),
        ("Congress Buys", "21.2%", "0.96", "1.34", "-29.1%", "17.1%", "0.03", "55.4%"),
        ("Insider Purchases", "21.0%", "0.64", "1.09", "-39.5%", "17.5%", "0.06", "50.8%"),
        ("Dan Meuser", "19.2%", "0.68", "0.92", "-37.1%", "19.1%", "0.01", "54.6%"),
        ("Top Lobbying Spenders", "17.6%", "0.76", "1.02", "-30.9%", "18.9%", "0.02", "53.5%"),
        ("Josh Gottheimer", "16.1%", "0.76", "0.98", "-32.6%", "12.3%", "0.01", "54.0%"),
        ("Bill Ackman", "15.2%", "0.62", "0.77", "-46.9%", "17.2%", "0.04", "55.0%"),
        ("Homeland Sec. Cmte", "14.3%", "0.66", "0.89", "-29.0%", " 9.7%", "0.03", "52.8%"),
        ("Top Gov Contracts", "12.6%", "0.48", "0.62", "-41.0%", "15.5%", "0.00", "52.8%"),
        ("Congress Sells", "11.6%", "0.45", "0.62", "-27.0%", " 7.1%", "0.02", "53.6%"),
        ("Sheldon Whitehouse", "11.2%", "0.63", "0.78", "-28.9%", "10.9%", "0.01", "55.1%"),
        ("Donald Beyer", " 9.4%", "0.40", "0.54", "-27.0%", "12.6%", "-0.02", "53.2%"),
        ("Lobbying Spending Growth", " 9.0%", "0.27", "0.36", "-43.5%", "11.0%", "0.00", "52.4%"),
        ("Howard Marks", " 4.7%", "0.16", "0.23", "-21.0%", " 9.5%", "0.01", "53.3%"),
        ("Nancy Pelosi", " 4.5%", "0.12", "0.17", "-42.0%", " 6.1%", "0.04", "52.6%"),
    ]
    for row in rows:
        line = f"{row[0]:<40} {row[1]:>6} {row[2]:>5} {row[3]:>5} {row[4]:>7} {row[5]:>6} {row[6]:>5} {row[7]:>5}"
        pdf.cell(0, 3.8, line, new_x="LMARGIN", new_y="NEXT")

    # ══════════════════════════════════════════════════════════════════════
    # DAY 2
    # ══════════════════════════════════════════════════════════════════════
    pdf.day_header(2, "Sunday", "STATS VALIDATION & REGRESSION TESTS")

    pdf.sub_title("Problem")
    pdf.body_text(
        "Need full confidence in backtest numbers. Some cached equity curves may have "
        "drift from the live engine. No regression tests to catch future breakage."
    )

    pdf.sub_title("Cursor Agents Will")
    pdf.bullet("Add missing stats to the unified runner: rolling Sharpe (12mo window), "
               "drawdown recovery time, skewness, kurtosis")
    pdf.bullet("Cross-validate: compare cached plot_data.json CAGRs against fresh "
               "RebalancingBacktestEngine runs for all 20 strategies")
    pdf.bullet("Build regression test suite: snapshot current results, assert future "
               "runs produce identical numbers (determinism check)")
    pdf.bullet("Insider Purchases anomaly RESOLVED (Day 1): was corrupted cached data "
               "with 400%+ single-period jumps. Fresh data shows 21.0% CAGR.")
    pdf.bullet("Create a BacktestReport class that outputs structured JSON with all stats, "
               "consumable by the UI")

    pdf.sub_title("Your 1 Hour")
    pdf.check_item("Review stat output for your best 5 strategies")
    pdf.check_item("Flag anything that looks wrong vs your expectations")
    pdf.check_item("Approve the regression test baselines")

    pdf.sub_title("Deliverable")
    pdf.body_text(
        "Comprehensive stats for every strategy with regression tests that lock in "
        "known-good results. One command: python -m pytest tests/test_backtest_regression.py"
    )

    # ══════════════════════════════════════════════════════════════════════
    # DAY 3
    # ══════════════════════════════════════════════════════════════════════
    pdf.day_header(3, "Monday", "UI: REAL DATA, NO SYNTHETIC CHARTS")

    pdf.sub_title("Problem")
    pdf.body_text(
        "UI shows synthetic/fake charts for some strategies. Missing strategies in the "
        "catalog. Charts don't use real backtest data from the unified runner."
    )

    pdf.sub_title("Cursor Agents Will")
    pdf.bullet("Trace the chart data pipeline: API endpoint -> plot_data.json -> "
               "frontend Chart.js component")
    pdf.bullet("Replace any synthetic chart generation with real data from "
               ".cache/all_results_combined.json")
    pdf.bullet("Add all 22 strategies to the strategy catalog UI")
    pdf.bullet("Add 'last updated' timestamp and 'data source' badge to every chart "
               "(live vs cached)")
    pdf.bullet("Ensure /api/plot_data serves real backtest curves from the unified runner")
    pdf.bullet("Fix any discrepancies between plot_data.json and latest_backtest_results.json")

    pdf.sub_title("Your 1 Hour")
    pdf.check_item("Open the UI (docker-compose up)")
    pdf.check_item("Check every strategy page - verify charts match Day 2 numbers")
    pdf.check_item("Flag any remaining synthetic or stale data")

    pdf.sub_title("Deliverable")
    pdf.body_text(
        "UI showing only real backtest data. Every chart has a timestamp and source badge. "
        "All 22 strategies visible in the catalog."
    )

    # ══════════════════════════════════════════════════════════════════════
    # DAY 4
    # ══════════════════════════════════════════════════════════════════════
    pdf.day_header(4, "Tuesday", "PORTFOLIO OPTIMIZER")

    pdf.sub_title("Problem")
    pdf.body_text(
        "Need multi-strategy portfolio construction with weight optimization. "
        "Current portfolio_math.py and portfolio_backtest.py exist but need "
        "verification and enhancement."
    )

    pdf.sub_title("Cursor Agents Will")
    pdf.bullet("Verify portfolio_math.py nav_blend produces correct blended NAV curves")
    pdf.bullet("Add portfolio optimization methods: equal-weight, inverse-volatility, "
               "risk-parity, and max-Sharpe (mean-variance)")
    pdf.bullet("Build portfolio comparison tool: same strategies, different weight schemes, "
               "side-by-side results")
    pdf.bullet("Add constraints: max weight per strategy (e.g., 30%), min diversification, "
               "max correlation between strategies")
    pdf.bullet("Connect portfolio backtester to the allocations UI page")
    pdf.bullet("Create a recommended portfolio based on Day 2 validated stats")

    pdf.sub_title("Your 1 Hour")
    pdf.check_item("Create 2-3 portfolio configs with your preferred strategies")
    pdf.check_item("Run the optimizer - review suggested weights")
    pdf.check_item("Compare blended performance vs individual strategies")
    pdf.check_item("Select your V1 portfolio allocation")

    pdf.sub_title("Deliverable")
    pdf.body_text(
        "Working portfolio optimizer: suggest weights, backtest blended result, "
        "compare schemes. V1 allocation locked in."
    )

    # ══════════════════════════════════════════════════════════════════════
    # DAY 5
    # ══════════════════════════════════════════════════════════════════════
    pdf.day_header(5, "Wednesday", "PAPER TRADING AUTOMATION")

    pdf.sub_title("Problem")
    pdf.body_text(
        "Paper trading exists (dual implementation: SQLite legacy + PostgreSQL modern) "
        "but isn't automated. No scheduled rebalancing. Need to validate the full "
        "signal -> rebalance -> fill -> P&L cycle."
    )

    pdf.sub_title("Cursor Agents Will")
    pdf.bullet("Consolidate to PostgreSQL paper trading only (deprecate SQLite)")
    pdf.bullet("Build automated rebalancing via Celery beat: check signals on schedule, "
               "execute paper rebalances")
    pdf.bullet("Add daily P&L snapshots and portfolio tracking")
    pdf.bullet("Create historical simulation mode: fast-forward through historical data "
               "to validate full cycle")
    pdf.bullet("Add paper trading dashboard data to the API")
    pdf.bullet("Write integration test: create portfolio -> generate signals -> "
               "rebalance -> verify positions")

    pdf.sub_title("Your 1 Hour")
    pdf.check_item("Run the historical simulation")
    pdf.check_item("Verify paper trading results are consistent with backtests")
    pdf.check_item("Review automated rebalancing schedule")

    pdf.sub_title("Deliverable")
    pdf.body_text(
        "Automated paper trading that rebalances on schedule with P&L tracking. "
        "Historical simulation validates the full cycle."
    )

    # ══════════════════════════════════════════════════════════════════════
    # DAY 6
    # ══════════════════════════════════════════════════════════════════════
    pdf.day_header(6, "Thursday", "LIVE TRADING SAFETY & IB INTEGRATION")

    pdf.sub_title("Problem")
    pdf.body_text(
        "Live trading infrastructure exists but execution is intentionally disabled. "
        "Need comprehensive safety checks before enabling with real money. "
        "VM deployment preparation needed."
    )

    pdf.sub_title("Cursor Agents Will")
    pdf.bullet("Review and harden all safety checks: position size limits, max daily loss, "
               "max orders/day, spread checks, price validation")
    pdf.bullet("Add pre-trade checklist: account balance, position limits, correlation, "
               "market hours verification")
    pdf.bullet("Build 'dry run' mode: log exactly what orders would be placed without executing")
    pdf.bullet("Create VM deployment script: docker-compose with IB Gateway, env setup, "
               "health checks, auto-restart")
    pdf.bullet("Add alerting: Telegram/email notifications for trades, errors, daily P&L")
    pdf.bullet("Document IB Gateway setup steps for VM (manual steps you'll need to do)")
    pdf.bullet("Create kill-switch: one command to halt all trading and liquidate")

    pdf.sub_title("Your 1 Hour")
    pdf.check_item("Review every safety check - set your personal risk limits")
    pdf.check_item("Set max position size (e.g., 10% of portfolio per position)")
    pdf.check_item("Set max daily loss limit (e.g., 2% of portfolio)")
    pdf.check_item("Begin VM setup if available")

    pdf.sub_title("Deliverable")
    pdf.body_text(
        "Live trading system with comprehensive safety rails. VM deployment script ready. "
        "Kill-switch operational. Risk limits configured."
    )

    # ══════════════════════════════════════════════════════════════════════
    # DAY 7
    # ══════════════════════════════════════════════════════════════════════
    pdf.day_header(7, "Friday", "INTEGRATION TESTING & GO-LIVE")

    pdf.sub_title("Problem")
    pdf.body_text(
        "No full-stack testing. Need confidence that all components work together "
        "before deploying with real money."
    )

    pdf.sub_title("Cursor Agents Will")
    pdf.bullet("Write end-to-end integration tests: API -> backtest -> results -> UI")
    pdf.bullet("Write paper trading integration test: create portfolio -> signals -> "
               "rebalance -> verify positions")
    pdf.bullet("Test full Docker stack boots cleanly (db + redis + api + worker + beat + web)")
    pdf.bullet("Create production runbook: startup, monitoring, troubleshooting, rollback")
    pdf.bullet("Final bug-fix pass on anything found during the week")
    pdf.bullet("Create go-live checklist with manual verification steps")

    pdf.sub_title("Your 1 Hour")
    pdf.check_item("Run the full test suite")
    pdf.check_item("Walk through the go-live checklist")
    pdf.check_item("Make the go/no-go decision")
    pdf.check_item("If go: deploy to VM, connect IB Gateway, start paper trading")

    pdf.sub_title("Deliverable")
    pdf.body_text(
        "Tested system with production runbook. Go-live checklist completed. "
        "System deployed and running in paper mode."
    )

    # ══════════════════════════════════════════════════════════════════════
    # DONE STATE
    # ══════════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("What 'Done' Looks Like - Friday Night", bg=(46, 160, 67))
    pdf.ln(2)

    components = [
        ("Backtesting", "All strategies, single engine, consistent data, full stats, regression tests"),
        ("Portfolio Optimizer", "Multi-strategy blends with weight optimization (4 methods)"),
        ("Paper Trading", "Automated rebalancing on schedule, daily P&L tracking"),
        ("Live Trading", "Safety-hardened, dry-run tested, IB Gateway ready on VM"),
        ("UI Dashboard", "Real charts only, all strategies, portfolio allocations"),
        ("Testing", "Integration tests passing, production runbook written"),
    ]
    for component, state in components:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(50, 6, component)
        pdf.set_font("Helvetica", "", 9.5)
        pdf.multi_cell(0, 6, state)
        pdf.ln(1)

    pdf.divider()
    pdf.section_title("Risks & Mitigations")
    pdf.ln(2)

    risks = [
        ("QuiverQuant stays down",
         "Use cached equity curves + SEC EDGAR. 17 strategies still have cached data. "
         "If restored mid-week, re-run fresh backtests immediately."),
        ("IB Gateway VM setup",
         "Requires your manual setup (agents can't SSH). Day 6 prep maximizes automation. "
         "Fallback: run locally for first week."),
        ("Time overrun",
         "If something breaks unexpectedly, cut Day 5 (paper trading automation) - "
         "it's least critical for go-live. Can run paper trades manually."),
        ("Data quality issues",
         "Insider Purchases 296% CAGR flagged. Regression tests on Day 2 will catch "
         "any other anomalies. Don't trade any strategy with unflagged data."),
    ]
    for risk, mitigation in risks:
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(200, 50, 50)
        pdf.cell(0, 5, f"Risk: {risk}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 9.5)
        pdf.multi_cell(0, 5, f"Mitigation: {mitigation}")
        pdf.ln(2)

    pdf.divider()
    pdf.section_title("Quick Reference Commands")
    pdf.set_font("Courier", "", 8.5)
    commands = [
        "# Coverage report",
        "python run_all_backtests.py --report-only",
        "",
        "# Run all backtests (cache fallback)",
        "python run_all_backtests.py --output results.json",
        "",
        "# Run SEC EDGAR strategies only (no API key needed)",
        "python run_all_backtests.py --sec-edgar-only",
        "",
        "# Run specific strategies",
        'python run_all_backtests.py --strategies "Michael Burry,Congress Buys"',
        "",
        "# Core strategies only",
        "python run_all_backtests.py --category core",
        "",
        "# Start full stack",
        "docker-compose up -d",
    ]
    for cmd in commands:
        pdf.cell(0, 4.5, f"  {cmd}", new_x="LMARGIN", new_y="NEXT")

    # Save
    output_path = str(__file__).replace("generate_plan_pdf.py", "IB_Bot_Production_Week_Plan.pdf")
    pdf.output(output_path)
    return output_path


if __name__ == "__main__":
    path = build_pdf()
    print(f"PDF saved to: {path}")
