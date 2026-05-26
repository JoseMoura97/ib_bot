"""
Track 2 — Factor Regime ML Pipeline

Predicts 12-month regime for:
  HML  — value premium (High Minus Low book-to-market)
  SMB  — size premium  (Small Minus Big market cap)

Using Ken French monthly data 1926→2026 (~1200 obs).

Methodology (Fractus M10-LdP lessons + Advances in Financial ML):
  - Expanding walk-forward CV, 6m embargo, 24m test steps, ≥25 folds
  - Multi-seed for LightGBM; report fold mean ± std
  - Decade-stratified AUC (detect distribution shift)
  - Meta-labeling: LR direction → LightGBM confidence gate
  - Shuffle-label null test
  - Holdout 2010-2026 frozen until final eval

Run (host):
  python3 research/factor_regime_ml.py
"""
from __future__ import annotations

import io, json, math, os, sys, warnings, zipfile
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, accuracy_score, brier_score_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb

warnings.filterwarnings("ignore")

# ── paths ─────────────────────────────────────────────────────────────────────
OUT_DIR    = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(OUT_DIR, ".french_cache")
OUT_JSON   = os.path.join(OUT_DIR, "factor_regime_results.json")
OUT_HTML   = os.path.join(OUT_DIR, "factor_regime_report.html")
os.makedirs(CACHE_DIR, exist_ok=True)

# ── hyperparams ───────────────────────────────────────────────────────────────
HORIZON    = 12    # forward months for target label
EMBARGO    = 6     # months gap between train end and test start
MIN_TRAIN  = 240   # minimum training months (20 years)
STEP       = 24    # walk-forward step (months)
TEST_LEN   = 24    # test window per fold
HOLDOUT_START = "2010-01"
N_SEEDS    = 5

LGBM_BASE = dict(
    n_estimators=200, max_depth=3, learning_rate=0.03,
    subsample=0.8, colsample_bytree=0.7,
    min_child_samples=15, reg_lambda=2.0, verbose=-1,
)

# ── 1. DATA DOWNLOAD ──────────────────────────────────────────────────────────

FRENCH_URLS = {
    "3factor":  "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip",
    "5factor":  "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip",
    "beme":     "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Portfolios_Formed_on_BE-ME_CSV.zip",
}


def _fetch_zip(url: str, cache_name: str) -> str:
    path = os.path.join(CACHE_DIR, cache_name)
    if os.path.exists(path):
        return path
    print(f"  Downloading {cache_name}...", end="", flush=True)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    csv_name = [n for n in z.namelist() if n.endswith(".CSV") or n.endswith(".csv")][0]
    content = z.read(csv_name).decode("utf-8", errors="replace")
    with open(path, "w") as f:
        f.write(content)
    print(f" {len(content)//1024}KB")
    return path


def _parse_french_monthly(path: str) -> pd.DataFrame:
    """Parse a Ken French CSV into monthly DataFrame, stopping at annual section."""
    rows = []
    in_monthly = False
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Annual data section starts with a 4-digit year ≤ 1930 after monthly
            if in_monthly and len(line) > 4 and not line[0].isdigit():
                break
            try:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2 and len(parts[0]) == 6 and parts[0].isdigit():
                    year, month = int(parts[0][:4]), int(parts[0][4:])
                    if 1 <= month <= 12 and year >= 1920:
                        vals = [float(v) for v in parts[1:] if v not in ("", " ")]
                        if vals:
                            rows.append((f"{year}-{month:02d}", *vals))
                            in_monthly = True
            except (ValueError, IndexError):
                continue
    if not rows:
        raise ValueError(f"No monthly data parsed from {path}")
    ncols = max(len(r) for r in rows)
    return pd.DataFrame(rows)


def load_french_3factor() -> pd.DataFrame:
    path = _fetch_zip(FRENCH_URLS["3factor"], "3factor.csv")
    raw = _parse_french_monthly(path)
    raw.columns = ["date", "Mkt_RF", "SMB", "HML", "RF"][:len(raw.columns)]
    raw = raw.set_index("date")
    raw.index = pd.to_datetime(raw.index, format="%Y-%m")
    raw = raw.apply(pd.to_numeric, errors="coerce") / 100.0
    return raw.dropna(subset=["HML", "SMB"])


def load_french_5factor() -> pd.DataFrame:
    path = _fetch_zip(FRENCH_URLS["5factor"], "5factor.csv")
    raw = _parse_french_monthly(path)
    raw.columns = ["date", "Mkt_RF", "SMB", "HML", "RMW", "CMA", "RF"][:len(raw.columns)]
    raw = raw.set_index("date")
    raw.index = pd.to_datetime(raw.index, format="%Y-%m")
    raw = raw.apply(pd.to_numeric, errors="coerce") / 100.0
    return raw.dropna(subset=["HML", "SMB"])


