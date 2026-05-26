import sys
sys.path.insert(0, '/app')

import os
import io
import json
import zipfile
import requests
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# 1. DOWNLOAD & PARSE KEN FRENCH DATA
# ─────────────────────────────────────────────

def download_french_factors():
    """Download F-F Research Data Factors (monthly). Returns DataFrame with
    Date(period), Mkt-RF, SMB, HML, RF — all as decimal returns."""
    url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip"
    print("Downloading F-F Factors CSV...")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    fname = [n for n in z.namelist() if n.endswith('.CSV') or n.endswith('.csv')][0]
    raw = z.read(fname).decode('latin-1')

    lines = raw.splitlines()

    # Find the monthly section: starts after the first header line that has
    # Mkt-RF in it, ends at the blank line before "Annual" section.
    monthly_start = None
    monthly_end = None
    for i, line in enumerate(lines):
        if 'Mkt-RF' in line and monthly_start is None:
            monthly_start = i + 1  # data starts after header row
        if monthly_start is not None and i > monthly_start:
            stripped = line.strip()
            # Annual factors section begins with a line that contains 'Annual'
            # or is an empty separator followed by a header row
            if stripped == '' and monthly_end is None:
                # peek ahead: if next non-empty line has 'Mkt-RF' it's the annual header
                for j in range(i+1, min(i+5, len(lines))):
                    if lines[j].strip():
                        if 'Mkt-RF' in lines[j] or 'Annual' in lines[j]:
                            monthly_end = i
                        break
                if monthly_end is not None:
                    break

    if monthly_end is None:
        monthly_end = len(lines)

    data_lines = lines[monthly_start:monthly_end]
    # Filter lines that start with a 6-digit date
    rows = []
    for line in data_lines:
        parts = line.strip().split(',')
        if len(parts) >= 5:
            try:
                date_str = parts[0].strip()
                if len(date_str) == 6 and date_str.isdigit():
                    mkt_rf = float(parts[1])
                    smb    = float(parts[2])
                    hml    = float(parts[3])
                    rf     = float(parts[4])
                    rows.append({'Date': date_str, 'Mkt-RF': mkt_rf,
                                 'SMB': smb, 'HML': hml, 'RF': rf})
            except ValueError:
                continue

    df = pd.DataFrame(rows)
    df['Date'] = pd.to_datetime(df['Date'], format='%Y%m') + pd.offsets.MonthEnd(0)
    df = df.set_index('Date').sort_index()
    # Convert percent → decimal
    for col in ['Mkt-RF', 'SMB', 'HML', 'RF']:
        df[col] = df[col] / 100.0
    print(f"  Factors loaded: {df.index[0].date()} → {df.index[-1].date()} ({len(df)} months)")
    return df


