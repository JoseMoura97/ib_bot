from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, List, Optional


def _repo_root_from(start: Path) -> Path:
    """
    Find repo root from an arbitrary file location by walking upward.
    We treat the first parent containing `.cache/` as the repo root.
    """
    start = start.resolve()
    for p in [start, *start.parents]:
        if (p / ".cache").exists():
            return p
    return start


def _inline(md: str) -> str:
    """
    Minimal inline markdown:
    - `code`
    - **bold**
    """
    s = html.escape(md, quote=False)
    # inline code first
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    # bold
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


def _split_table_row(line: str) -> List[str]:
    # Trim outer pipes, then split.
    raw = line.strip()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
    return [c.strip() for c in raw.split("|")]


def _is_table_sep(line: str) -> bool:
    # e.g. |---|---:|---|
    s = line.strip()
    if "|" not in s:
        return False
    cells = _split_table_row(s)
    if not cells:
        return False
    for c in cells:
        c = c.strip()
        if not c:
            return False
        if not re.fullmatch(r":?-{3,}:?", c):
            return False
    return True


def render_markdown(md_text: str) -> str:
    lines = md_text.splitlines()
    out: List[str] = []

    in_code = False
    code_lang: Optional[str] = None
    code_buf: List[str] = []

    in_ul = False
    para_buf: List[str] = []

    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")

        # Code fences
        if line.strip().startswith("```"):
            fence = line.strip()
            if not in_code:
                in_code = True
                code_lang = fence[3:].strip() or None
                code_buf = []
            else:
                # close
                in_code = False
                lang_class = f"language-{html.escape(code_lang)}" if code_lang else ""
                code_html = html.escape("\n".join(code_buf), quote=False)
                out.append(f"<pre><code class=\"{lang_class}\">{code_html}\n</code></pre>")
                code_lang = None
                code_buf = []
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # Flush paragraph on blank line
        if not line.strip():
            if para_buf:
                out.append(f"<p>{_inline(' '.join(para_buf).strip())}</p>")
                para_buf = []
            if in_ul:
                out.append("</ul>")
                in_ul = False
            i += 1
            continue

        # Horizontal rule
        if line.strip() == "---":
            if para_buf:
                out.append(f"<p>{_inline(' '.join(para_buf).strip())}</p>")
                para_buf = []
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append("<hr />")
            i += 1
            continue

        # Headings (### / ####)
        m = re.match(r"^(#{3,6})\s+(.*)$", line)
        if m:
            if para_buf:
                out.append(f"<p>{_inline(' '.join(para_buf).strip())}</p>")
                para_buf = []
            if in_ul:
                out.append("</ul>")
                in_ul = False
            level = min(6, max(1, len(m.group(1))))
            out.append(f"<h{level}>{_inline(m.group(2).strip())}</h{level}>")
            i += 1
            continue

        # Tables
        if line.strip().startswith("|") and "|" in line:
            # Detect header + separator + body rows
            if (i + 1) < len(lines) and _is_table_sep(lines[i + 1]):
                if para_buf:
                    out.append(f"<p>{_inline(' '.join(para_buf).strip())}</p>")
                    para_buf = []
                if in_ul:
                    out.append("</ul>")
                    in_ul = False

                header_cells = _split_table_row(line)
                out.append("<table>")
                out.append("<thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in header_cells) + "</tr></thead>")
                out.append("<tbody>")
                i += 2  # skip sep line
                while i < len(lines):
                    row = lines[i].strip()
                    if not row.startswith("|") or "|" not in row or _is_table_sep(row) or not row:
                        break
                    cells = _split_table_row(row)
                    out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
                    i += 1
                out.append("</tbody></table>")
                continue

        # Lists
        if line.lstrip().startswith("- "):
            if para_buf:
                out.append(f"<p>{_inline(' '.join(para_buf).strip())}</p>")
                para_buf = []
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            item = line.lstrip()[2:].strip()
            out.append(f"<li>{_inline(item)}</li>")
            i += 1
            continue

        # Default: accumulate paragraph
        para_buf.append(line.strip())
        i += 1

    # Final flush
    if para_buf:
        out.append(f"<p>{_inline(' '.join(para_buf).strip())}</p>")
    if in_ul:
        out.append("</ul>")

    return "\n".join(out).strip()


def _parse_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if not s:
        return None
    if s.endswith("%"):
        s = s[:-1].strip()
    try:
        return float(s.replace(",", ""))
    except Exception:
        return None


def _parse_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    if isinstance(x, int):
        return int(x)
    if isinstance(x, float) and x.is_integer():
        return int(x)
    s = str(x).strip().replace(",", "")
    m = re.search(r"(-?\d+)", s)
    return int(m.group(1)) if m else None


def _fmt_num(x: Optional[float], places: int = 3) -> str:
    return "N/A" if x is None else f"{x:.{places}f}"


def _fmt_pct(x: Optional[float], places: int = 2) -> str:
    return "N/A" if x is None else f"{x:.{places}f}%"


def _fmt_int(x: Optional[int]) -> str:
    return "N/A" if x is None else str(int(x))


def build_metrics_comparison_section(repo_root: Path) -> str:
    """
    Build an HTML section comparing Quiver vs Our "other metrics".

    Data sources:
    - Quiver: .cache/quiver_strategies_site.json (scraped site metrics)
    - Our:    .cache/last_validation_results.json (computed metrics; merged incrementally)
    """
    q_path = repo_root / ".cache" / "quiver_strategies_site.json"
    o_path = repo_root / ".cache" / "last_validation_results.json"

    if not q_path.exists():
        return "<p><strong>Expanded metrics comparison:</strong> N/A (missing <code>.cache/quiver_strategies_site.json</code>).</p>"
    if not o_path.exists():
        return "<p><strong>Expanded metrics comparison:</strong> N/A (missing <code>.cache/last_validation_results.json</code> — run validation to populate).</p>"

    try:
        q_payload = json.loads(q_path.read_text(encoding="utf-8"))
        q = q_payload.get("strategies", {}) if isinstance(q_payload, dict) else {}
    except Exception:
        q = {}

    try:
        o_payload = json.loads(o_path.read_text(encoding="utf-8"))
        our = o_payload.get("strategies", {}) if isinstance(o_payload, dict) else {}
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

    header = [
        "Strategy",
        "Q_Beta",
        "Our_Beta",
        "Diff",
        "Q_Alpha",
        "Our_Alpha",
        "Diff",
        "Q_IR",
        "Our_IR",
        "Diff",
        "Q_Treynor",
        "Our_Treynor",
        "Diff",
        "Q_WinRate",
        "Our_WinRate",
        "Diff",
        "Q_Trades",
        "Our_Trades",
        "Diff",
    ]

    rows_html: List[str] = []
    rows_html.append("<thead><tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in header) + "</tr></thead>")
    rows_html.append("<tbody>")

    for name in order:
        q_row = q.get(name, {}) if isinstance(q, dict) else {}
        o_row = our.get(name, {}) if isinstance(our, dict) else {}

        q_beta = _parse_float(q_row.get("beta"))
        o_beta = _parse_float(o_row.get("beta"))
        q_alpha = _parse_float(q_row.get("alpha"))
        o_alpha = _parse_float(o_row.get("alpha"))
        q_ir = _parse_float(q_row.get("info_ratio"))
        o_ir = _parse_float(o_row.get("info_ratio"))
        q_treyn = _parse_float(q_row.get("treynor"))
        o_treyn = _parse_float(o_row.get("treynor"))

        q_wr = _parse_float(q_row.get("win_rate"))
        o_wr = _parse_float(o_row.get("win_rate"))

        q_tr = _parse_int(q_row.get("trades"))
        o_tr = _parse_int(o_row.get("trades"))

        def d(a: Optional[float], b: Optional[float]) -> Optional[float]:
            if a is None or b is None:
                return None
            return b - a

        def d_int(a: Optional[int], b: Optional[int]) -> Optional[int]:
            if a is None or b is None:
                return None
            return int(b - a)

        cells = [
            html.escape(name),
            _fmt_num(q_beta),
            _fmt_num(o_beta),
            _fmt_num(d(q_beta, o_beta)),
            _fmt_num(q_alpha),
            _fmt_num(o_alpha),
            _fmt_num(d(q_alpha, o_alpha)),
            _fmt_num(q_ir),
            _fmt_num(o_ir),
            _fmt_num(d(q_ir, o_ir)),
            _fmt_num(q_treyn),
            _fmt_num(o_treyn),
            _fmt_num(d(q_treyn, o_treyn)),
            _fmt_pct(q_wr),
            _fmt_pct(o_wr),
            _fmt_pct(d(q_wr, o_wr)),
            _fmt_int(q_tr),
            _fmt_int(o_tr),
            _fmt_int(d_int(q_tr, o_tr)),
        ]
        rows_html.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")

    rows_html.append("</tbody>")

    table = "<div class=\"table-wrap\"><table>" + "\n".join(rows_html) + "</table></div>"
    note = (
        "<p><em>Notes:</em> Our metrics are computed vs <code>SPY</code> using aligned daily returns and RF=2% annualized. "
        "Quiver values come from the scraped site cache. Missing values show as N/A.</p>"
    )
    return "<hr /><h4>Expanded metrics comparison (Quiver vs Our)</h4>" + note + table


def main() -> None:
    here = Path(__file__).resolve().parent
    repo_root = _repo_root_from(here)

    md_path = here / "FULL_SUMMARY.md"
    html_path = here / "FULL_SUMMARY.html"

    md_text = md_path.read_text(encoding="utf-8")
    body = render_markdown(md_text)
    extra = build_metrics_comparison_section(repo_root)

    doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>IB Bot — Full Summary</title>
  <style>
    :root {{
      --bg: #0b1220;
      --panel: #101a2e;
      --text: #e6edf3;
      --muted: #9fb0c0;
      --border: #25324a;
      --code-bg: #0f172a;
      --accent: #7aa2f7;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.55 ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, "Noto Sans", "Liberation Sans", sans-serif;
    }}
    .wrap {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 28px 18px 60px;
    }}
    h3, h4, h5, h6 {{
      margin: 18px 0 10px;
      line-height: 1.25;
    }}
    h3 {{ font-size: 22px; }}
    h4 {{ font-size: 16px; color: var(--accent); }}
    p {{ margin: 10px 0; color: var(--text); }}
    ul {{ margin: 10px 0 14px 18px; padding: 0; }}
    li {{ margin: 4px 0; color: var(--text); }}
    hr {{
      border: none;
      border-top: 1px solid var(--border);
      margin: 18px 0;
    }}
    code {{
      background: rgba(122, 162, 247, 0.12);
      border: 1px solid rgba(122, 162, 247, 0.22);
      padding: 1px 5px;
      border-radius: 6px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      color: var(--text);
    }}
    pre {{
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 14px;
      overflow: auto;
    }}
    pre code {{
      background: transparent;
      border: none;
      padding: 0;
      border-radius: 0;
      display: block;
      color: var(--text);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 12px 0 18px;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
    }}
    .table-wrap {{
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }}
    th, td {{
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }}
    th {{
      text-align: left;
      font-weight: 700;
      color: var(--text);
      background: rgba(122, 162, 247, 0.08);
    }}
    tr:last-child td {{ border-bottom: none; }}
    .footer {{
      margin-top: 22px;
      color: var(--muted);
      font-size: 12px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    {body}
    {extra}
    <div class="footer">Generated from <code>research/reports/FULL_SUMMARY.md</code>.</div>
  </div>
</body>
</html>
"""
    html_path.write_text(doc, encoding="utf-8")
    print(f"Wrote {html_path}")


if __name__ == "__main__":
    main()