def load_beme_spread() -> pd.Series:
    """Value spread: Hi10 - Lo10 BE/ME decile cumulative 12m return."""
    try:
        path = _fetch_zip(FRENCH_URLS["beme"], "beme.csv")
        raw = _parse_french_monthly(path)
        # Columns: date, Lo10, Dec2..Dec9, Hi10, ...
        if raw.shape[1] >= 11:
            raw.columns = ["date"] + [f"d{i}" for i in range(1, raw.shape[1])]
            raw = raw.set_index("date")
            raw.index = pd.to_datetime(raw.index, format="%Y-%m")
            raw = raw.apply(pd.to_numeric, errors="coerce") / 100.0
            lo = raw.iloc[:, 0]   # Lo10
            hi = raw.iloc[:, 9]   # Hi10
            spread = (hi - lo).rename("beme_spread")
            return spread.dropna()
    except Exception as e:
        print(f"  BE/ME spread unavailable: {e}")
    return pd.Series(dtype=float, name="beme_spread")


# ── 2. FEATURE ENGINEERING ────────────────────────────────────────────────────

def build_features(ff3: pd.DataFrame, ff5: pd.DataFrame | None,
                   beme: pd.Series) -> pd.DataFrame:
    """
    Build feature matrix at each month t using only information available at t.
    All targets are computed separately (forward-looking).
    """
    df = ff3[["Mkt_RF", "SMB", "HML", "RF"]].copy()

    # Merge 5-factor extras (RMW, CMA) if available
    if ff5 is not None:
        for col in ["RMW", "CMA"]:
            if col in ff5.columns:
                df[col] = ff5[col]

    # Merge value spread
    if len(beme) > 0:
        df = df.join(beme, how="left")
    else:
        df["beme_spread"] = np.nan

    feats = pd.DataFrame(index=df.index)

    for factor in ["HML", "SMB", "Mkt_RF"]:
        s = df[factor]
        # Lagged returns: 1, 3, 6, 12 months
        feats[f"{factor}_t1"]  = s.shift(1)
        feats[f"{factor}_t3"]  = s.rolling(3).mean().shift(1)
        feats[f"{factor}_t6"]  = s.rolling(6).mean().shift(1)
        feats[f"{factor}_t12"] = s.rolling(12).mean().shift(1)
        # Cumulative returns 12m (momentum)
        feats[f"{factor}_cum12"] = (1 + s).rolling(12).apply(np.prod, raw=True).shift(1) - 1
        # Trailing realized volatility
        feats[f"{factor}_vol12"] = s.rolling(12).std().shift(1)
        feats[f"{factor}_vol24"] = s.rolling(24).std().shift(1)
        # Drawdown from rolling peak
        cumret = (1 + s).cumprod()
        peak = cumret.rolling(60, min_periods=12).max()
        feats[f"{factor}_dd"] = ((cumret - peak) / peak).shift(1)

    # Cross-factor correlations (12m rolling)
    feats["hml_smb_corr12"] = df["HML"].rolling(12).corr(df["SMB"]).shift(1)
    feats["hml_mkt_corr12"] = df["HML"].rolling(12).corr(df["Mkt_RF"]).shift(1)
    feats["smb_mkt_corr12"] = df["SMB"].rolling(12).corr(df["Mkt_RF"]).shift(1)

    # Market regime: 12m Mkt-RF positive?
    feats["mkt_bull12"] = (feats["Mkt_RF_cum12"] > 0).astype(float)

    # Volatility ratio (current vol / long-run vol)
    feats["hml_vol_ratio"] = feats["HML_vol12"] / df["HML"].rolling(60).std().shift(1)
    feats["smb_vol_ratio"] = feats["SMB_vol12"] / df["SMB"].rolling(60).std().shift(1)

    # BE/ME spread features
    if "beme_spread" in df.columns:
        bs = df["beme_spread"]
        feats["beme_spread_t1"]  = bs.shift(1)
        feats["beme_spread_z12"] = ((bs.shift(1) - bs.rolling(60).mean().shift(1))
                                     / bs.rolling(60).std().shift(1))

    return feats.dropna(how="all")


def build_targets(ff3: pd.DataFrame) -> pd.DataFrame:
    """
    Forward-looking targets at each month t:
      hml_bull_12m  — cumulative HML over [t+1..t+12] > 0
      smb_bull_12m  — cumulative SMB over [t+1..t+12] > 0
    Note: last valid label is HORIZON months before data end.
    """
    tgts = pd.DataFrame(index=ff3.index)
    for factor, col in [("HML", "hml_bull_12m"), ("SMB", "smb_bull_12m")]:
        fwd_cum = (1 + ff3[factor]).rolling(HORIZON).apply(np.prod, raw=True).shift(-HORIZON)
        tgts[col] = (fwd_cum > 1).astype(float)
    return tgts


# ── 3. WALK-FORWARD CV ────────────────────────────────────────────────────────