def download_french_beme():
    """Download Portfolios Formed on BE/ME (monthly). Returns decile returns."""
    url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Portfolios_Formed_on_BE-ME_CSV.zip"
    print("Downloading BE/ME Portfolios CSV...")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    fname = [n for n in z.namelist() if n.endswith('.CSV') or n.endswith('.csv')][0]
    raw = z.read(fname).decode('latin-1')

    lines = raw.splitlines()

    # We want "Value Weight Returns -- Monthly" section with decile columns
    # Look for the section header and the row with "Lo 10" or decile labels
    section_start = None
    header_row_idx = None
    for i, line in enumerate(lines):
        if 'Value Weight Returns' in line and 'Monthly' in line:
            section_start = i
        if section_start is not None and header_row_idx is None:
            parts = [p.strip() for p in line.split(',')]
            # Decile header row typically has Lo 10, Dec 2 ... Hi 10 or similar
            if any(p in ['Lo 10', 'Hi 10', 'Lo10', 'Hi10', 'Low', 'High'] for p in parts):
                header_row_idx = i
                break

    if header_row_idx is None:
        # Fallback: just find the first row after section_start that has >=11 comma-sep float-like cols
        for i in range(section_start or 0, len(lines)):
            parts = [p.strip() for p in lines[i].split(',')]
            if len(parts) >= 12:
                # check if second element looks like a column header (not digit)
                if parts[1] and not parts[1][0].isdigit() and parts[1][0] != '-':
                    header_row_idx = i
                    break

    if header_row_idx is None:
        print("  WARNING: Could not find BE/ME decile header. Skipping value spread.")
        return None

    col_names = [p.strip() for p in lines[header_row_idx].split(',')]
    # Collect data rows (6-digit date)
    rows = []
    section_end = None
    for i in range(header_row_idx + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            # Check if next section follows
            section_end = i
            break
        parts = [p.strip() for p in line.split(',')]
        if len(parts) >= 2:
            date_str = parts[0].strip()
            if len(date_str) == 6 and date_str.isdigit():
                try:
                    vals = [float(x) if x.strip() not in ('', ' ') else np.nan
                            for x in parts[1:len(col_names)]]
                    row = {'Date': date_str}
                    for j, cn in enumerate(col_names[1:], 0):
                        if j < len(vals):
                            row[cn] = vals[j]
                    rows.append(row)
                except ValueError:
                    continue

    df = pd.DataFrame(rows)
    if df.empty:
        print("  WARNING: No BE/ME data parsed.")
        return None
    df['Date'] = pd.to_datetime(df['Date'], format='%Y%m') + pd.offsets.MonthEnd(0)
    df = df.set_index('Date').sort_index()
    # Convert pct → decimal
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce') / 100.0
    print(f"  BE/ME Portfolios loaded: {df.index[0].date()} → {df.index[-1].date()} ({len(df)} months)")
    return df


# ─────────────────────────────────────────────
# 2. ETF DATA FROM YFINANCE
# ─────────────────────────────────────────────

def get_etf_prices(tickers):
    """Download max history of adjusted close prices for tickers."""
    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance not available")
        return None

    print(f"Downloading ETF prices: {tickers}")
    data = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period='max', auto_adjust=True)
            if not hist.empty:
                s = hist['Close']
                s.index = s.index.tz_localize(None)
                s.index = s.index + pd.offsets.MonthEnd(0)  # will be used monthly
                data[ticker] = s
                print(f"  {ticker}: {s.index[0].date()} → {s.index[-1].date()} ({len(s)} days)")
        except Exception as e:
            print(f"  {ticker} failed: {e}")
    return data


def get_etf_pb(tickers):
    """Try to fetch P/B ratios from yfinance info."""
    try:
        import yfinance as yf
    except ImportError:
        return {}
    result = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            pb = info.get('priceToBook', None)
            result[t] = pb
        except Exception:
            result[t] = None
    return result


# ─────────────────────────────────────────────
# 3. ANALYSIS FUNCTIONS
# ─────────────────────────────────────────────

