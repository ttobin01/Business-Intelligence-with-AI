"""
03_validate.py - Referential integrity, rule checks, reconciliations, IQR
outlier flags and the raw-vs-clean data quality scorecard (HW4 Part D).

    python hw04/scripts/03_validate.py

Runs every check on BOTH the raw tables (data/raw/) and the clean tables
(data/clean/) and saves:
    reports/data_quality_scorecard.csv  one row per table per stage (raw / clean):
                                        % completeness, % key uniqueness,
                                        % type validity, % rule pass, % referential match
    reports/validation_details.csv      every individual check behind the scorecard
                                        (13 relationships, rules, reconciliations, IQR flags)

check_referential_integrity() is the ONE reusable RI function (kept for Assignment 5);
01_profile.py and 02_clean.py import it from here.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wildcat_schema as ws  # noqa: E402
from wildcat_schema import blank, cat, norm_key, to_num  # noqa: E402


def check(condition, message):
    """Raise if a claimed result does not hold (still runs under python -O)."""
    if not bool(condition):
        raise AssertionError(message)


def check_referential_integrity(fact_df, fact_key, dim_df, dim_key):
    """Check that every value of fact_df[fact_key] exists in dim_df[dim_key].

    Works for any child/parent pair (fact -> dimension, or dimension ->
    dimension) and any column dtype. Keys are compared as text after
    norm_key(): spaces stripped, a trailing '.0' on whole numbers removed (so
    a float-formatted id 45.0 still matches 45 - that formatting problem is
    reported by the type-validity checks, not here). A blank key, a real
    NaN/None, or a null-like token ('NULL', 'N/A', ...) counts as a NULL key
    (unresolvable), never as an orphan.

    Returns a dict:
        rows                 total child rows
        null_key_rows        child rows with a blank key
        null_key_rate        null_key_rows / rows
        non_null_rows        rows - null_key_rows
        matched_rows         non-null rows whose key exists in the parent
        match_rate           matched_rows / non_null_rows (NaN if every key is null)
        orphan_row_count     non-null rows whose key is NOT in the parent
        orphan_rate          orphan_row_count / non_null_rows
        distinct_orphan_keys number of different orphan key values
        orphan_key_sample    up to 10 orphan key values (sorted)
        dim_key_duplicates   parent key values that appear more than once
                             (a non-unique parent key breaks every join)
        orphan_rows          DataFrame of the orphan child rows
    """
    child = norm_key(fact_df[fact_key])
    parent = norm_key(dim_df[dim_key])
    parent = parent[parent != ""]

    null_mask = child == ""
    orphan_mask = ~null_mask & ~child.isin(set(parent))

    rows = len(child)
    null_rows = int(null_mask.sum())
    non_null = rows - null_rows
    orphans = int(orphan_mask.sum())
    orphan_keys = sorted(child[orphan_mask].unique(), key=lambda k: (len(k), k))

    return {
        "rows": rows,
        "null_key_rows": null_rows,
        "null_key_rate": null_rows / rows if rows else 0.0,
        "non_null_rows": non_null,
        "matched_rows": non_null - orphans,
        "match_rate": (non_null - orphans) / non_null if non_null else float("nan"),
        "orphan_row_count": orphans,
        "orphan_rate": orphans / non_null if non_null else float("nan"),
        "distinct_orphan_keys": len(orphan_keys),
        "orphan_key_sample": orphan_keys[:10],
        "dim_key_duplicates": int(parent.duplicated().sum()),
        "orphan_rows": fact_df[orphan_mask],
    }


# ---------------------------------------------------------------------------
# 1. Referential integrity on all 13 relationships
# ---------------------------------------------------------------------------

def run_referential_integrity(tables, stage, details):
    rows = []
    for child, ckey, parent, pkey in ws.RELATIONSHIPS:
        r = check_referential_integrity(tables[child], ckey, tables[parent], pkey)
        rows.append({"stage": stage, "child": child, "fk": ckey, "parent": parent, "pk": pkey,
                     **{k: v for k, v in r.items() if k not in ("orphan_rows", "orphan_key_sample")},
                     "orphan_key_sample": " ".join(r["orphan_key_sample"])})
        details.append({
            "stage": stage, "check_type": "referential integrity", "table": child,
            "check": f"{child}.{ckey} -> {parent}.{pkey}", "evaluated": r["non_null_rows"],
            "failed": r["orphan_row_count"], "pass_pct": round(100 * r["match_rate"], 4),
            "detail": (f"null-key rate {r['null_key_rate']:.2%}; distinct orphan keys "
                       f"{r['distinct_orphan_keys']}; parent key duplicates {r['dim_key_duplicates']}"),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2. Rule-based checks (natural business bounds, code lists, sign rules)
# ---------------------------------------------------------------------------

def column_rule_results(df, table):
    """Column-level rules declared in the schema: allowed lists, patterns and ranges.

    Returns a list of (rule description, evaluated rows, failed rows). A value
    is evaluated only if it is non-blank and type-valid, so a failure here is a
    genuine out-of-bounds value (format problems are counted under type validity).
    """
    out = []
    for col, spec in ws.SCHEMA[table]["columns"].items():
        s = df[col].astype(str).str.strip()
        ok = ~blank(s) & ws.valid_type_mask(s, spec["type"])
        if "allowed" in spec:
            out.append((f"{col} in allowed list", int(ok.sum()), int((ok & ~s.isin(spec["allowed"])).sum())))
        if "pattern" in spec:
            out.append((f"{col} matches {spec['pattern']}", int(ok.sum()),
                        int((ok & ~s.str.fullmatch(spec["pattern"])).sum())))
        if ("min" in spec or "max" in spec) and spec["type"] in ("int", "float", "date"):
            v = ws.to_date(s) if spec["type"] == "date" else to_num(s)
            conv = (lambda x: pd.Timestamp(x)) if spec["type"] == "date" else (lambda x: x)
            bad = pd.Series(False, index=df.index)
            if "min" in spec:
                bad |= ok & (v < conv(spec["min"]))
            if "max" in spec:
                bad |= ok & (v > conv(spec["max"]))
            out.append((f"{col} within [{spec.get('min', '')}, {spec.get('max', '')}]",
                        int(ok.sum()), int(bad.sum())))
    return out


def run_rules(tables, stage, details):
    """All rule checks per table. Returns {table: (evaluations, passes)} for the scorecard.

    Scorecard '% rule pass' = passed evaluations / all evaluations over the
    column-level bounds plus the ERROR and WARN row/cross-table rules. INFO
    rules describe documented source limitations (e.g. dividend definition)
    and are reported in the details file but not scored.
    """
    totals = {t: [0, 0] for t in ws.TABLE_ORDER}

    def record(table, check, evaluated, failed, kind, scored=True):
        details.append({"stage": stage, "check_type": kind, "table": table, "check": check,
                        "evaluated": evaluated, "failed": failed,
                        "pass_pct": round(100 * (1 - failed / evaluated), 4) if evaluated else 100.0,
                        "detail": "" if scored else "INFO rule - reported, not scored"})
        if scored:
            totals[table][0] += evaluated
            totals[table][1] += evaluated - failed

    for table in ws.TABLE_ORDER:
        for rule, ev, failed in column_rule_results(tables[table], table):
            record(table, rule, ev, failed, "rule: column bound")
    # Denominator = the rows each rule applies to (e.g. Buy/Sell rows for the trading-day rule)
    for (table, rule, _dim, sev, func, applies) in ws.ROW_RULES:
        df = tables[table]
        bad = func(df).fillna(False).astype(bool)
        n = int(applies(df).fillna(False).sum()) if applies else len(df)
        record(table, f"[{sev}] {rule}", n, int(bad.sum()), "rule: single-table", sev != "INFO")
    for (table, rule, _dim, sev, func, applies) in ws.CROSS_RULES:
        bad = func(tables).fillna(False).astype(bool)
        n = int(applies(tables).fillna(False).sum()) if applies else len(tables[table])
        record(table, f"[{sev}] {rule}", n, int(bad.sum()), "rule: cross-table", sev != "INFO")
    return totals


# ---------------------------------------------------------------------------
# 3. Cross-table reconciliations (recomputed or second-source value vs stored)
# ---------------------------------------------------------------------------

def run_reconciliations(tables, stage, details):
    fees, snap, tx = tables["fact_fees"], tables["fact_portfolio_snapshot"], tables["fact_transactions"]
    out = []

    # R1  fact_fees.aum_basis vs fact_portfolio_snapshot.aum (same client, same month)
    key_s = norm_key(snap["client_id"]) + "|" + snap["snapshot_date"].str.strip()
    aum = pd.Series(to_num(snap["aum"]).values, index=key_s)
    aum = aum[~aum.index.duplicated()]
    key_f = norm_key(fees["client_id"]) + "|" + fees["fee_date"].str.strip()
    s_aum = key_f.map(aum)
    basis = to_num(fees["aum_basis"])
    matched = s_aum.notna()
    agree = matched & ((basis - s_aum).abs() <= 0.011)
    out.append(("R1 fact_fees.aum_basis = fact_portfolio_snapshot.aum (same client-month)", "fact_fees",
                int(matched.sum()), int((matched & ~agree).sum()),
                f"sum aum_basis ${basis[matched].sum():,.2f} vs sum snapshot aum ${s_aum[matched].sum():,.2f}; "
                f"{int((~matched).sum())} fee rows without a snapshot"))

    # R2  fact_fees.amount vs recomputed aum_basis x bps / 10,000 / 12
    calc = (basis * to_num(fees["bps_charged"]) / 10_000 / 12).round(2)
    amt = to_num(fees["amount"])
    ok = calc.notna() & amt.notna()
    out.append(("R2 fact_fees.amount = round(aum_basis x bps_charged / 120,000, 2)", "fact_fees",
                int(ok.sum()), int((ok & ((calc - amt).abs() > 0.011)).sum()),
                f"stored total ${amt[ok].sum():,.2f} vs recomputed total ${calc[ok].sum():,.2f}"))

    # R3  fact_transactions.amount vs recomputed |shares| x price (security rows)
    calc = (to_num(tx["shares"]).abs() * to_num(tx["price"])).round(2)
    amt = to_num(tx["amount"])
    ok = calc.notna() & amt.notna()
    out.append(("R3 fact_transactions.amount = round(|shares| x price, 2)", "fact_transactions",
                int(ok.sum()), int((ok & ((calc - amt).abs() > 0.011)).sum()),
                f"stored total ${amt[ok].sum():,.2f} vs recomputed total ${calc[ok].sum():,.2f}; "
                f"rows with negative shares: {int((to_num(tx['shares']) < 0).sum())}"))

    # R4  return_ytd vs benchmark_return_ytd + active_alpha_ytd
    r = to_num(snap["return_ytd"])
    rec = to_num(snap["benchmark_return_ytd"]) + to_num(snap["active_alpha_ytd"])
    ok = rec.notna()
    out.append(("R4 fact_portfolio_snapshot.return_ytd = benchmark_return_ytd + active_alpha_ytd",
                "fact_portfolio_snapshot", int(ok.sum()), int((ok & ~((r - rec).abs() <= 1e-5)).sum()),
                f"{int((ok & r.isna()).sum())} return values unparseable (counted as not reconciled)"))

    # R5  advisor on every fact = client's advisor in dim_client
    cli_adv = tables["dim_client"].assign(_k=norm_key(tables["dim_client"]["client_id"]),
                                          _a=norm_key(tables["dim_client"]["advisor_id"])) \
        .drop_duplicates("_k").set_index("_k")["_a"]
    for name in ("fact_transactions", "fact_fees", "fact_portfolio_snapshot"):
        f = tables[name]
        exp = norm_key(f["client_id"]).map(cli_adv)
        ok = exp.notna()
        out.append((f"R5 {name}.advisor_id = dim_client.advisor_id for the client", name,
                    int(ok.sum()), int((ok & (norm_key(f["advisor_id"]) != exp)).sum()),
                    f"{int((~ok).sum())} rows whose client is not in dim_client"))

    for check, table, ev, failed, detail in out:
        details.append({"stage": stage, "check_type": "reconciliation", "table": table, "check": check,
                        "evaluated": ev, "failed": failed,
                        "pass_pct": round(100 * (1 - failed / ev), 4) if ev else 100.0, "detail": detail})
    return out


# ---------------------------------------------------------------------------
# 4. IQR outlier flags (numeric columns with no natural upper bound)
# ---------------------------------------------------------------------------

def iqr_flags(series, k=1.5):
    """Flag values outside [Q1 - k*IQR, Q3 + k*IQR] (both tails).

    Returns (flags, low_fence, high_fence). NaN and +/-inf are never flagged and
    never move the fences. An empty / all-NaN column, or one whose IQR is 0
    (more than half the values identical), returns no flags and NaN fences
    rather than raising or flagging every other value.
    """
    x = pd.to_numeric(pd.Series(series), errors="coerce")
    x = x.where(np.isfinite(x))
    valid = x.dropna()
    no_flags = pd.Series(False, index=x.index)
    if valid.empty:
        return no_flags, np.nan, np.nan
    q1, q3 = valid.quantile(0.25), valid.quantile(0.75)
    if q3 == q1:
        return no_flags, np.nan, np.nan
    lo, hi = q1 - k * (q3 - q1), q3 + k * (q3 - q1)
    return ((x < lo) | (x > hi)).fillna(False), lo, hi


IQR_COLUMNS = [
    ("fact_portfolio_snapshot", "aum"),
    ("fact_fees", "amount"),
    ("fact_transactions", "amount"),
    ("dim_client", "initial_aum"),
]


def run_iqr(tables, stage, details):
    out = []
    for table, col in IQR_COLUMNS:
        v = to_num(tables[table][col])
        flags, lo, hi = iqr_flags(v)
        n = int(v.notna().sum())
        n_low, n_high = int((v < lo).sum()), int((v > hi).sum())
        out.append((table, col, n, int(flags.sum()), lo, hi, n_low, n_high))
        details.append({"stage": stage, "check_type": "IQR outlier (informational)", "table": table,
                        "check": f"{col} outside Q1-1.5*IQR .. Q3+1.5*IQR", "evaluated": n,
                        "failed": int(flags.sum()),
                        "pass_pct": round(100 * (1 - flags.sum() / n), 4) if n else 100.0,
                        "detail": f"fences [{lo:,.2f}, {hi:,.2f}]; {n_low} low / {n_high} high; flagged != wrong"})
    return out


# ---------------------------------------------------------------------------
# 5. Headline business totals (so the report quotes script output, not estimates)
# ---------------------------------------------------------------------------

def run_headline_totals(tables, stage, details):
    tx, fees, snap = tables["fact_transactions"], tables["fact_fees"], tables["fact_portfolio_snapshot"]
    amt = to_num(tx["amount"])
    dep = amt[cat(tx["txn_type"]) == "Deposit"].sum()
    wd = amt[cat(tx["txn_type"]) == "Withdrawal"].sum()
    last = snap["snapshot_date"].str.strip().max()
    dec = snap[snap["snapshot_date"].str.strip() == last]
    aum, ret = to_num(dec["aum"]), to_num(dec["return_ytd"])
    ok = aum.notna() & ret.notna()
    fee_amt, basis = to_num(fees["amount"]), to_num(fees["aum_basis"])
    totals = [
        ("clients in dim_client", len(tables["dim_client"])),
        ("total fee revenue ($)", round(fee_amt.sum(), 2)),
        ("AUM-weighted fee rate (bps) = sum(fees) x 12 x 10,000 / sum(aum_basis)",
         round(fee_amt.sum() * 12 * 10_000 / basis.sum(), 2)),
        ("simple average bps_charged", round(to_num(fees["bps_charged"]).mean(), 2)),
        ("net cash flow ($) = deposits - withdrawals", round(dep - wd, 2)),
        (f"ending AUM ($) at {last}", round(aum.sum(), 2)),
        (f"clients with a snapshot at {last}", len(dec)),
        (f"simple average return_ytd at {last} (%)", round(100 * ret[ok].mean(), 2)),
        (f"AUM-weighted return_ytd at {last} (%)", round(100 * (ret[ok] * aum[ok]).sum() / aum[ok].sum(), 2)),
    ]
    if "extreme_return_flag" in dec.columns:
        keep = ok & (dec["extreme_return_flag"] == "0")
        totals.append((f"simple average return_ytd at {last} excluding extreme_return_flag rows (%)",
                       round(100 * ret[keep].mean(), 2)))
    for name, value in totals:
        details.append({"stage": stage, "check_type": "headline total", "table": "", "check": name,
                        "evaluated": "", "failed": "", "pass_pct": "", "detail": value})
    return totals


# ---------------------------------------------------------------------------
# 6. Scorecard
# ---------------------------------------------------------------------------

def completeness_and_validity(df, table):
    req_cells = filled = nonblank = valid = 0
    for col, spec in ws.SCHEMA[table]["columns"].items():
        s = df[col]
        nb = ~blank(s)
        req = ws.required_mask(df, spec)
        req_cells += int(req.sum())
        filled += int((req & nb).sum())
        nonblank += int(nb.sum())
        valid += int((nb & ws.valid_type_mask(s, spec["type"])).sum())
    return 100 * filled / req_cells, 100 * valid / nonblank


def key_uniqueness(df, table):
    """% of rows that are not an extra copy: neither a repeated primary key nor a
    near-duplicate of another row on the table's declared natural key / grain."""
    pk = norm_key(df[ws.SCHEMA[table]["pk"]])
    extra = (pk != "") & pk.duplicated(keep="first")
    extra |= df.duplicated(subset=ws.SCHEMA[table]["near_dup_keys"], keep="first")
    return 100 * (1 - extra.mean())