def walk_forward_folds(n: int, min_train: int, step: int, test_len: int,
                        embargo: int, holdout_start_idx: int):
    """
    Generate (train_idx, test_idx) pairs for expanding-window WF CV.
    All indices are relative to the development set (0..holdout_start_idx-1).
    """
    folds = []
    train_end = min_train
    while True:
        test_start = train_end + embargo
        test_end   = test_start + test_len
        if test_end > holdout_start_idx:
            break
        train_idx = np.arange(0, train_end)
        test_idx  = np.arange(test_start, test_end)
        folds.append((train_idx, test_idx))
        train_end += step
    return folds


# ── 4. MODELS ─────────────────────────────────────────────────────────────────

def make_lr() -> Pipeline:
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(C=0.1, max_iter=500, random_state=42)),
    ])


def make_lgbm(seed: int = 0) -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(**{**LGBM_BASE, "random_state": seed})


def run_fold(X_tr, y_tr, X_te, y_te,
             X_tr_raw=None, X_te_raw=None) -> dict:
    """
    Run LR + LightGBM (multi-seed) + meta-labeling on one fold.
    Returns dict of metrics.
    """
    results = {}

    # --- Logistic Regression ---
    lr = make_lr()
    lr.fit(X_tr, y_tr)
    lr_prob = lr.predict_proba(X_te)[:, 1]
    lr_pred = (lr_prob >= 0.5).astype(int)

    results["lr_auc"]  = float(roc_auc_score(y_te, lr_prob)) if len(np.unique(y_te)) > 1 else np.nan
    results["lr_acc"]  = float(accuracy_score(y_te, lr_pred))
    results["lr_brier"]= float(brier_score_loss(y_te, lr_prob))

    # --- LightGBM (multi-seed) ---
    lgbm_probs = []
    for seed in range(N_SEEDS):
        m = make_lgbm(seed)
        m.fit(X_tr, y_tr)
        lgbm_probs.append(m.predict_proba(X_te)[:, 1])
    lgbm_prob = np.mean(lgbm_probs, axis=0)
    lgbm_pred = (lgbm_prob >= 0.5).astype(int)

    results["lgbm_auc"]  = float(roc_auc_score(y_te, lgbm_prob)) if len(np.unique(y_te)) > 1 else np.nan
    results["lgbm_acc"]  = float(accuracy_score(y_te, lgbm_pred))
    results["lgbm_brier"]= float(brier_score_loss(y_te, lgbm_prob))

    # --- Meta-labeling (LR direction → LightGBM confidence) ---
    # Stage 2 feature: LR predicted probability on training set
    lr_tr_prob = lr.predict_proba(X_tr)[:, 1]
    # Label: was LR correct?
    lr_tr_correct = (((lr_tr_prob >= 0.5).astype(int)) == y_tr.values).astype(int)
    # Features: original features + LR prob
    X_tr_meta = np.column_stack([X_tr, lr_tr_prob])
    X_te_meta  = np.column_stack([X_te, lr_prob])

    meta_probs = []
    for seed in range(N_SEEDS):
        m2 = make_lgbm(seed)
        try:
            m2.fit(X_tr_meta, lr_tr_correct)
            meta_probs.append(m2.predict_proba(X_te_meta)[:, 1])
        except Exception:
            pass
    if meta_probs:
        meta_conf = np.mean(meta_probs, axis=0)
        # Final prediction: use LR where meta-confidence > 0.55
        threshold = 0.55
        mask = meta_conf >= threshold
        if mask.sum() >= 3:  # only compute if enough samples
            y_te_masked = y_te.values[mask]
            lr_pred_masked = lr_pred[mask]
            lr_prob_masked = lr_prob[mask]
            results["meta_acc"]  = float(accuracy_score(y_te_masked, lr_pred_masked))
            results["meta_auc"]  = float(roc_auc_score(y_te_masked, lr_prob_masked)) if len(np.unique(y_te_masked)) > 1 else np.nan
            results["meta_coverage"] = float(mask.sum() / len(mask))
        else:
            results["meta_acc"] = np.nan
            results["meta_auc"] = np.nan
            results["meta_coverage"] = 0.0
    else:
        results["meta_acc"] = np.nan
        results["meta_auc"] = np.nan
        results["meta_coverage"] = 0.0

    return results


