"""
02_clean.py - Cleaning program for the Wildcat Capital tables (HW4 Part C).

    python hw04/scripts/02_clean.py

Reads the eight raw files in data/raw/ (never modified) and writes:
    data/clean/<same 8 file names>       same columns (+ clearly named 0/1 flag columns)
    data/audit/cleaning_log.csv          table, issue, action, rows affected, note
    data/audit/value_changes.csv         table, key column, key, column, old value, new value
    data/audit/quarantine_*.csv          one file per quarantined set of rows

Rules followed (see decision_log.md for the reasoning behind every step):
  * One transformation at a time. Each step prints rows affected and a
    before/after check, then asserts the after-state with check(), which
    raises AssertionError - the script stops if a fix did not do what it
    claims. (check() is used instead of the bare `assert` statement so the
    safety checks still run under `python -O`.)
  * Repairs are reconciled against other columns/tables, never guessed.
  * Nothing is deleted silently: removed rows go to a quarantine file, and
    raw = clean + quarantined is proven row by row (by key) for every table.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wildcat_schema as ws  # noqa: E402
from wildcat_schema import blank, cat, norm_key, to_date, to_num  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "validate_mod", Path(__file__).resolve().parent / "03_validate.py")
_validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_validate)
check_referential_integrity = _validate.check_referential_integrity

# Explicit, complete map for the state names found in the audit (decision log #2)
STATE_NAME_TO_CODE = {
    "Pennsylvania": "PA", "Florida": "FL", "New York": "NY", "New Jersey": "NJ",
    "California": "CA", "Illinois": "IL", "Texas": "TX",
}

# Counts documented in decision_log.md. If the raw data ever changes, the
# script stops instead of silently applying a decision made for other data.
EXPECTED = {
    "duplicate_clients": 25, "state_names": 77, "orphan_transactions": 200,
    "security_id_format": 197_044, "negative_shares": 835, "percent_returns": 300,
    "flag_non_trading_day": 40_630, "flag_after_last_snapshot": 2_410, "clients_after_last_snapshot": 131,
    "flag_snapshot_aum_floor": 420, "flag_fee_aum_floor": 386, "flag_extreme_return": 3_875,
    "risk_profile_blank": 75,
}


def check(condition, message):
    """Stop the script if a claimed after-state does not hold (works under python -O)."""
    if not bool(condition):
        raise AssertionError(message)


def check_count(name, actual):
    check(actual == EXPECTED[name], f"{name}: expected {EXPECTED[name]:,} per the decision log, found {actual:,}")


class AuditTrail:
    """Collects the cleaning log, value-level changes and quarantined rows."""

    def __init__(self):
        self.log = []
        self.changes = []
        self.quarantine = {}          # file stem -> (table, DataFrame)

    def step(self, table, issue, action, rows, note):
        self.log.append({"step": len(self.log) + 1, "table": table, "issue": issue,
                         "action": action, "rows_affected": int(rows), "note": note})

    def value_changes(self, table, df_before, df_after, mask, column):
        key = ws.SCHEMA[table]["pk"]
        self.changes.append(pd.DataFrame({
            "table": table, "key_column": key, "key": df_before.loc[mask, key].values,
            "column": column, "old_value": df_before.loc[mask, column].values,
            "new_value": df_after.loc[mask, column].values,
        }))

    def quarantine_rows(self, name, table, rows, reason):
        q = rows.copy()
        q.insert(0, "quarantine_reason", reason)
        q.insert(0, "source_table", table)
        self.quarantine[name] = (table, q)

    def quarantined(self, table):
        frames = [q for t, q in self.quarantine.values() if t == table]
        return pd.concat(frames) if frames else pd.DataFrame()


def banner(n, title):
    print(f"\n{'=' * 78}\nSTEP {n}: {title}\n{'=' * 78}")


# ---------------------------------------------------------------------------
# Step 1 - dim_client: quarantine duplicate client records (decision log #1)
# ---------------------------------------------------------------------------

def step_dedupe_clients(t, audit):
    banner(1, "dim_client - quarantine duplicate client records entered under a new id")
    cli = t["dim_client"]
    keys = ws.SCHEMA["dim_client"]["near_dup_keys"]
    before_rows = len(cli)

    cid = to_num(cli["client_id"]).astype(int)
    group_min = cli.assign(_id=cid).groupby(keys)["_id"].transform("min")
    is_copy = cid != group_min
    copies = cli[is_copy].copy()
    copies["duplicate_of_client_id"] = group_min[is_copy].astype(str).values
    print(f"Before: {before_rows:,} rows | near-duplicate copies found: {len(copies)}")
    check(is_copy.any(), "no duplicates found - nothing to quarantine")

    # Evidence that these are the SAME person, not just similar profiles:
    #  (a) the only difference is the last name, and it is a one-letter
    #      truncation/extension of the original (Taylor -> Taylo, Pace -> Pacen)
    originals = cli.set_index("client_id")
    for _, r in copies.iterrows():
        o = originals.loc[r["duplicate_of_client_id"]]
        a, b = o["last_name"], r["last_name"]
        differ = [c for c in cli.columns if c not in ("client_id", "last_name") and o[c] != r[c]]
        check(not differ, f"client {r['client_id']} differs from its original in {differ}")
        check(abs(len(a) - len(b)) == 1 and (a.startswith(b) or b.startswith(a)),
              f"client {r['client_id']}: '{b}' is not a one-letter truncation/extension of '{a}'")
    #  (b) the copies carry no facts, the originals carry all of them
    for fact in ("fact_transactions", "fact_fees", "fact_portfolio_snapshot"):
        used = set(norm_key(t[fact]["client_id"]))
        check(not set(copies["client_id"]) & used, f"a duplicate client id has rows in {fact}")
        check(set(copies["duplicate_of_client_id"]) <= used, f"an original has no rows in {fact}")
    print("Verified: each copy equals its original except a one-letter last-name change; "
          "copies have 0 fact rows, originals have rows in all 3 fact tables")
    print("Example pairs:", "; ".join(
        f"{r.duplicate_of_client_id} {originals.loc[r.duplicate_of_client_id, 'last_name']} <- "
        f"{r.client_id} {r.last_name}" for r in copies.head(3).itertuples()))

    audit.quarantine_rows("quarantine_dim_client_duplicates", "dim_client", copies,
                          "near-duplicate of an existing client (same attributes, no fact rows)")
    t["dim_client"] = cli[~is_copy].reset_index(drop=True)
    after = t["dim_client"]

    print(f"After:  {len(after):,} rows | quarantined: {len(copies)}")
    check_count("duplicate_clients", len(copies))
    check(len(after) + len(copies) == before_rows, "row count does not add up")
    check(not after.duplicated(keys).any(), "near-duplicates remain")
    check(norm_key(after["client_id"]).is_unique, "client_id not unique")
    check(after["client_tier"].value_counts().to_dict() == {"Retail": 1510, "HNW": 737, "UHNW": 253},
          "tier counts after de-duplication do not match the decision log")
    audit.step("dim_client", f"{len(copies)} client records duplicated under ids "
               f"{copies['client_id'].astype(int).min()}-{copies['client_id'].astype(int).max()} (last name truncated)",
               "quarantine", len(copies),
               "kept the lower id that holds all fact rows; verified identical attributes, one-letter last-name "
               "change and 0 fact rows on every copy; tiers now Retail 1,510 / HNW 737 / UHNW 253 (decision log #1)")


# ---------------------------------------------------------------------------
# Step 2 - dim_client.state: full names -> USPS codes (decision log #2)
# ---------------------------------------------------------------------------

def step_standardize_state(t, audit):
    banner(2, "dim_client.state - standardize full state names to 2-letter codes")
    cli = t["dim_client"]
    before = cli.copy()
    bad = ~cat(cli["state"]).isin(ws.US_STATE_CODES)
    print(f"Before: {bad.sum()} non-code values: {cli.loc[bad, 'state'].value_counts().to_dict()}")
    unmapped = set(cat(cli.loc[bad, "state"])) - set(STATE_NAME_TO_CODE)
    check(not unmapped, f"state values with no mapping: {unmapped}")   # fail loudly, never guess

    mapped = cat(cli.loc[bad, "state"]).map(STATE_NAME_TO_CODE)
    check(mapped.notna().all(), "a state name mapped to nothing")
    cli.loc[bad, "state"] = mapped
    print(f"After:  {(~cli['state'].isin(ws.US_STATE_CODES)).sum()} non-code values | "
          f"rows changed: {bad.sum()} | PA before {(before['state'] == 'PA').sum()} + "
          f"'Pennsylvania' {(before['state'] == 'Pennsylvania').sum()} -> PA after {(cli['state'] == 'PA').sum()}")

    check_count("state_names", int(bad.sum()))
    check(cli["state"].isin(ws.US_STATE_CODES).all(), "a state is still not a valid code")
    check(len(cli) == len(before), "row count changed")
    for name, code in STATE_NAME_TO_CODE.items():
        check((cli["state"] == code).sum() == ((before["state"] == code) | (before["state"] == name)).sum(),
              f"{code} count does not equal old {code} + '{name}'")
    check((cli.loc[~bad, "state"] == before.loc[~bad, "state"]).all(), "an unrelated state changed")
    audit.value_changes("dim_client", before, cli, bad, "state")
    audit.step("dim_client", f"state stored as full names ({bad.sum()} rows after de-duplication; "
               "78 in raw, 1 was on a quarantined duplicate)", "standardize", bad.sum(),
               "explicit name->code map; checks no unmapped value and per-state counts add up (decision log #2)")


# ---------------------------------------------------------------------------
# Step 3 - fact_transactions: quarantine orphan client_ids (decision log #4)
# ---------------------------------------------------------------------------

def step_quarantine_orphans(t, audit):
    banner(3, "fact_transactions.client_id - quarantine transactions for clients not in dim_client")
    tx = t["fact_transactions"]
    before_rows = len(tx)
    ri = check_referential_integrity(tx, "client_id", t["dim_client"], "client_id")
    orphans = ri["orphan_rows"]
    ids = to_num(orphans["txn_id"])
    print(f"Before: {before_rows:,} rows | orphan rows {ri['orphan_row_count']} | distinct orphan "
          f"client_ids {ri['distinct_orphan_keys']} | match rate {ri['match_rate']:.4%}")
    print(f"        orphan txn_id range {ids.min():.0f}-{ids.max():.0f}, amount ${to_num(orphans['amount']).sum():,.2f}")
    check(len(orphans) > 0, "no orphans found")
    # These ids exist nowhere else either, so they cannot be re-attributed
    for fact in ("fact_fees", "fact_portfolio_snapshot"):
        check(not set(norm_key(orphans["client_id"])) & set(norm_key(t[fact]["client_id"])),
              f"orphan id found in {fact} - investigate before quarantining")

    audit.quarantine_rows("quarantine_fact_transactions_orphans", "fact_transactions", orphans,
                          "client_id not found in dim_client (or any other table)")
    t["fact_transactions"] = tx.drop(index=orphans.index).reset_index(drop=True)
    after = check_referential_integrity(t["fact_transactions"], "client_id", t["dim_client"], "client_id")
    print(f"After:  {len(t['fact_transactions']):,} rows | orphan rows {after['orphan_row_count']} | "
          f"match rate {after['match_rate']:.2%}")

    check_count("orphan_transactions", len(orphans))
    check(len(t["fact_transactions"]) + len(orphans) == before_rows, "row count does not add up")
    check(after["orphan_row_count"] == 0 and after["null_key_rows"] == 0, "orphans or null keys remain")
    audit.step("fact_transactions", f"{len(orphans)} transactions reference client_ids "
               f"{to_num(orphans['client_id']).min():.0f}-{to_num(orphans['client_id']).max():.0f} that do not exist",
               "quarantine", len(orphans),
               f"txn_id {ids.min():.0f}-{ids.max():.0f}; ${to_num(orphans['amount']).sum():,.2f}; "
               "ids absent from all tables (decision log #4)")


# ---------------------------------------------------------------------------
# Step 4 - fact_transactions.security_id: '45.0' -> '45' (decision log #3)
# ---------------------------------------------------------------------------

def step_security_id_format(t, audit):
    banner(4, "fact_transactions.security_id - convert decimal-formatted ids to integers")
    tx = t["fact_transactions"]
    before = tx.copy()
    s = tx["security_id"]
    nb = ~blank(s)
    fmt = nb & ~s.str.fullmatch(r"[0-9]+")
    print(f"Before: {fmt.sum():,} of {nb.sum():,} non-blank ids not in integer format "
          f"(e.g. {s[fmt].head(3).tolist()})")
    check(fmt.any(), "nothing to convert")
    check(s[fmt].str.fullmatch(r"[0-9]+\.0+").all(), "an id has a non-zero fractional part - not safe")

    tx.loc[fmt, "security_id"] = s[fmt].str.replace(r"\.0+$", "", regex=True)
    after = tx["security_id"]
    still_bad = (nb & ~after.str.fullmatch(r"[0-9]+")).sum()
    print(f"After:  {still_bad} not in integer format | rows changed: {fmt.sum():,}")

    check_count("security_id_format", int(fmt.sum()))
    check(still_bad == 0, "ids still not in integer format")
    check((blank(after) == ~nb).all(), "blank pattern changed")
    check((to_num(after[nb]) == to_num(before.loc[nb, "security_id"])).all(), "a numeric id value changed")
    # Exact text join, as a BI tool would do it (no normalisation)
    exact = after[nb].isin(set(t["dim_security"]["security_id"]))
    print(f"Check:  converted ids that match dim_security.security_id exactly (no normalisation): "
          f"{exact.sum():,} of {nb.sum():,}")
    check(exact.all(), "a converted id does not exist in dim_security")
    audit.value_changes("fact_transactions", before, tx, fmt, "security_id")
    audit.step("fact_transactions", "security_id stored as decimals (45.0)", "convert", fmt.sum(),
               "integer text; numeric value unchanged; 100% of ids match dim_security exactly (decision log #3)")


# ---------------------------------------------------------------------------
# Step 5 - fact_transactions.shares: negative Buy shares -> absolute value (#5)
# ---------------------------------------------------------------------------

def step_fix_share_sign(t, audit):
    banner(5, "fact_transactions.shares - correct the sign of negative Buy shares (reconciled to amount)")
    tx = t["fact_transactions"]
    before = tx.copy()
    sh, pr, amt = to_num(tx["shares"]), to_num(tx["price"]), to_num(tx["amount"])
    neg = sh < 0
    print(f"Before: {neg.sum()} negative share values; by type {tx.loc[neg, 'txn_type'].value_counts().to_dict()}")
    check(neg.any(), "no negative shares found")

    # Reconcile BEFORE changing: amount must already equal |shares| x price on these rows
    recon = ((sh.abs() * pr).round(2) - amt).abs()
    check((cat(tx.loc[neg, "txn_type"]) == "Buy").all(), "negative shares on a non-Buy row")
    check((recon[neg] <= 0.011).all(), "amount does not confirm the magnitude - not safe to flip")
    print(f"Reconcile: amount = round(|shares| x price, 2) on {(recon[neg] <= 0.011).sum()}/{neg.sum()} "
          f"rows (max diff ${recon[neg].max():.2f}) -> only the sign is wrong")

    tx.loc[neg, "shares"] = tx.loc[neg, "shares"].str.strip().str.lstrip("-")
    sh_after = to_num(tx["shares"])
    print(f"After:  {(sh_after < 0).sum()} negative share values | rows changed: {neg.sum()}")

    check_count("negative_shares", int(neg.sum()))
    check((sh_after < 0).sum() == 0, "negative shares remain")
    check(np.allclose(sh_after[neg], sh[neg].abs()), "a magnitude changed")
    check((tx.loc[~neg, "shares"] == before.loc[~neg, "shares"]).all(), "an unrelated value changed")
    sec = sh_after.notna()
    check((((sh_after.abs() * pr).round(2) - amt).abs()[sec] <= 0.011).all(), "reconciliation broke")
    audit.value_changes("fact_transactions", before, tx, neg, "shares")
    audit.step("fact_transactions", f"{neg.sum()} Buy rows with negative shares (836 in raw; 1 was in "
               "the quarantined orphan rows)", "convert (absolute value)", neg.sum(),
               "amount = |shares| x price confirmed on every row before and after (decision log #5)")


# ---------------------------------------------------------------------------
# Step 6 - fact_portfolio_snapshot.return_ytd: percent strings (decision log #6)
# ---------------------------------------------------------------------------

def _fmt6(x):
    """Format a decimal to at most 6 places, like the surrounding values (0.0928 not 0.092800)."""
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def step_fix_return_ytd(t, audit):
    banner(6, "fact_portfolio_snapshot.return_ytd - replace percent strings by benchmark + alpha")
    sn = t["fact_portfolio_snapshot"]
    before = sn.copy()
    pct = sn["return_ytd"].str.contains("%", regex=False)
    print(f"Before: {pct.sum()} percent strings (e.g. {sn.loc[pct, 'return_ytd'].head(3).tolist()}); "
          f"{(~ws.valid_type_mask(sn['return_ytd'], 'float')).sum()} values fail to parse as decimal")
    check(pct.any(), "no percent strings found")

    recomputed = to_num(sn["benchmark_return_ytd"]) + to_num(sn["active_alpha_ytd"])
    from_pct = to_num(sn.loc[pct, "return_ytd"].str.strip().str.rstrip("%")) / 100
    gap = (recomputed[pct] - from_pct).abs()
    print(f"Reconcile: benchmark + alpha vs percent/100 -> max gap {gap.max():.6f} "
          f"(a 2-decimal percent is only accurate to 0.00005)")
    check(recomputed[pct].notna().all() and from_pct.notna().all(), "an input to the recompute is missing")
    check((gap <= 0.00005 + 1e-9).all(), "recomputed return disagrees with the stored percent")

    sn.loc[pct, "return_ytd"] = recomputed[pct].map(_fmt6)
    after = sn["return_ytd"]
    print(f"After:  {after.str.contains('%', regex=False).sum()} percent strings | "
          f"{(~ws.valid_type_mask(after, 'float')).sum()} values fail to parse | rows changed: {pct.sum()}")

    check_count("percent_returns", int(pct.sum()))
    check(ws.valid_type_mask(after, "float").all(), "a return still does not parse")
    r = to_num(after)
    check(((r - recomputed).abs()[pct] <= 1e-6).all(), "stored value differs from the recompute")
    check(((r - to_num(sn["benchmark_return_ytd"]) - to_num(sn["active_alpha_ytd"])).abs() <= 1e-5).all(),
          "alpha identity broken")
    check((r >= -1).all(), "a return below -100%")
    check((after[~pct] == before.loc[~pct, "return_ytd"]).all(), "an unrelated value changed")
    audit.value_changes("fact_portfolio_snapshot", before, sn, pct, "return_ytd")
    audit.step("fact_portfolio_snapshot", f"{pct.sum()} return_ytd values stored as percent strings",
               "convert (recompute = benchmark_return_ytd + active_alpha_ytd)", pct.sum(),
               f"agrees with percent/100 within {gap.max():.6f} on every row; alpha identity holds on all rows "
               "(decision log #6)")


# ---------------------------------------------------------------------------
# Step 7 - flag columns for suspicious values that cannot be corrected
# ---------------------------------------------------------------------------

def _add_flag(t, audit, n, table, col, mask, expected, issue, note):
    df = t[table]
    check(col not in df.columns, f"{col} already exists")
    before = df.copy()
    df[col] = mask.astype(int).astype(str).values
    print(f"[{n}] {table}.{col}: {int(mask.sum()):,} rows flagged of {len(df):,}")
    check_count(expected, int(mask.sum()))
    check(set(df[col]) <= {"0", "1"} and (df[col] == "1").sum() == mask.sum(), "flag values wrong")
    check(list(df.columns) == list(before.columns) + [col], "columns other than the flag changed")
    check(df[list(before.columns)].equals(before), "a value changed while adding a flag")
    audit.step(table, issue, f"flag ({col})", mask.sum(), note)


def step_flags(t, audit):
    banner(7, "Add 0/1 flag columns for values that are suspicious but cannot be corrected")
    tx, sn, fe, dd = t["fact_transactions"], t["fact_portfolio_snapshot"], t["fact_fees"], t["dim_date"]

    calendar = dd.drop_duplicates("date").set_index("date")["is_trading_day"]
    trading = tx["txn_date"].map(calendar)
    check(trading.notna().all(), "a txn_date is missing from dim_date")
    m = cat(tx["txn_type"]).isin(["Buy", "Sell"]) & (trading == "0")
    # independent cross-check: the same answer from the weekday of the date itself
    check((m == (cat(tx["txn_type"]).isin(["Buy", "Sell"]) & (to_date(tx["txn_date"]).dt.dayofweek >= 5))).all(),
          "dim_date trading flag disagrees with the weekday")
    _add_flag(t, audit, "7a", "fact_transactions", "trade_on_non_trading_day_flag", m, "flag_non_trading_day",
              "Buy/Sell dated on a non-trading day (weekend) per dim_date",
              "date kept; true trade date unknown (decision log #8)")

    last = to_date(sn["snapshot_date"]).groupby(sn["client_id"]).max()
    last_month = tx["client_id"].map(last)
    check(last_month.notna().all(), "a client has transactions but no snapshots")
    txn_month = to_date(tx["txn_date"]).dt.to_period("M").dt.to_timestamp()
    m = txn_month > last_month
    status = tx.loc[m, "client_id"].map(t["dim_client"].set_index("client_id")["is_active"])
    check((status == "False").all(), "an ACTIVE client has activity after its last snapshot")
    check_count("clients_after_last_snapshot", tx.loc[m, "client_id"].nunique())
    _add_flag(t, audit, "7b", "fact_transactions", "txn_after_last_snapshot_flag", m, "flag_after_last_snapshot",
              "transaction dated after the client's last monthly snapshot (inactive clients only)",
              f"{tx.loc[m, 'client_id'].nunique()} inactive clients; rows kept (decision log #9)")

    m = to_num(sn["aum"]) == ws.AUM_FLOOR_VALUE
    _add_flag(t, audit, "7c", "fact_portfolio_snapshot", "aum_floor_flag", m, "flag_snapshot_aum_floor",
              "aum exactly $1,000.00 placeholder floor", "value kept; true balance unknown (decision log #10)")
    m = to_num(fe["aum_basis"]) == ws.AUM_FLOOR_VALUE
    _add_flag(t, audit, "7d", "fact_fees", "aum_floor_flag", m, "flag_fee_aum_floor",
              "aum_basis exactly $1,000.00 placeholder floor", "consistent with the snapshot flag (decision log #10)")

    m = to_num(sn["active_alpha_ytd"]).abs() > ws.EXTREME_ALPHA_THRESHOLD
    _add_flag(t, audit, "7e", "fact_portfolio_snapshot", "extreme_return_flag", m, "flag_extreme_return",
              "|active_alpha_ytd| > 0.50: return implausibly far from benchmark",
              "values kept; use AUM-weighted returns or exclude flagged rows (decision log #11)")

    # Cross-table consistency of the two floor flags: same client-month, same flag
    key_s = sn["client_id"] + "|" + sn["snapshot_date"]
    key_f = fe["client_id"] + "|" + fe["fee_date"]
    snap_flag = key_f.map(pd.Series(sn["aum_floor_flag"].values, index=key_s))
    check((snap_flag == fe["aum_floor_flag"]).all(), "fee and snapshot floor flags disagree")
    print("Check:  fee aum_floor_flag equals the snapshot flag for the same client-month on every fee row")


# ---------------------------------------------------------------------------
# Documented "leave as is" decisions (logged so the trail is complete)
# ---------------------------------------------------------------------------

def log_left_as_is(t, audit):
    banner(8, "Record issues deliberately left as is (no values changed)")
    cli, tx, sec, sn = t["dim_client"], t["fact_transactions"], t["dim_security"], t["fact_portfolio_snapshot"]
    rule = ws.rule_function

    n = int(blank(cli["risk_profile"]).sum())
    check_count("risk_profile_blank", n)
    audit.step("dim_client", "risk_profile blank", "leave as is", n,
               "MCAR-looking; no mode fill (would invent a suitability rating) - decision log #7")

    cash = cat(tx["txn_type"]).isin(ws.TXN_TYPES_CASH_ONLY)
    check((blank(tx.loc[cash, "security_id"]) & blank(tx.loc[cash, "shares"])
           & blank(tx.loc[cash, "price"])).all(), "a cash row carries security fields")
    entries = [
        ("dim_security", "sector blank on ETFs / expense_ratio_bps blank on stocks (structural nulls)",
         int(blank(sec["sector"]).sum() + blank(sec["expense_ratio_bps"]).sum()), "decision log #12"),
        ("dim_advisor", "certifications = 'None' text is a real category (no certification)",
         int((t["dim_advisor"]["certifications"] == "None").sum()), "read with keep_default_na=False - #13"),
        ("fact_transactions", "security_id/shares/price blank on Deposit/Withdrawal/Advisory Fee rows "
         "(structural nulls)", int(cash.sum()), "decision log #14"),
        ("fact_portfolio_snapshot", "tiny returns written in scientific notation (valid numbers)",
         int((sn["return_ytd"].str.contains("e", case=False) | sn["active_alpha_ytd"].str.contains("e", case=False)).sum()),
         "decision log #15"),
        ("dim_client", "zip_code / account type '529' are codes that must stay text",
         int(cli["zip_code"].str.startswith("0").sum()), "rows with a leading-zero ZIP - decision log #16"),
        ("dim_client", "zip_code first digit inconsistent with state",
         int(rule("zip_code first digit is consistent with state (USPS area)")(cli).sum()),
         "cannot tell which field is wrong - decision log #17"),
        ("fact_transactions", "Dividend amount equals the full position value (shares x price)",
         int(rule("Dividend amount is not the full position value (shares x price)")(tx).sum()),
         "source definition issue; true dividend per share unknown - decision log #18"),
        ("fact_transactions", "Advisory Fee debits do not tie to fact_fees (no fee row or different amount)",
         int((rule("Advisory Fee debit has a fact_fees row for that client-month")(t)
              | rule("Advisory Fee debit equals the fact_fees amount for that client-month")(t)).sum()),
         "different systems; use fact_fees for revenue - decision log #19"),
        ("fact_portfolio_snapshot", "snapshot client-months with no fee row",
         int(rule("every snapshot month has a fee row (fee billed for the month)")(t).sum()),
         "cannot create a bill without inventing it - decision log #20"),
        ("fact_transactions", "transactions dated on fixed market holidays marked as trading days",
         int(rule("transaction not dated on a fixed market holiday that dim_date marks as trading")(t).sum()),
         "dim_date only excludes weekends - decision log #21"),
    ]
    for table, issue, rows, note in entries:
        audit.step(table, issue, "leave as is", rows, note)
        print(f"  {table}: {issue} -> {rows:,} rows left as is")


# ---------------------------------------------------------------------------
# Final proof and output
# ---------------------------------------------------------------------------

def verify_and_save(raw, t, audit):
    banner(9, "Prove raw = clean + quarantined, check every change is logged, save outputs")
    changes = (pd.concat(audit.changes, ignore_index=True) if audit.changes else
               pd.DataFrame(columns=["table", "key_column", "key", "column", "old_value", "new_value"]))
    summary = []
    for name in ws.TABLE_ORDER:
        r, c = raw[name], t[name]
        pk = ws.SCHEMA[name]["pk"]
        q = audit.quarantined(name)
        flags = ws.FLAG_COLUMNS.get(name, [])

        # Rows: the clean and quarantined keys are disjoint and together are exactly the raw keys
        q_keys = list(q[pk]) if len(q) else []
        check(len(r) == len(c) + len(q_keys), f"{name}: raw {len(r)} != clean {len(c)} + quarantined {len(q_keys)}")
        check(not set(c[pk]) & set(q_keys), f"{name}: a row is both clean and quarantined")
        check(sorted(list(c[pk]) + q_keys) == sorted(r[pk]), f"{name}: clean + quarantined keys != raw keys")
        if len(q):   # quarantined rows are kept exactly as received
            check(q[list(r.columns)].set_index(pk).equals(r.set_index(pk).loc[q[pk]]),
                  f"{name}: a quarantined row differs from its raw row")

        # Columns: same columns, flags are the only additions
        check(list(c.columns) == list(r.columns) + flags, f"{name}: unexpected columns")

        # Cells: the set of changed (key, column, old, new) equals what value_changes.csv logs
        rk = r.set_index(pk).loc[c[pk]]
        ck = c.set_index(pk)[list(r.columns.drop(pk))]
        diff = (rk != ck).stack()
        diff = diff[diff]
        actual = {(k, col, rk.at[k, col], ck.at[k, col]) for k, col in diff.index}
        logged_df = changes[changes["table"] == name]
        logged = set(zip(logged_df["key"], logged_df["column"], logged_df["old_value"], logged_df["new_value"]))
        check(actual == logged, f"{name}: changed cells and value_changes.csv disagree "
                                f"({len(actual)} changed vs {len(logged)} logged)")
        summary.append({"table": name, "raw_rows": len(r), "clean_rows": len(c),
                        "quarantined_rows": len(q_keys), "cells_changed": len(actual),
                        "flag_columns_added": len(flags)})
    summary = pd.DataFrame(summary)
    print(summary.to_string(index=False))
    print("Verified for all 8 tables: clean keys + quarantined keys = raw keys (no overlap, nothing lost); "
          "quarantined rows equal their raw rows; every changed cell (key, column, old, new) is in "
          "value_changes.csv and nothing else is")

    ws.CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    ws.AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out = {"lineterminator": "\n", "index": False}    # same bytes on Windows and Mac/Linux
    for name in ws.TABLE_ORDER:
        t[name].to_csv(ws.CLEAN_DIR / ws.SCHEMA[name]["file"], **out)
    pd.DataFrame(audit.log).to_csv(ws.AUDIT_DIR / "cleaning_log.csv", **out)
    changes.to_csv(ws.AUDIT_DIR / "value_changes.csv", **out)
    for stem, (_, q) in audit.quarantine.items():
        q.to_csv(ws.AUDIT_DIR / f"{stem}.csv", **out)

    # Reload what was written (as text) and confirm nothing was lost on disk
    for name in ws.TABLE_ORDER:
        back = ws.read_table(ws.CLEAN_DIR / ws.SCHEMA[name]["file"])
        check(list(back.columns) == list(t[name].columns), f"{name}: reloaded columns differ")
        check(back.shape == t[name].shape, f"{name}: reload shape mismatch")
        check((back.values == t[name].reset_index(drop=True).values).all(), f"{name}: reloaded values differ")
    for stem, (_, q) in audit.quarantine.items():
        check(len(ws.read_table(ws.AUDIT_DIR / f"{stem}.csv")) == len(q), f"{stem}: reload row count differs")
    print(f"\nSaved 8 clean tables to {ws.CLEAN_DIR.relative_to(ws.HW_DIR)}/ and the audit trail to "
          f"{ws.AUDIT_DIR.relative_to(ws.HW_DIR)}/ ({len(audit.log)} log entries, {len(changes):,} value "
          f"changes, {len(audit.quarantine)} quarantine files). Reloaded every file and re-checked "
          "columns, shape and values.")


def main():
    raw = ws.load_tables(ws.RAW_DIR)
    for name in ws.TABLE_ORDER:
        check(len(raw[name]) == ws.SCHEMA[name]["rows"], f"{name}: unexpected raw row count")
        check(norm_key(raw[name][ws.SCHEMA[name]["pk"]]).is_unique, f"{name}: raw primary key not unique")
    t = {name: df.copy() for name, df in raw.items()}
    audit = AuditTrail()

    step_dedupe_clients(t, audit)        # dimensions first
    step_standardize_state(t, audit)
    step_quarantine_orphans(t, audit)    # remove rows before repairing values (quarantine keeps raw values)
    step_security_id_format(t, audit)    # then fix the key format and prove every id joins
    step_fix_share_sign(t, audit)        # reconciled value repairs
    step_fix_return_ytd(t, audit)
    step_flags(t, audit)                 # flags last, on the cleaned tables
    log_left_as_is(t, audit)
    verify_and_save(raw, t, audit)


if __name__ == "__main__":
    main()