def referential_match(ri, table):
    sub = ri[ri["child"] == table]
    if sub.empty or sub["non_null_rows"].sum() == 0:
        return np.nan          # table has no foreign keys (or no non-null ones)
    return 100 * sub["matched_rows"].sum() / sub["non_null_rows"].sum()


def validate_stage(folder, stage, details):
    tables = ws.load_tables(folder)
    print(f"\n{'=' * 78}\nSTAGE: {stage.upper()}  ({Path(folder).relative_to(ws.HW_DIR)})\n{'=' * 78}")
    ri = run_referential_integrity(tables, stage, details)
    print("\nReferential integrity (13 relationships):")
    for _, r in ri.iterrows():
        print(f"  {r['child'] + '.' + r['fk']:38s} -> {r['parent'] + '.' + r['pk']:28s} "
              f"match {r['match_rate']:8.4%} | orphans {r['orphan_row_count']:4d} "
              f"({r['distinct_orphan_keys']} keys) | null-key {r['null_key_rate']:6.2%}")

    rule_totals = run_rules(tables, stage, details)

    recs = run_reconciliations(tables, stage, details)
    print("\nCross-table reconciliations:")
    for check, table, ev, failed, detail in recs:
        print(f"  {check}: {ev - failed:,}/{ev:,} agree ({failed:,} differ) | {detail}")

    iqr = run_iqr(tables, stage, details)
    print("\nIQR outlier flags (1.5 x IQR, both tails):")
    for table, col, n, flagged, lo, hi, n_low, n_high in iqr:
        print(f"  {table}.{col}: {flagged:,} of {n:,} flagged ({(flagged / n if n else 0):.1%}); "
              f"fences [{lo:,.2f}, {hi:,.2f}]; low {n_low}, high {n_high}")

    print("\nHeadline business totals:")
    for name, value in run_headline_totals(tables, stage, details):
        print(f"  {name}: {value:,}")

    score = []
    for name in ws.TABLE_ORDER:
        df = tables[name]
        comp, validity = completeness_and_validity(df, name)
        ev, passed = rule_totals[name]
        score.append({
            "table": name, "stage": stage, "rows": len(df),
            "pct_completeness": round(comp, 3),
            "pct_key_uniqueness": round(key_uniqueness(df, name), 3),
            "pct_type_validity": round(validity, 3),
            "pct_rule_pass": round(100 * passed / ev, 3) if ev else np.nan,
            "pct_referential_match": round(referential_match(ri, name), 3),
        })
    return pd.DataFrame(score)