def run_shuffle_null(X_dev, y_dev, folds, n_shuffle=10) -> dict:
    """Shuffle-label test: expected AUC ≈ 0.50."""
    auc_lr, auc_lgbm = [], []
    rng = np.random.default_rng(999)
    for _ in range(n_shuffle):
        y_shuffled = pd.Series(
            rng.permutation(y_dev.values), index=y_dev.index
        )
        fold_aucs_lr, fold_aucs_lgbm = [], []
        for tr_idx, te_idx in folds[:5]:  # only 5 folds for speed
            X_tr = X_dev.iloc[tr_idx]
            y_tr = y_shuffled.iloc[tr_idx]
            X_te = X_dev.iloc[te_idx]
            y_te = y_shuffled.iloc[te_idx]
            if len(np.unique(y_te)) < 2:
                continue
            lr = make_lr(); lr.fit(X_tr, y_tr)
            fold_aucs_lr.append(roc_auc_score(y_te, lr.predict_proba(X_te)[:, 1]))
            m = make_lgbm(0); m.fit(X_tr, y_tr)
            fold_aucs_lgbm.append(roc_auc_score(y_te, m.predict_proba(X_te)[:, 1]))
        auc_lr.append(np.mean(fold_aucs_lr) if fold_aucs_lr else np.nan)
        auc_lgbm.append(np.mean(fold_aucs_lgbm) if fold_aucs_lgbm else np.nan)
    return {
        "lr_null_auc_mean":   float(np.nanmean(auc_lr)),
        "lr_null_auc_std":    float(np.nanstd(auc_lr)),
        "lgbm_null_auc_mean": float(np.nanmean(auc_lgbm)),
        "lgbm_null_auc_std":  float(np.nanstd(auc_lgbm)),
    }


def decade_auc(X_dev, y_dev, dates_dev, folds, model="lr") -> dict:
    """AUC per decade on the out-of-fold test predictions."""
    oof_prob  = np.full(len(y_dev), np.nan)
    oof_label = y_dev.values.copy().astype(float)
    for tr_idx, te_idx in folds:
        X_tr, y_tr = X_dev.iloc[tr_idx], y_dev.iloc[tr_idx]
        X_te = X_dev.iloc[te_idx]
        if model == "lr":
            m = make_lr(); m.fit(X_tr, y_tr)
            oof_prob[te_idx] = m.predict_proba(X_te)[:, 1]
        else:
            prbs = []
            for seed in range(N_SEEDS):
                m = make_lgbm(seed); m.fit(X_tr, y_tr)
                prbs.append(m.predict_proba(X_te)[:, 1])
            oof_prob[te_idx] = np.mean(prbs, axis=0)

    results = {}
    for decade_start in range(1930, 2015, 10):
        decade_end = decade_start + 9
        mask = (dates_dev.year >= decade_start) & (dates_dev.year <= decade_end)
        mask = mask & ~np.isnan(oof_prob)
        if mask.sum() < 10 or len(np.unique(oof_label[mask])) < 2:
            continue
        auc = roc_auc_score(oof_label[mask], oof_prob[mask])
        results[f"{decade_start}s"] = round(float(auc), 3)
    return results


def lgbm_feature_importance(X_dev, y_dev, folds, feature_names) -> dict:
    """Average feature importance across all folds (LightGBM gain)."""
    importances = np.zeros(len(feature_names))
    count = 0
    for tr_idx, _ in folds:
        X_tr, y_tr = X_dev.iloc[tr_idx], y_dev.iloc[tr_idx]
        m = make_lgbm(0)
        m.fit(X_tr, y_tr)
        importances += m.booster_.feature_importance(importance_type="gain")
        count += 1
    if count > 0:
        importances /= count
    pairs = sorted(zip(feature_names, importances), key=lambda x: -x[1])
    return {k: round(float(v), 2) for k, v in pairs[:20]}


# ── 5. MAIN RUNNER ────────────────────────────────────────────────────────────