def decade_label(year):
    decade = (year // 10) * 10
    return f"{decade}s"


def compute_decade_table(factors_df):
    """Annual average returns by decade for SMB, HML, combined, Mkt-RF."""
    df = factors_df.copy()
    df['year'] = df.index.year
    df['decade'] = df['year'].apply(decade_label)
    df['SMB_HML'] = df['SMB'] + df['HML']

    # Annualize monthly returns: compound 12 months
    def annualize_monthly(series):
        """Compute annualized return from monthly returns."""
        return (1 + series).prod() ** (12 / len(series)) - 1

    decades = sorted(df['decade'].unique())
    rows = []
    for d in decades:
        sub = df[df['decade'] == d]
        if len(sub) < 12:  # Skip incomplete decades at edges
            continue
        rows.append({
            'Decade': d,
            'SMB': annualize_monthly(sub['SMB']),
            'HML': annualize_monthly(sub['HML']),
            'SMB+HML': annualize_monthly(sub['SMB_HML']),
            'Mkt-RF': annualize_monthly(sub['Mkt-RF']),
        })
    return pd.DataFrame(rows).set_index('Decade')


def compute_rolling_premium(factors_df, window_months=120):
    """Rolling 10yr annualized SMB+HML premium."""
    df = factors_df.copy()
    df['SMB_HML'] = df['SMB'] + df['HML']

    def rolling_ann(series, window):
        results = []
        for i in range(window - 1, len(series)):
            chunk = series.iloc[i - window + 1: i + 1]
            ann = (1 + chunk).prod() ** (12 / window) - 1
            results.append(ann)
        return pd.Series(results, index=series.index[window - 1:])

    roll = rolling_ann(df['SMB_HML'], window_months)
    roll_mkt = rolling_ann(df['Mkt-RF'], window_months)
    return roll, roll_mkt


def compute_etf_rolling_alpha(price_series_dict, window_years=5):
    """Compute rolling alpha of IWN vs SPY using OLS regression."""
    if 'IWN' not in price_series_dict or 'SPY' not in price_series_dict:
        print("  IWN or SPY data missing, skipping alpha computation.")
        return None, None

    iwn_daily = price_series_dict['IWN']
    spy_daily = price_series_dict['SPY']

    # Monthly returns
    iwn_m = iwn_daily.resample('ME').last().pct_change().dropna()
    spy_m = spy_daily.resample('ME').last().pct_change().dropna()

    combined = pd.DataFrame({'IWN': iwn_m, 'SPY': spy_m}).dropna()

    window = window_years * 12
    alphas_5yr = []
    alphas_3yr = []
    dates = []

    # 5yr rolling
    for i in range(window - 1, len(combined)):
        chunk = combined.iloc[i - window + 1: i + 1]
        x = chunk['SPY'].values
        y = chunk['IWN'].values
        # OLS: y = alpha + beta * x
        A = np.column_stack([np.ones(len(x)), x])
        try:
            coeffs, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
            alpha_monthly = coeffs[0]
            alpha_annual = (1 + alpha_monthly) ** 12 - 1
        except Exception:
            alpha_annual = np.nan
        alphas_5yr.append(alpha_annual)
        dates.append(combined.index[i])

    # 3yr rolling
    window3 = 3 * 12
    for i in range(window3 - 1, len(combined)):
        chunk = combined.iloc[i - window3 + 1: i + 1]
        x = chunk['SPY'].values
        y = chunk['IWN'].values
        A = np.column_stack([np.ones(len(x)), x])
        try:
            coeffs, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
            alpha_monthly = coeffs[0]
            alpha_annual = (1 + alpha_monthly) ** 12 - 1
        except Exception:
            alpha_annual = np.nan
        alphas_3yr.append(alpha_annual)

    alpha5_series = pd.Series(alphas_5yr, index=dates)
    alpha3_dates = combined.index[window3 - 1:]
    alpha3_series = pd.Series(alphas_3yr, index=alpha3_dates)

    return alpha5_series, alpha3_series


def compute_value_spread(beme_df):
    """Rolling 3yr spread between Hi and Lo B/M decile returns."""
    if beme_df is None:
        return None

    # Find hi and lo columns
    cols = beme_df.columns.tolist()
    hi_col = None
    lo_col = None
    for c in cols:
        cl = c.strip().lower().replace(' ', '')
        if cl in ['hi10', 'hi 10', 'high', 'hi']:
            hi_col = c
        if cl in ['lo10', 'lo 10', 'low', 'lo']:
            lo_col = c

    if hi_col is None:
        # Try numeric approach: last and first non-empty named columns
        named = [c for c in cols if c.strip()]
        if len(named) >= 2:
            lo_col = named[0]
            hi_col = named[-1]

    if hi_col is None or lo_col is None:
        print(f"  Could not identify Hi/Lo B/M columns. Available: {cols}")
        return None

    print(f"  Value spread using columns: Lo='{lo_col}', Hi='{hi_col}'")
    spread = beme_df[hi_col] - beme_df[lo_col]
    spread = spread.dropna()

    # Rolling 3yr annualized spread
    window = 36
    roll_spread = []
    dates = []
    for i in range(window - 1, len(spread)):
        chunk = spread.iloc[i - window + 1: i + 1]
        ann = (1 + chunk).prod() ** (12 / window) - 1
        roll_spread.append(ann)
        dates.append(spread.index[i])

    return pd.Series(roll_spread, index=dates)


def compute_pre_post_1992(factors_df):
    """Pre vs post 1992 (Fama-French publication) average stats."""
    df = factors_df.copy()
    df['SMB_HML'] = df['SMB'] + df['HML']

    def annualize(series):
        return (1 + series).prod() ** (12 / len(series)) - 1

    pre = df[df.index.year < 1992]
    post = df[df.index.year >= 1992]

    results = []
    for period_name, subset in [('Pre-1992', pre), ('Post-1992', post)]:
        results.append({
            'Period': period_name,
            'SMB Ann.': annualize(subset['SMB']),
            'HML Ann.': annualize(subset['HML']),
            'SMB+HML Ann.': annualize(subset['SMB_HML']),
            'Mkt-RF Ann.': annualize(subset['Mkt-RF']),
            'N Months': len(subset),
        })
    return pd.DataFrame(results).set_index('Period')


# ─────────────────────────────────────────────
# 4. HTML REPORT BUILDER
# ─────────────────────────────────────────────

def pct(v, decimals=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return 'N/A'
    return f"{v*100:.{decimals}f}%"


def build_html_report(factors_df, beme_df, price_dict, pb_dict):
    print("Building charts and HTML report...")

    # ── Compute all data ──
    decade_tbl = compute_decade_table(factors_df)
    roll_premium, roll_mkt = compute_rolling_premium(factors_df, 120)
    alpha5, alpha3 = compute_etf_rolling_alpha(price_dict)
    value_spread = compute_value_spread(beme_df)
    pre_post = compute_pre_post_1992(factors_df)

    # ── Chart 1: Rolling 10yr SMB+HML premium ──
    x1 = roll_premium.index.strftime('%Y-%m-%d').tolist()
    y1 = roll_premium.tolist()

    # Split for fill: positive vs negative
    y1_pos = [v if v >= 0 else 0 for v in y1]
    y1_neg = [v if v < 0 else 0 for v in y1]

    chart1_traces = [
        {
            "x": x1, "y": [round(v*100, 3) for v in y1_pos],
            "fill": "tozeroy", "fillcolor": "rgba(0,200,80,0.25)",
            "line": {"color": "#00c850", "width": 0},
            "mode": "lines", "name": "SMB+HML > 0", "type": "scatter",
            "showlegend": True
        },
        {
            "x": x1, "y": [round(v*100, 3) for v in y1_neg],
            "fill": "tozeroy", "fillcolor": "rgba(220,50,50,0.25)",
            "line": {"color": "#dc3232", "width": 0},
            "mode": "lines", "name": "SMB+HML < 0", "type": "scatter",
            "showlegend": True
        },
        {
            "x": x1, "y": [round(v*100, 3) for v in y1],
            "line": {"color": "#f0c040", "width": 2},
            "mode": "lines", "name": "10yr Rolling Ann. SMB+HML", "type": "scatter"
        }
    ]

    chart1_layout = {
        "title": {"text": "Rolling 10-Year Annualized SMB+HML Premium (1936–Present)",
                  "font": {"color": "#e0e0e0", "size": 16}},
        "paper_bgcolor": "#0f1117", "plot_bgcolor": "#141824",
        "font": {"color": "#b0b0b0"},
        "xaxis": {"gridcolor": "#2a2a3a", "title": "Date",
                  "tickfont": {"color": "#b0b0b0"}},
        "yaxis": {"gridcolor": "#2a2a3a", "title": "Annualized Return (%)",
                  "tickformat": ".1f", "ticksuffix": "%",
                  "tickfont": {"color": "#b0b0b0"},
                  "zeroline": True, "zerolinecolor": "#555566", "zerolinewidth": 1},
        "legend": {"bgcolor": "#1a1a2e", "bordercolor": "#333344"},
        "shapes": [
            # 1992 vertical line
            {"type": "line", "x0": "1992-01-01", "x1": "1992-01-01",
             "y0": 0, "y1": 1, "yref": "paper",
             "line": {"color": "#8888ff", "width": 2, "dash": "dash"}},
        ],
        "annotations": [
            {"x": "1992-01-01", "y": 0.97, "yref": "paper",
             "text": "FF 1992 Publication", "showarrow": False,
             "font": {"color": "#8888ff", "size": 11},
             "xanchor": "left"}
        ],
        "margin": {"l": 60, "r": 30, "t": 60, "b": 50},
        "height": 420
    }

    # ── Chart 2: IWN vs SPY rolling alpha ──
    if alpha5 is not None:
        x2_5 = alpha5.index.strftime('%Y-%m-%d').tolist()
        y2_5 = [round(v*100, 3) for v in alpha5.tolist()]
        x2_3 = alpha3.index.strftime('%Y-%m-%d').tolist()
        y2_3 = [round(v*100, 3) for v in alpha3.tolist()]
        chart2_traces = [
            {
                "x": x2_5, "y": y2_5,
                "line": {"color": "#f0c040", "width": 2},
                "mode": "lines", "name": "5yr Rolling Alpha", "type": "scatter"
            },
            {
                "x": x2_3, "y": y2_3,
                "line": {"color": "#00c8ff", "width": 1.5, "dash": "dot"},
                "mode": "lines", "name": "3yr Rolling Alpha", "type": "scatter"
            }
        ]
    else:
        chart2_traces = [{"x": [], "y": [], "mode": "lines", "name": "No data", "type": "scatter"}]

    chart2_layout = {
        "title": {"text": "Rolling Alpha: IWN vs SPY (OLS, Annualized)",
                  "font": {"color": "#e0e0e0", "size": 16}},
        "paper_bgcolor": "#0f1117", "plot_bgcolor": "#141824",
        "font": {"color": "#b0b0b0"},
        "xaxis": {"gridcolor": "#2a2a3a", "title": "Date",
                  "tickfont": {"color": "#b0b0b0"}},
        "yaxis": {"gridcolor": "#2a2a3a", "title": "Alpha (%/yr)",
                  "tickformat": ".1f", "ticksuffix": "%",
                  "tickfont": {"color": "#b0b0b0"},
                  "zeroline": True, "zerolinecolor": "#555566", "zerolinewidth": 1.5},
        "legend": {"bgcolor": "#1a1a2e", "bordercolor": "#333344"},
        "shapes": [
            {"type": "line", "x0": "2007-01-01", "x1": "2007-01-01",
             "y0": 0, "y1": 1, "yref": "paper",
             "line": {"color": "#ff6666", "width": 1, "dash": "dot"}},
            {"type": "line", "x0": "2020-01-01", "x1": "2020-01-01",
             "y0": 0, "y1": 1, "yref": "paper",
             "line": {"color": "#ff6666", "width": 1, "dash": "dot"}},
        ],
        "annotations": [
            {"x": "2007-06-01", "y": 0.95, "yref": "paper",
             "text": "GFC", "showarrow": False,
             "font": {"color": "#ff9999", "size": 10}, "xanchor": "left"},
            {"x": "2020-03-01", "y": 0.95, "yref": "paper",
             "text": "COVID", "showarrow": False,
             "font": {"color": "#ff9999", "size": 10}, "xanchor": "left"},
        ],
        "margin": {"l": 60, "r": 30, "t": 60, "b": 50},
        "height": 420
    }

    # ── Chart 3: Decade bar chart ──
    decades = decade_tbl.index.tolist()
    smb_vals  = [round(v*100, 2) for v in decade_tbl['SMB'].tolist()]
    hml_vals  = [round(v*100, 2) for v in decade_tbl['HML'].tolist()]
    comb_vals = [round(v*100, 2) for v in decade_tbl['SMB+HML'].tolist()]
    mkt_vals  = [round(v*100, 2) for v in decade_tbl['Mkt-RF'].tolist()]

    chart3_traces = [
        {"x": decades, "y": smb_vals, "name": "SMB",
         "type": "bar", "marker": {"color": "#00c8ff"}},
        {"x": decades, "y": hml_vals, "name": "HML",
         "type": "bar", "marker": {"color": "#f0c040"}},
        {"x": decades, "y": comb_vals, "name": "SMB+HML",
         "type": "bar", "marker": {"color": "#00c850"}},
        {"x": decades, "y": mkt_vals, "name": "Mkt-RF",
         "type": "bar", "marker": {"color": "#ff6644"}},
    ]
    chart3_layout = {
        "title": {"text": "Decade-by-Decade Factor Premiums (Annualized)",
                  "font": {"color": "#e0e0e0", "size": 16}},
        "paper_bgcolor": "#0f1117", "plot_bgcolor": "#141824",
        "font": {"color": "#b0b0b0"},
        "barmode": "group",
        "xaxis": {"gridcolor": "#2a2a3a", "title": "Decade",
                  "tickfont": {"color": "#b0b0b0"}},
        "yaxis": {"gridcolor": "#2a2a3a", "title": "Ann. Return (%/yr)",
                  "tickformat": ".1f", "ticksuffix": "%",
                  "tickfont": {"color": "#b0b0b0"},
                  "zeroline": True, "zerolinecolor": "#555566"},
        "legend": {"bgcolor": "#1a1a2e", "bordercolor": "#333344"},
        "margin": {"l": 60, "r": 30, "t": 60, "b": 50},
        "height": 420
    }

    # ── Chart 4: Value spread rolling 3yr ──
    if value_spread is not None:
        x4 = value_spread.index.strftime('%Y-%m-%d').tolist()
        y4 = [round(v*100, 3) for v in value_spread.tolist()]
        y4_pos = [v if v >= 0 else 0 for v in y4]
        y4_neg = [v if v < 0 else 0 for v in y4]
        chart4_traces = [
            {
                "x": x4, "y": y4_pos,
                "fill": "tozeroy", "fillcolor": "rgba(0,200,80,0.2)",
                "line": {"color": "#00c850", "width": 0},
                "mode": "lines", "name": "Spread > 0", "type": "scatter"
            },
            {
                "x": x4, "y": y4_neg,
                "fill": "tozeroy", "fillcolor": "rgba(220,50,50,0.2)",
                "line": {"color": "#dc3232", "width": 0},
                "mode": "lines", "name": "Spread < 0", "type": "scatter"
            },
            {
                "x": x4, "y": y4,
                "line": {"color": "#f0c040", "width": 2},
                "mode": "lines", "name": "3yr Rolling Hi−Lo B/M Spread", "type": "scatter"
            }
        ]
    else:
        chart4_traces = [{"x": [], "y": [], "mode": "lines", "name": "No data", "type": "scatter"}]

    chart4_layout = {
        "title": {"text": "Value Spread: Rolling 3yr Hi − Lo B/M Decile Return (Ann.)",
                  "font": {"color": "#e0e0e0", "size": 16}},
        "paper_bgcolor": "#0f1117", "plot_bgcolor": "#141824",
        "font": {"color": "#b0b0b0"},
        "xaxis": {"gridcolor": "#2a2a3a", "title": "Date",
                  "tickfont": {"color": "#b0b0b0"}},
        "yaxis": {"gridcolor": "#2a2a3a", "title": "Spread Ann. (%/yr)",
                  "tickformat": ".1f", "ticksuffix": "%",
                  "tickfont": {"color": "#b0b0b0"},
                  "zeroline": True, "zerolinecolor": "#555566"},
        "legend": {"bgcolor": "#1a1a2e", "bordercolor": "#333344"},
        "shapes": [
            {"type": "line", "x0": "1992-01-01", "x1": "1992-01-01",
             "y0": 0, "y1": 1, "yref": "paper",
             "line": {"color": "#8888ff", "width": 1.5, "dash": "dash"}},
        ],
        "margin": {"l": 60, "r": 30, "t": 60, "b": 50},
        "height": 420
    }

    # ── Summary table ──
    def row_html(row):
        def fmt(v):
            if isinstance(v, float) and not np.isnan(v):
                color = "#00c850" if v > 0 else "#dc3232"
                return f'<td style="color:{color};text-align:right">{v*100:.2f}%</td>'
            elif isinstance(v, int):
                return f'<td style="color:#aaa;text-align:right">{v}</td>'
            else:
                return f'<td style="color:#aaa;text-align:right">{v}</td>'
        cells = ''.join(fmt(row[c]) for c in ['SMB Ann.', 'HML Ann.', 'SMB+HML Ann.', 'Mkt-RF Ann.', 'N Months'])
        return f'<tr><td style="color:#e0e0e0;font-weight:bold;padding:8px 16px">{row.name}</td>{cells}</tr>'

    table_rows = ''.join(row_html(pre_post.loc[p]) for p in pre_post.index)

    # Decade table rows
    def decade_row(idx, row):
        def fc(v):
            color = "#00c850" if v > 0 else "#dc3232"
            return f'<td style="color:{color};text-align:right;padding:6px 14px">{v:.2f}%</td>'
        return (f'<tr><td style="color:#e0e0e0;padding:6px 14px">{idx}</td>'
                f'{fc(row["SMB"]*100)}{fc(row["HML"]*100)}'
                f'{fc(row["SMB+HML"]*100)}{fc(row["Mkt-RF"]*100)}</tr>')

    decade_rows = ''.join(decade_row(idx, row) for idx, row in decade_tbl.iterrows())

    # ETF P/B table
    pb_rows = ''
    for t, v in pb_dict.items():
        if v is not None:
            pb_rows += f'<tr><td style="color:#e0e0e0;padding:6px 14px">{t}</td><td style="color:#f0c040;text-align:right;padding:6px 14px">{v:.2f}x</td></tr>'
        else:
            pb_rows += f'<tr><td style="color:#e0e0e0;padding:6px 14px">{t}</td><td style="color:#888;text-align:right;padding:6px 14px">N/A</td></tr>'

    # ── Assemble HTML ──
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>French Factor Premium Analysis</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
  html, body {{
    background: #0f1117 !important;
    color: #b0b0b0;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    margin: 0; padding: 0;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
  h1 {{ color: #f0c040; border-bottom: 2px solid #2a2a3a; padding-bottom: 12px; }}
  h2 {{ color: #00c8ff; margin-top: 40px; }}
  .chart-box {{ background: #0f1117; border: 1px solid #2a2a3a; border-radius: 8px;
               margin: 20px 0; padding: 12px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th {{ background: #141824; color: #f0c040; text-align: right; padding: 8px 16px;
       border-bottom: 2px solid #333; }}
  th:first-child {{ text-align: left; }}
  tr:nth-child(even) {{ background: #141824; }}
  tr:hover {{ background: #1e2030; }}
  .summary-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  .stat-card {{
    background: #141824; border: 1px solid #2a2a3a; border-radius: 8px;
    padding: 16px 20px;
  }}
  .stat-label {{ color: #888; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }}
  .stat-value {{ color: #f0c040; font-size: 24px; font-weight: bold; margin-top: 4px; }}
  .note {{ color: #666; font-size: 12px; margin-top: 8px; }}
  .green {{ color: #00c850 !important; }}
  .red {{ color: #dc3232 !important; }}
  .yellow {{ color: #f0c040 !important; }}
  .section {{ margin-bottom: 48px; }}
</style>
</head>
<body>
<div class="container">

<h1>Ken French Factor Premium Analysis</h1>
<p style="color:#666">
  Data: Ken French Data Library | ETF prices via yfinance |
  Generated {pd.Timestamp.now().strftime('%Y-%m-%d')}
</p>

<div class="section">
<h2>1. Rolling 10-Year SMB+HML Premium</h2>
<p style="color:#888;font-size:13px">
  The combined size+value premium (SMB+HML) rolling 10yr annualized, 1936–present.
  Vertical dashed line marks the <strong style="color:#8888ff">1992 Fama-French publication</strong>
  — after which the premium should theoretically compress if arbitraged away.
</p>
<div class="chart-box" id="chart1"></div>
</div>

<div class="section">
<h2>2. IWN vs SPY Rolling Alpha (OLS)</h2>
<p style="color:#888;font-size:13px">
  Rolling 5yr (yellow) and 3yr (blue dashed) annualized alpha of IWN (Russell 2000 Value ETF)
  vs SPY (S&P 500). Positive alpha = IWN outperforms after adjusting for market beta.
</p>
<div class="chart-box" id="chart2"></div>
</div>

<div class="section">
<h2>3. Decade-by-Decade Factor Premiums</h2>
<p style="color:#888;font-size:13px">
  Annualized average returns for each decade. SMB = small minus big cap.
  HML = high minus low B/M (value). Combined = SMB+HML. All vs market excess return.
</p>
<div class="chart-box" id="chart3"></div>

<h3 style="color:#888;margin-top:24px">Decade Detail Table</h3>
<table>
  <thead>
    <tr>
      <th style="text-align:left">Decade</th>
      <th>SMB (Ann.)</th><th>HML (Ann.)</th>
      <th>SMB+HML (Ann.)</th><th>Mkt-RF (Ann.)</th>
    </tr>
  </thead>
  <tbody>{decade_rows}</tbody>
</table>
</div>

<div class="section">
<h2>4. Value Spread — Hi vs Lo B/M Decile</h2>
<p style="color:#888;font-size:13px">
  Rolling 3yr annualized return difference between the highest and lowest
  B/M decile portfolios (Ken French data). High spread = value stocks are
  generating large premiums relative to growth. Low/negative = value cold streak.
</p>
<div class="chart-box" id="chart4"></div>
</div>

<div class="section">
<h2>5. Summary: Pre vs Post 1992 Publication</h2>
<table>
  <thead>
    <tr>
      <th style="text-align:left">Period</th>
      <th>SMB Ann.</th><th>HML Ann.</th>
      <th>SMB+HML Ann.</th><th>Mkt-RF Ann.</th><th>N Months</th>
    </tr>
  </thead>
  <tbody>{table_rows}</tbody>
</table>
<p class="note">
  Pre-1992: historical data used to <em>construct</em> the model.
  Post-1992: out-of-sample. A declining premium post-1992 is consistent with
  arbitrage/factor crowding — though HML has recovered since 2022.
</p>
</div>

<div class="section">
<h2>6. Current ETF Price-to-Book Ratios</h2>
<table style="width:400px">
  <thead>
    <tr>
      <th style="text-align:left">Ticker</th>
      <th>P/B Ratio</th>
    </tr>
  </thead>
  <tbody>{pb_rows if pb_rows else '<tr><td colspan="2" style="color:#666;text-align:center;padding:12px">No P/B data available</td></tr>'}</tbody>
</table>
<p class="note">
  Lower P/B = cheaper relative to book value (tilts toward value).
  ZPRX.DE = SPDR MSCI Europe Small Cap Value Weighted ETF.
  VWCE.DE = Vanguard FTSE All-World.
</p>
</div>

</div><!-- end container -->

<script>
var c1_traces = {json.dumps(chart1_traces)};
var c1_layout = {json.dumps(chart1_layout)};
Plotly.newPlot('chart1', c1_traces, c1_layout, {{responsive: true, displayModeBar: false}});

var c2_traces = {json.dumps(chart2_traces)};
var c2_layout = {json.dumps(chart2_layout)};
Plotly.newPlot('chart2', c2_traces, c2_layout, {{responsive: true, displayModeBar: false}});

var c3_traces = {json.dumps(chart3_traces)};
var c3_layout = {json.dumps(chart3_layout)};
Plotly.newPlot('chart3', c3_traces, c3_layout, {{responsive: true, displayModeBar: false}});

var c4_traces = {json.dumps(chart4_traces)};
var c4_layout = {json.dumps(chart4_layout)};
Plotly.newPlot('chart4', c4_traces, c4_layout, {{responsive: true, displayModeBar: false}});
</script>
</body>
</html>"""

    return html


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    os.makedirs('/app/research', exist_ok=True)

    # 1. Download French Factors
    factors_df = download_french_factors()

    # 2. Download BE/ME Portfolios
    beme_df = download_french_beme()

    # 3. ETF prices
    price_dict = get_etf_prices(['IWN', 'SPY'])

    # 4. P/B ratios
    print("Fetching P/B ratios for ETFs...")
    pb_tickers = ['ZPRX.DE', 'VWCE.DE', 'IWN', 'SPY']
    pb_dict = get_etf_pb(pb_tickers)
    for t, v in pb_dict.items():
        print(f"  {t} P/B: {v}")

    # 5. Build and save report
    html = build_html_report(factors_df, beme_df, price_dict, pb_dict)
    out_path = '/app/research/french_factor_report.html'
    with open(out_path, 'w') as f:
        f.write(html)
    print(f"\nReport saved to {out_path}")
    print(f"File size: {os.path.getsize(out_path):,} bytes")


if __name__ == '__main__':
    main()