def main():
    details = []
    raw = validate_stage(ws.RAW_DIR, "raw", details)
    clean = validate_stage(ws.CLEAN_DIR, "clean", details)

    score = pd.concat([raw, clean]).sort_values(["table", "stage"], ascending=[True, False],
                                                key=lambda s: s.map({"raw": 1, "clean": 0}) if s.name == "stage" else s)
    score = score.reset_index(drop=True)
    ws.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    score.to_csv(ws.REPORTS_DIR / "data_quality_scorecard.csv", index=False, lineterminator="\n")
    pd.DataFrame(details).to_csv(ws.REPORTS_DIR / "validation_details.csv", index=False, lineterminator="\n")

    pd.set_option("display.width", 200)
    print(f"\n{'=' * 78}\nDATA QUALITY SCORECARD (raw vs clean)\n{'=' * 78}")
    print(score.to_string(index=False))
    print("\npct_referential_match is blank for tables with no foreign keys (dim_advisor, dim_benchmark, dim_date).")
    print("IQR note: 'flagged' does not mean 'wrong' - wealth is highly skewed, so UHNW balances and large trades "
          "fall outside the fences legitimately; a flag only marks a value for a second look.")

    # The clean stage must be at least as good as raw on every measure, and the
    # repaired dimensions must be perfect.
    for name in ws.TABLE_ORDER:
        r = raw[raw["table"] == name].iloc[0]
        c = clean[clean["table"] == name].iloc[0]
        for m in ("pct_completeness", "pct_key_uniqueness", "pct_type_validity", "pct_rule_pass",
                  "pct_referential_match"):
            if not (np.isnan(r[m]) and np.isnan(c[m])):
                check(c[m] >= r[m] - 1e-9, f"{name}: clean {m} is worse than raw")
        check(c["pct_key_uniqueness"] == 100 and c["pct_type_validity"] == 100,
              f"{name}: clean key uniqueness / type validity below 100%")
        check(np.isnan(c["pct_referential_match"]) or c["pct_referential_match"] == 100,
              f"{name}: clean referential match below 100%")
    print("\nChecked: clean >= raw on every measure; clean key uniqueness, type validity and "
          "referential match are 100%.")
    print(f"Saved {(ws.REPORTS_DIR / 'data_quality_scorecard.csv').relative_to(ws.HW_DIR)} and "
          f"{(ws.REPORTS_DIR / 'validation_details.csv').relative_to(ws.HW_DIR)}")


if __name__ == "__main__":
    main()