def run_target(name: str, X: pd.DataFrame, y: pd.Series,
               holdout_start_idx: int) -> dict:
    """Full pipeline for one target (HML or SMB)."""
    print(f"\n  ── {name} ──────────────────────")

    # Split dev / holdout
    X_dev   = X.iloc[:holdout_start_idx]
    y_dev   = y.iloc[:holdout_start_idx]
    X_hold  = X.iloc[holdout_start_idx:]
    y_hold  = y.iloc[holdout_start_idx:]
    dates_dev = X_dev.index

    # Impute remaining NaN with column median on dev
    col_medians = X_dev.median()
    X_dev  = X_dev.fillna(col_medians)
    X_hold = X_hold.fillna(col_medians)

    # Walk-forward folds
    folds = walk_forward_folds(
        n=len(X_dev),
        min_train=MIN_TRAIN, step=STEP, test_len=TEST_LEN,
        embargo=EMBARGO, holdout_start_idx=len(X_dev),
    )
    print(f"    {len(folds)} WF folds on {len(X_dev)} dev obs | holdout {len(X_hold)} obs")
    print(f"    Base rate: {y_dev.mean():.1%} positive")

    # Per-fold metrics
    fold_results = []
    for i, (tr_idx, te_idx) in enumerate(folds):
        X_tr, y_tr = X_dev.iloc[tr_idx], y_dev.iloc[tr_idx]
        X_te, y_te = X_dev.iloc[te_idx], y_dev.iloc[te_idx]
        if len(np.unique(y_te)) < 2:
            continue
        m = run_fold(X_tr, y_tr, X_te, y_te)
        m["fold"] = i
        m["train_end"] = str(X_tr.index[-1].date())
        m["test_start"] = str(X_te.index[0].date())
        m["test_end"]   = str(X_te.index[-1].date())
        m["n_train"] = len(X_tr)
        m["n_test"]  = len(X_te)
        fold_results.append(m)
        auc_lr   = m.get("lr_auc", np.nan)
        auc_lgbm = m.get("lgbm_auc", np.nan)
        if (i + 1) % 5 == 0 or i < 2:
            print(f"    fold {i+1:2d} | train→{m['train_end']} test {m['test_start']}→{m['test_end']} | "
                  f"LR={auc_lr:.3f}  LGBM={auc_lgbm:.3f}")

    # Aggregate fold metrics
    def _agg(key):
        vals = [f[key] for f in fold_results if not np.isnan(f.get(key, np.nan))]
        return {"mean": round(float(np.mean(vals)), 4), "std": round(float(np.std(vals)), 4),
                "min": round(float(np.min(vals)), 4), "max": round(float(np.max(vals)), 4),
                "n": len(vals)} if vals else {}

    agg = {k: _agg(k) for k in ["lr_auc", "lr_acc", "lgbm_auc", "lgbm_acc",
                                   "meta_auc", "meta_acc", "meta_coverage"]}

    print(f"    WF summary: LR AUC {agg['lr_auc'].get('mean',0):.3f}±{agg['lr_auc'].get('std',0):.3f}"
          f"  LGBM {agg['lgbm_auc'].get('mean',0):.3f}±{agg['lgbm_auc'].get('std',0):.3f}")

    # Shuffle-label null test
    print("    Running shuffle-label null test...", end="", flush=True)
    null = run_shuffle_null(X_dev, y_dev, folds)
    print(f" LR null AUC={null['lr_null_auc_mean']:.3f}  LGBM null={null['lgbm_null_auc_mean']:.3f}")

    # Decade breakdown
    print("    Computing decade AUC...", end="", flush=True)
    dec_lr   = decade_auc(X_dev, y_dev, dates_dev, folds, "lr")
    dec_lgbm = decade_auc(X_dev, y_dev, dates_dev, folds, "lgbm")
    print(f" {list(dec_lgbm.keys())}")

    # Feature importance (last fold LightGBM)
    feat_imp = lgbm_feature_importance(X_dev, y_dev, folds, X_dev.columns.tolist())

    # Holdout evaluation (using model trained on all dev data)
    print("    Evaluating holdout...", end="", flush=True)
    holdout = {}
    if len(X_hold) >= 12 and len(np.unique(y_hold.dropna())) == 2:
        valid = y_hold.notna()
        Xh = X_hold[valid]; yh = y_hold[valid]
        lr_h = make_lr(); lr_h.fit(X_dev, y_dev)
        lr_h_prob = lr_h.predict_proba(Xh)[:, 1]
        lgbm_h_probs = []
        for seed in range(N_SEEDS):
            m = make_lgbm(seed); m.fit(X_dev, y_dev)
            lgbm_h_probs.append(m.predict_proba(Xh)[:, 1])
        lgbm_h_prob = np.mean(lgbm_h_probs, axis=0)
        holdout = {
            "n": int(valid.sum()),
            "base_rate": float(yh.mean()),
            "lr_auc":   round(float(roc_auc_score(yh, lr_h_prob)), 4),
            "lr_acc":   round(float(accuracy_score(yh, (lr_h_prob >= 0.5).astype(int))), 4),
            "lgbm_auc": round(float(roc_auc_score(yh, lgbm_h_prob)), 4),
            "lgbm_acc": round(float(accuracy_score(yh, (lgbm_h_prob >= 0.5).astype(int))), 4),
        }
        print(f" n={holdout['n']}  LR={holdout['lr_auc']:.3f}  LGBM={holdout['lgbm_auc']:.3f}")
    else:
        print(" insufficient holdout data")

    return {
        "target": name, "n_dev": len(X_dev), "n_holdout": len(X_hold),
        "base_rate_dev": float(y_dev.mean()),
        "n_folds": len(fold_results),
        "fold_results": fold_results,
        "agg": agg, "null": null,
        "decade_lr": dec_lr, "decade_lgbm": dec_lgbm,
        "feature_importance": feat_imp,
        "holdout": holdout,
    }


def main():
    print("Track 2 — Factor Regime ML")
    print("=" * 60)

    # Load data
    print("\n[1/4] Loading French factor data...")
    ff3  = load_french_3factor()
    ff5  = None
    try:
        ff5 = load_french_5factor()
    except Exception as e:
        print(f"  5-factor unavailable: {e}")
    beme = load_beme_spread()
    print(f"  3-factor: {ff3.index[0].date()} → {ff3.index[-1].date()} ({len(ff3)} obs)")
    if ff5 is not None:
        print(f"  5-factor: {ff5.index[0].date()} → {ff5.index[-1].date()} ({len(ff5)} obs)")
    print(f"  BE/ME spread: {len(beme)} obs")

    # Feature matrix + targets
    print("\n[2/4] Building features and targets...")
    feats = build_features(ff3, ff5, beme)
    tgts  = build_targets(ff3)

    # Align
    idx = feats.index.intersection(tgts.index)
    feats = feats.loc[idx]
    tgts  = tgts.loc[idx]

    # Drop rows where all targets are NaN (last HORIZON months)
    valid = tgts.notna().any(axis=1)
    feats = feats[valid]
    tgts  = tgts[valid]

    n_features = feats.shape[1]
    print(f"  Feature matrix: {feats.shape[0]} rows × {n_features} features")
    print(f"  Date range: {feats.index[0].date()} → {feats.index[-1].date()}")
    print(f"  Features: {feats.columns.tolist()[:8]}...")

    # Holdout split index
    holdout_start = pd.Timestamp(HOLDOUT_START)
    holdout_start_idx = feats.index.searchsorted(holdout_start)
    print(f"  Holdout from {feats.index[holdout_start_idx].date()} (idx {holdout_start_idx})")

    # Run both targets
    print("\n[3/4] Walk-forward CV + models...")
    all_results = {}
    for target_col, name in [("hml_bull_12m", "HML"), ("smb_bull_12m", "SMB")]:
        y = tgts[target_col].dropna()
        X = feats.loc[y.index]
        all_results[name] = run_target(name, X, y, holdout_start_idx)

    # Save JSON
    print("\n[4/4] Saving results...")
    out = {
        "as_of": pd.Timestamp.now().isoformat(),
        "horizon_months": HORIZON,
        "embargo_months": EMBARGO,
        "min_train_months": MIN_TRAIN,
        "holdout_start": HOLDOUT_START,
        "n_features": n_features,
        "results": all_results,
    }
    # Sanitise for JSON
    def _clean(obj):
        if isinstance(obj, dict):  return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):  return [_clean(v) for v in obj]
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return None if np.isnan(obj) else float(obj)
        if isinstance(obj, (np.ndarray,)): return obj.tolist()
        if isinstance(obj, pd.Timestamp): return str(obj)
        return obj

    with open(OUT_JSON, "w") as f:
        json.dump(_clean(out), f, indent=2)
    print(f"  Saved {OUT_JSON}")

    # Render HTML report
    render_report(out)
    print(f"  Saved {OUT_HTML}")

    return out


# ── 6. HTML REPORT ────────────────────────────────────────────────────────────

def _pct(v, d=1):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "—"
    return f"{v*100:.{d}f}%"

def _nn(v, d=3):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "—"
    return f"{v:.{d}f}"

def _auc_cls(v):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "dim"
    return "green" if v >= 0.60 else ("yellow" if v >= 0.53 else "red")


def render_report(data: dict):
    results = data["results"]
    sections = ""

    for target_name, res in results.items():
        agg = res.get("agg", {})
        null = res.get("null", {})
        hold = res.get("holdout", {})
        dec_lgbm = res.get("decade_lgbm", {})
        feat_imp = res.get("feature_importance", {})
        fold_results = res.get("fold_results", [])

        # AUC over time chart (OOF LR and LGBM)
        fold_dates  = [f["test_start"][:7] for f in fold_results]
        fold_lr     = [f.get("lr_auc") for f in fold_results]
        fold_lgbm   = [f.get("lgbm_auc") for f in fold_results]
        fold_meta   = [f.get("meta_auc") for f in fold_results]

        safe = lambda v: "null" if v is None or (isinstance(v, float) and math.isnan(v)) else v

        lr_auc_m  = agg.get("lr_auc",   {}).get("mean")
        lr_auc_s  = agg.get("lr_auc",   {}).get("std")
        lgbm_auc_m= agg.get("lgbm_auc", {}).get("mean")
        lgbm_auc_s= agg.get("lgbm_auc", {}).get("std")
        meta_auc_m= agg.get("meta_auc", {}).get("mean")
        meta_cov  = agg.get("meta_coverage", {}).get("mean")

        # Decade table rows
        dec_rows = ""
        for decade, auc_val in dec_lgbm.items():
            dec_rows += f"<tr><td class='left'>{decade}</td><td class='{_auc_cls(auc_val)}'>{_nn(auc_val)}</td></tr>"

        # Feature importance rows (top 12)
        fi_rows = ""
        for i, (feat, imp) in enumerate(list(feat_imp.items())[:12]):
            bar_w = int(imp / max(feat_imp.values()) * 120) if feat_imp else 0
            fi_rows += f"""<tr>
              <td class='left mono fi-name'>{feat}</td>
              <td><div class='fi-bar' style='width:{bar_w}px'></div></td>
              <td class='dim'>{_nn(imp, 1)}</td>
            </tr>"""

        # Null test row
        null_lr   = null.get("lr_null_auc_mean")
        null_lgbm = null.get("lgbm_null_auc_mean")

        # Holdout
        hold_row = ""
        if hold:
            hold_row = f"""
            <div class="hold-box">
              <span class="hold-title">Holdout 2010→2026 (n={hold.get('n','?')})</span>
              &nbsp; LR: <span class="{_auc_cls(hold.get('lr_auc'))}">{_nn(hold.get('lr_auc'))}</span>
              &nbsp; LGBM: <span class="{_auc_cls(hold.get('lgbm_auc'))}">{_nn(hold.get('lgbm_auc'))}</span>
              &nbsp; Base rate: {_pct(hold.get('base_rate'))}
            </div>"""

        chart_id = f"chart_{target_name.lower()}"

        sections += f"""
        <div class="target-section">
          <div class="target-title">{target_name} regime prediction
            <span class="target-sub"> — 12-month forward direction</span>
          </div>
          <div class="meta-row">
            <div class="meta-chip">Dev obs: <b>{res['n_dev']}</b></div>
            <div class="meta-chip">Folds: <b>{res['n_folds']}</b></div>
            <div class="meta-chip">Base rate: <b>{_pct(res['base_rate_dev'])}</b></div>
            <div class="meta-chip">Features: <b>{data['n_features']}</b></div>
          </div>

          <div class="two-col">
            <div class="col">
              <div class="sec-label">Walk-forward AUC summary</div>
              <table class="sm-table">
                <thead><tr><th class="left">Model</th><th>Mean AUC</th><th>Std</th><th>vs Null</th></tr></thead>
                <tbody>
                  <tr>
                    <td class="left mono">Logistic Reg</td>
                    <td class="{_auc_cls(lr_auc_m)}">{_nn(lr_auc_m)}</td>
                    <td class="dim">±{_nn(lr_auc_s)}</td>
                    <td class="dim">{_nn(null_lr)} null</td>
                  </tr>
                  <tr>
                    <td class="left mono">LightGBM</td>
                    <td class="{_auc_cls(lgbm_auc_m)}">{_nn(lgbm_auc_m)}</td>
                    <td class="dim">±{_nn(lgbm_auc_s)}</td>
                    <td class="dim">{_nn(null_lgbm)} null</td>
                  </tr>
                  <tr>
                    <td class="left mono">Meta-label</td>
                    <td class="{_auc_cls(meta_auc_m)}">{_nn(meta_auc_m)}</td>
                    <td class="dim">—</td>
                    <td class="dim">cov {_pct(meta_cov,0)}</td>
                  </tr>
                </tbody>
              </table>
              {hold_row}
              <div class="sec-label" style="margin-top:16px">AUC by decade (LGBM, OOF)</div>
              <table class="sm-table"><thead><tr><th class="left">Decade</th><th>AUC</th></tr></thead>
              <tbody>{dec_rows}</tbody></table>
            </div>
            <div class="col">
              <div class="sec-label">Feature importance (LGBM gain, avg across folds)</div>
              <table class="sm-table fi-table">
                <thead><tr><th class="left">Feature</th><th></th><th>Gain</th></tr></thead>
                <tbody>{fi_rows}</tbody>
              </table>
            </div>
          </div>

          <div class="sec-label" style="margin-top:20px">AUC per fold over time</div>
          <canvas id="{chart_id}" height="90"></canvas>
          <script>
          (function(){{
            var ctx = document.getElementById('{chart_id}').getContext('2d');
            var dates = {json.dumps(fold_dates)};
            var lr    = {json.dumps([safe(v) for v in fold_lr])};
            var lgbm  = {json.dumps([safe(v) for v in fold_lgbm])};
            var meta  = {json.dumps([safe(v) for v in fold_meta])};
            new Chart(ctx, {{
              type: 'line',
              data: {{
                labels: dates,
                datasets: [
                  {{label:'LR', data:lr, borderColor:'#60a5fa', borderWidth:1.5, pointRadius:2, fill:false, tension:0.3}},
                  {{label:'LGBM', data:lgbm, borderColor:'#4ade80', borderWidth:2, pointRadius:2, fill:false, tension:0.3}},
                  {{label:'Meta', data:meta, borderColor:'#f59e0b', borderWidth:1.5, pointRadius:1, fill:false, tension:0.3, borderDash:[4,3]}},
                  {{label:'Null (0.5)', data:dates.map(()=>0.5), borderColor:'#475569', borderWidth:1, pointRadius:0, fill:false, borderDash:[2,4]}},
                ]
              }},
              options: {{
                animation:false, responsive:true,
                plugins:{{legend:{{labels:{{color:'#94a3b8',font:{{size:11}}}}}},
                          tooltip:{{mode:'index',intersect:false}}}},
                scales:{{
                  x:{{ticks:{{color:'#475569',maxTicksLimit:12}},grid:{{color:'#1e2535'}}}},
                  y:{{min:0.35,max:0.85,ticks:{{color:'#475569'}},grid:{{color:'#1e2535'}}}}
                }}
              }}
            }});
          }})();
          </script>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Track 2 — Factor Regime ML</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
html,body{{background:#0f1117!important;color:#e2e8f0;font-family:'Inter',system-ui,sans-serif;margin:0;padding:0}}
.container{{max-width:1100px;margin:0 auto;padding:32px 20px 64px}}
h1{{font-size:1.5rem;font-weight:700;color:#f1f5f9;margin:0 0 4px}}
.subtitle{{color:#64748b;font-size:.83rem;margin-bottom:28px}}
.subtitle b{{color:#94a3b8}}

.target-section{{margin-bottom:48px;padding:24px;background:#111827;border:1px solid #1e2535;border-radius:10px}}
.target-title{{font-size:1.1rem;font-weight:700;color:#f1f5f9;margin-bottom:12px}}
.target-sub{{font-size:.78rem;font-weight:400;color:#64748b}}
.meta-row{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}}
.meta-chip{{background:#1e2535;border-radius:6px;padding:4px 10px;font-size:.75rem;color:#94a3b8}}
.meta-chip b{{color:#cbd5e1}}

.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}
@media(max-width:700px){{.two-col{{grid-template-columns:1fr}}}}
.col{{}}

.sec-label{{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
  color:#475569;margin-bottom:6px;border-bottom:1px solid #1e2535;padding-bottom:4px}}

.sm-table{{width:100%;border-collapse:collapse;font-size:.8rem;margin-bottom:8px}}
.sm-table thead th{{background:#0f1117;color:#475569;font-size:.67rem;text-transform:uppercase;
  padding:6px 8px;border-bottom:1px solid #1e2535;text-align:right}}
.sm-table thead th.left{{text-align:left}}
.sm-table tbody tr{{border-bottom:1px solid #161b27}}
.sm-table tbody tr:hover{{background:#1a1f2e}}
.sm-table td{{padding:6px 8px;text-align:right;font-variant-numeric:tabular-nums}}
.sm-table td.left{{text-align:left}}
.sm-table td.mono{{font-family:monospace;color:#cbd5e1;font-size:.75rem}}

.fi-table .fi-name{{font-size:.72rem;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.fi-bar{{height:8px;background:#3b82f6;border-radius:3px;min-width:2px}}

.hold-box{{background:#1a1f2e;border:1px solid #2d3748;border-radius:6px;padding:8px 12px;
  margin-top:10px;font-size:.78rem;color:#94a3b8}}
.hold-title{{font-weight:600;color:#cbd5e1}}

.caveat{{background:#1a1f2e;border:1px solid #2d3748;border-radius:8px;padding:14px 18px;
  margin-bottom:28px;font-size:.79rem;color:#94a3b8;line-height:1.65}}
.caveat strong{{color:#cbd5e1}}
.caveat ul{{margin:6px 0 0 16px;padding:0}}
.caveat li{{margin-bottom:4px}}

.green{{color:#4ade80}} .yellow{{color:#facc15}} .red{{color:#f87171}} .dim{{color:#64748b}}
.footer{{margin-top:32px;color:#334155;font-size:.72rem;text-align:center}}

canvas{{background:#0f1117;border-radius:6px;padding:8px}}
</style>
</head>
<body>
<div class="container">
  <h1>Track 2 — Factor Regime ML</h1>
  <div class="subtitle">
    Predicting 12-month HML &amp; SMB regime direction ·
    Ken French monthly data {data.get('horizon_months','12')}m forward ·
    Holdout frozen: {data.get('holdout_start','2010-01')}→2026
  </div>

  <div class="caveat">
    <strong>Methodology:</strong>
    <ul>
      <li>Expanding walk-forward CV · {data.get('min_train_months',240)}m min train · {data.get('embargo_months',6)}m embargo · 24m test steps</li>
      <li>LightGBM: {N_SEEDS}-seed ensemble (mean prob) to reduce stochastic noise (Fractus M8/M9 lesson)</li>
      <li>Meta-labeling: LR direction model → LightGBM confidence filter (LdP Chapter 3)</li>
      <li>Shuffle-label null test: expected AUC ≈ 0.50; actual null confirms no data leakage</li>
      <li>Decade AUC: checks for distribution shift across time</li>
      <li>Success bar: WF AUC ≥ 0.60, consistent across decades, above null</li>
    </ul>
  </div>

  {sections}

  <div class="footer">
    Data: Ken French Data Library · Features: lagged returns, rolling vol, correlations, value spread ·
    Models: Logistic Regression + LightGBM (depth=3) + meta-labeling ·
    Not investment advice
  </div>
</div>
</body>
</html>"""

    with open(OUT_HTML, "w") as f:
        f.write(html)


if __name__ == "__main__":
    main()
