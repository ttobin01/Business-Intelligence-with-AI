"""
wildcat_schema.py - Shared metadata for the HW4 Wildcat Capital scripts.

This module holds *declarations only* (file names, keys, expected column types,
allowed values, ranges and relationships). The checking logic lives in the
scripts:

    01_profile.py   - generic profiler + four groups of audit checks
    02_clean.py     - cleaning program (raw -> clean + quarantine + audit trail)
    03_validate.py  - referential integrity, rules, reconciliations, IQR, scorecard

Keeping the rules in one place means the audit, the cleaning asserts and the
validation scorecard all test the *same* definitions.
"""

from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths (everything is relative to the hw04/ folder, so the scripts can be run
# from the repo root or from inside hw04/)
# ---------------------------------------------------------------------------
HW_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = HW_DIR / "data" / "raw"
CLEAN_DIR = HW_DIR / "data" / "clean"
AUDIT_DIR = HW_DIR / "data" / "audit"
REPORTS_DIR = HW_DIR / "reports"

TABLE_ORDER = [
    "dim_advisor", "dim_benchmark", "dim_client", "dim_date", "dim_security",
    "fact_fees", "fact_portfolio_snapshot", "fact_transactions",
]

# Text tokens that pandas' default read_csv turns into NaN (plus '-' and '?',
# which people often type for "unknown"). Reported as INFO, never auto-blanked.
NULL_LIKE_TOKENS = {"none", "null", "nan", "-nan", "n/a", "na", "#n/a", "#na", "<na>", "1.#ind",
                    "-1.#ind", "1.#qnan", "-1.#qnan", "-", "?"}

US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE",
    "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
    "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}

TXN_TYPES_WITH_SECURITY = ["Buy", "Sell", "Dividend"]          # need security_id, shares, price
TXN_TYPES_CASH_ONLY = ["Deposit", "Withdrawal", "Advisory Fee"]  # no security by design

# ---------------------------------------------------------------------------
# Column declarations
#   type: int | float | date | bool_tf ('True'/'False') | flag01 ('0'/'1') | text
#   required: True (never blank) | False (blank allowed) |
#             a callable(df) -> boolean Series of rows where the value is required
#   allowed / min / max / pattern: column-level rules (checked on parsed values)
# ---------------------------------------------------------------------------


def cat(s):
    """Category text normalised for comparisons (strip surrounding spaces)."""
    return s.astype(str).str.strip()


def _is_etf(df):
    return cat(df["is_etf"]) == "True"


def _has_security(df):
    return cat(df["txn_type"]).isin(TXN_TYPES_WITH_SECURITY)


SCHEMA = {
    "dim_advisor": {
        "file": "dim_advisor.csv", "rows": 25, "pk": "advisor_id",
        "near_dup_keys": ["first_name", "last_name"],
        "columns": {
            "advisor_id": {"type": "int", "required": True, "min": 1},
            "first_name": {"type": "text", "required": True},
            "last_name": {"type": "text", "required": True},
            "region": {"type": "text", "required": True,
                       "allowed": ["Northeast", "Mid-Atlantic", "Southeast", "Midwest", "West"]},
            "years_experience": {"type": "int", "required": True, "min": 0, "max": 60},
            "aum_target_mm": {"type": "int", "required": True, "min": 1, "max": 10000},
            # "None" is a legitimate value here (advisor holds no certification)
            "certifications": {"type": "text", "required": True,
                               "allowed": ["CFA", "CFP", "CFP, CFA", "CFP, CIMA", "None"]},
        },
    },
    "dim_benchmark": {
        "file": "dim_benchmark.csv", "rows": 8, "pk": "benchmark_id",
        "near_dup_keys": ["name"],
        "columns": {
            "benchmark_id": {"type": "int", "required": True, "min": 1},
            "name": {"type": "text", "required": True},
            "asset_class": {"type": "text", "required": True},
            "ticker_proxy": {"type": "text", "required": True},
        },
    },
    "dim_client": {
        "file": "dim_client.csv", "rows": 2525, "pk": "client_id",
        # Same person entered twice: every attribute except the id and (possibly
        # mistyped) last name is identical.
        "near_dup_keys": ["first_name", "age", "city", "state", "zip_code", "risk_profile",
                          "client_tier", "primary_account_type", "initial_aum",
                          "client_since", "advisor_id", "is_active"],
        "columns": {
            "client_id": {"type": "int", "required": True, "min": 1},
            "first_name": {"type": "text", "required": True},
            "last_name": {"type": "text", "required": True},
            "age": {"type": "int", "required": True, "min": 18, "max": 110},
            "city": {"type": "text", "required": True},
            "state": {"type": "text", "required": True, "allowed": sorted(US_STATE_CODES)},
            "zip_code": {"type": "text", "required": True, "pattern": r"^\d{5}$"},
            "risk_profile": {"type": "text", "required": True,
                             "allowed": ["Conservative", "Moderately Conservative", "Balanced",
                                         "Moderately Aggressive", "Aggressive"]},
            "client_tier": {"type": "text", "required": True, "allowed": ["Retail", "HNW", "UHNW"]},
            "primary_account_type": {"type": "text", "required": True,
                                     "allowed": ["Taxable", "IRA", "Roth IRA", "Trust", "529"]},
            "initial_aum": {"type": "float", "required": True, "min": 0.01},
            "client_since": {"type": "date", "required": True,
                             "min": "1990-01-01", "max": "2024-12-31"},
            "advisor_id": {"type": "int", "required": True, "min": 1},
            "is_active": {"type": "bool_tf", "required": True},
        },
    },
    "dim_date": {
        "file": "dim_date.csv", "rows": 1827, "pk": "date_id",
        "near_dup_keys": ["date"],
        "columns": {
            "date_id": {"type": "int", "required": True, "min": 1},
            "date": {"type": "date", "required": True, "min": "2020-01-01", "max": "2024-12-31"},
            "year": {"type": "int", "required": True, "min": 2020, "max": 2024},
            "quarter": {"type": "int", "required": True, "min": 1, "max": 4},
            "month": {"type": "int", "required": True, "min": 1, "max": 12},
            "month_name": {"type": "text", "required": True,
                           "allowed": ["January", "February", "March", "April", "May", "June", "July",
                                       "August", "September", "October", "November", "December"]},
            "week_of_year": {"type": "int", "required": True, "min": 1, "max": 53},
            "day_of_week": {"type": "text", "required": True,
                            "allowed": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                                        "Saturday", "Sunday"]},
            "is_month_end": {"type": "flag01", "required": True},
            "is_quarter_end": {"type": "flag01", "required": True},
            "is_year_end": {"type": "flag01", "required": True},
            "is_trading_day": {"type": "flag01", "required": True},
        },
    },
    "dim_security": {
        "file": "dim_security.csv", "rows": 500, "pk": "security_id",
        "near_dup_keys": ["ticker"],
        "columns": {
            "security_id": {"type": "int", "required": True, "min": 1},
            "ticker": {"type": "text", "required": True, "pattern": r"^[A-Z]{1,5}$"},
            "name": {"type": "text", "required": True},
            "asset_class": {"type": "text", "required": True,
                            "allowed": ["Equity", "Fixed Income", "Alternative", "Cash Equivalent"]},
            # Structural nulls: ETFs have no sector, single stocks have no expense ratio
            "sector": {"type": "text", "required": lambda df: ~_is_etf(df)},
            "benchmark_id": {"type": "int", "required": True, "min": 1},
            "is_etf": {"type": "bool_tf", "required": True},
            "expense_ratio_bps": {"type": "float", "required": _is_etf, "min": 0, "max": 300},
        },
    },
    "fact_fees": {
        "file": "fact_fees.csv", "rows": 122197, "pk": "fee_id",
        "near_dup_keys": ["client_id", "fee_date"],      # grain: one row per client per month
        "columns": {
            "fee_id": {"type": "int", "required": True, "min": 1},
            "client_id": {"type": "int", "required": True, "min": 1},
            "advisor_id": {"type": "int", "required": True, "min": 1},
            "fee_date": {"type": "date", "required": True, "min": "2020-01-01", "max": "2024-12-31"},
            "fee_type": {"type": "text", "required": True,
                         "allowed": ["Advisory", "Custodial", "Management", "Performance"]},
            "aum_basis": {"type": "float", "required": True, "min": 0.01},
            "bps_charged": {"type": "float", "required": True, "min": 0.01, "max": 300},
            "amount": {"type": "float", "required": True, "min": 0.01},
        },
    },
    "fact_portfolio_snapshot": {
        "file": "fact_portfolio_snapshot.csv", "rows": 129547, "pk": "snapshot_id",
        "near_dup_keys": ["client_id", "snapshot_date"],  # grain: one row per client per month
        "columns": {
            "snapshot_id": {"type": "int", "required": True, "min": 1},
            "client_id": {"type": "int", "required": True, "min": 1},
            "advisor_id": {"type": "int", "required": True, "min": 1},
            "benchmark_id": {"type": "int", "required": True, "min": 1},
            "snapshot_date": {"type": "date", "required": True, "min": "2020-01-01", "max": "2024-12-31"},
            "year": {"type": "int", "required": True, "min": 2020, "max": 2024},
            "month": {"type": "int", "required": True, "min": 1, "max": 12},
            "aum": {"type": "float", "required": True, "min": 0.01},
            "return_ytd": {"type": "float", "required": True, "min": -1.0},     # cannot lose >100%
            "benchmark_return_ytd": {"type": "float", "required": True, "min": -1.0},
            "active_alpha_ytd": {"type": "float", "required": True},
            "cash_pct": {"type": "float", "required": True, "min": 0.0, "max": 1.0},
            "account_type": {"type": "text", "required": True,
                             "allowed": ["Taxable", "IRA", "Roth IRA", "Trust", "529"]},
        },
    },
    "fact_transactions": {
        "file": "fact_transactions.csv", "rows": 298772, "pk": "txn_id",
        "near_dup_keys": ["client_id", "advisor_id", "security_id", "txn_date", "txn_type",
                          "shares", "price", "amount"],      # identical event except the id
        "columns": {
            "txn_id": {"type": "int", "required": True, "min": 1},
            "client_id": {"type": "int", "required": True, "min": 1},
            "advisor_id": {"type": "int", "required": True, "min": 1},
            "security_id": {"type": "int", "min": 1, "required": _has_security},
            "txn_date": {"type": "date", "required": True, "min": "2020-01-01", "max": "2024-12-31"},
            "txn_type": {"type": "text", "required": True,
                         "allowed": TXN_TYPES_WITH_SECURITY + TXN_TYPES_CASH_ONLY},
            # sign rule (shares > 0) is a row rule in ROW_RULES
            "shares": {"type": "float", "required": _has_security},
            "price": {"type": "float", "min": 0.01, "required": _has_security},
            "amount": {"type": "float", "required": True, "min": 0.01},  # direction comes from txn_type
        },
    },
}

# ---------------------------------------------------------------------------
# Relationships: 10 ID-based + 3 date joins = 13
# (child table, child column, parent table, parent column)
# ---------------------------------------------------------------------------
RELATIONSHIPS = [
    ("dim_client", "advisor_id", "dim_advisor", "advisor_id"),
    ("dim_security", "benchmark_id", "dim_benchmark", "benchmark_id"),
    ("fact_transactions", "client_id", "dim_client", "client_id"),
    ("fact_transactions", "advisor_id", "dim_advisor", "advisor_id"),
    ("fact_transactions", "security_id", "dim_security", "security_id"),
    ("fact_fees", "client_id", "dim_client", "client_id"),
    ("fact_fees", "advisor_id", "dim_advisor", "advisor_id"),
    ("fact_portfolio_snapshot", "client_id", "dim_client", "client_id"),
    ("fact_portfolio_snapshot", "advisor_id", "dim_advisor", "advisor_id"),
    ("fact_portfolio_snapshot", "benchmark_id", "dim_benchmark", "benchmark_id"),
    ("fact_transactions", "txn_date", "dim_date", "date"),
    ("fact_fees", "fee_date", "dim_date", "date"),
    ("fact_portfolio_snapshot", "snapshot_date", "dim_date", "date"),
]

# Flag columns added by 02_clean.py (not part of the raw schema)
FLAG_COLUMNS = {
    "fact_transactions": ["trade_on_non_trading_day_flag", "txn_after_last_snapshot_flag"],
    "fact_fees": ["aum_floor_flag"],
    "fact_portfolio_snapshot": ["aum_floor_flag", "extreme_return_flag"],
}

AUM_FLOOR_VALUE = 1000.0          # suspicious placeholder balance seen in snapshots / fee basis
EXTREME_ALPHA_THRESHOLD = 0.50    # |return - benchmark| > 50 percentage points year-to-date


# ---------------------------------------------------------------------------
# Small shared helpers (parsing only; no business decisions)
# ---------------------------------------------------------------------------

def read_table(path):
    """Read a CSV with every column as text, exactly as the assignment requires."""
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_tables(folder):
    """Load all eight tables from a folder into a dict {name: DataFrame}."""
    return {name: read_table(Path(folder) / SCHEMA[name]["file"]) for name in TABLE_ORDER}


def blank(s):
    """True where a value is empty, whitespace only, or a real missing value (NaN/None)."""
    return s.isna() | (s.astype(str).str.strip() == "")


def _text(s):
    """Text view of a column with real missing values turned into ''."""
    s = s.astype(object)
    return s.where(s.notna(), "").astype(str).str.strip()


def to_num(s):
    """Parse text to float; blanks, unparseable text and +/-inf become NaN (never guessed)."""
    t = _text(s)
    x = pd.to_numeric(t.where(t != "", np.nan), errors="coerce")
    return x.where(np.isfinite(x))


def to_date(s):
    """Parse ISO yyyy-mm-dd text to datetime; anything else becomes NaT."""
    t = _text(s)
    return pd.to_datetime(t.where(t != "", None), format="%Y-%m-%d", errors="coerce")


def valid_type_mask(s, col_type):
    """Boolean Series: does each non-blank value conform to the declared type?
    ([0-9] rather than a "digit" class, so the answer is the same with or without pyarrow strings.)"""
    t = _text(s)
    if col_type == "int":
        return t.str.fullmatch(r"-?[0-9]+")
    if col_type == "float":
        return to_num(t).notna() & ~t.str.contains("%", regex=False)
    if col_type == "date":
        return t.str.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}") & to_date(t).notna()
    if col_type == "bool_tf":
        return t.isin(["True", "False"])
    if col_type == "flag01":
        return t.isin(["0", "1"])
    return pd.Series(True, index=s.index)  # text: anything non-blank is a valid string


def required_mask(df, spec):
    """Rows where the column is required to be non-blank."""
    req = spec.get("required", True)
    if callable(req):
        return req(df).fillna(False).astype(bool)
    return pd.Series(bool(req), index=df.index)


def norm_key(s):
    """Normalise a key for joins and duplicate tests.

    Strips spaces, turns real missing values (NaN/None) and null-like tokens
    into '' (= null key), and removes a trailing '.0' from whole numbers so a
    float-formatted id (45.0) equals 45. Anything else is left as written,
    so '045' or 'A-1' stay different keys (reported by the type checks).
    """
    t = _text(s)
    t = t.where(~t.str.lower().isin(NULL_LIKE_TOKENS), "")
    return t.str.replace(r"^(-?[0-9]+)\.0+$", r"\1", regex=True)


# ---------------------------------------------------------------------------
# Row-level business rules (single table). Each rule is
#   (table, description, dimension, severity, violates(df), applies(df) or None)
# violates() is True where a row BREAKS the rule; applies() marks the rows the
# rule is about (None = every row), which is the denominator for pass rates.
# Rows whose inputs are blank or unparseable are not counted as violations
# here - type validity and completeness checks report those separately.
# ---------------------------------------------------------------------------

def _rule_client_tier_vs_aum(df):
    aum, tier = to_num(df["initial_aum"]), cat(df["client_tier"])
    expected = pd.Series(np.select([aum < 500_000, aum < 5_000_000], ["Retail", "HNW"], "UHNW"),
                         index=df.index)
    return aum.notna() & tier.isin(["Retail", "HNW", "UHNW"]) & (tier != expected)


def _rule_date_attributes(df):
    d = to_date(df["date"])
    ok = d.notna()
    bad = pd.Series(False, index=df.index)
    checks = {
        "year": d.dt.year, "quarter": d.dt.quarter, "month": d.dt.month,
        "week_of_year": d.dt.isocalendar().week.astype("float"),
        "is_month_end": d.dt.is_month_end.astype(float),
        "is_quarter_end": d.dt.is_quarter_end.astype(float),
        "is_year_end": d.dt.is_year_end.astype(float),
    }
    for col, exp in checks.items():
        v = to_num(df[col])
        bad |= ok & v.notna() & (v != exp)          # blanks are reported by completeness, not here
    for col, exp in (("month_name", d.dt.month_name()), ("day_of_week", d.dt.day_name())):
        v = cat(df[col])
        bad |= ok & (v != "") & (v != exp)
    return bad


def _rule_weekend_trading_day(df):
    d = to_date(df["date"])
    return d.notna() & (d.dt.dayofweek >= 5) & (cat(df["is_trading_day"]) == "1")


def _rule_security_etf_vs_class(df):
    etf = cat(df["is_etf"]) == "True"
    equity = cat(df["asset_class"]) == "Equity"
    return cat(df["is_etf"]).isin(["True", "False"]) & (etf == equity)


def _rule_structural_nulls_security(df):
    etf = cat(df["is_etf"]) == "True"
    return (etf & ~blank(df["sector"])) | (~etf & ~blank(df["expense_ratio_bps"]))


def _rule_fee_amount_recompute(df):
    calc = (to_num(df["aum_basis"]) * to_num(df["bps_charged"]) / 10_000 / 12).round(2)
    amt = to_num(df["amount"])
    return calc.notna() & amt.notna() & ((calc - amt).abs() > 0.011)


def _rule_first_of_month(col):
    def f(df):
        d = to_date(df[col])
        return d.notna() & (d.dt.day != 1)
    return f


def _rule_snapshot_year_month(df):
    d = to_date(df["snapshot_date"])
    y, m = to_num(df["year"]), to_num(df["month"])
    return d.notna() & ((y.notna() & (y != d.dt.year)) | (m.notna() & (m != d.dt.month)))


def _rule_alpha_recompute(df):
    r, b, a = to_num(df["return_ytd"]), to_num(df["benchmark_return_ytd"]), to_num(df["active_alpha_ytd"])
    # values are stored to 6 decimals, so allow a 1e-5 rounding tolerance
    return r.notna() & b.notna() & a.notna() & ((r - b - a).abs() > 1e-5)


def _rule_aum_floor(col):
    def f(df):
        return to_num(df[col]) == AUM_FLOOR_VALUE
    return f


def _rule_extreme_alpha(df):
    return to_num(df["active_alpha_ytd"]).abs() > EXTREME_ALPHA_THRESHOLD


def _rule_txn_security_presence(df):
    needs = _has_security(df)
    has_any = ~blank(df["security_id"]) | ~blank(df["shares"]) | ~blank(df["price"])
    has_all = ~blank(df["security_id"]) & ~blank(df["shares"]) & ~blank(df["price"])
    return (needs & ~has_all) | (~needs & has_any)


def _rule_txn_shares_sign(df):
    return to_num(df["shares"]) <= 0          # zero shares is not a trade either


def _applies_shares(df):
    return to_num(df["shares"]).notna()


def _rule_dividend_equals_position_value(df):
    calc = (to_num(df["shares"]).abs() * to_num(df["price"])).round(2)
    return (cat(df["txn_type"]) == "Dividend") & ((calc - to_num(df["amount"])).abs() <= 0.011)


def _applies_dividend(df):
    return cat(df["txn_type"]) == "Dividend"


# First digit of a ZIP code by state (USPS national area). Used only as a
# plausibility check - a mismatch cannot tell us WHICH of the two is wrong.
ZIP_FIRST_DIGIT = {
    "0": "CT MA ME NH NJ PR RI VT", "1": "DE NY PA", "2": "DC MD NC SC VA WV",
    "3": "AL FL GA MS TN", "4": "IN KY MI OH", "5": "IA MN MT ND SD WI",
    "6": "IL KS MO NE", "7": "AR LA OK TX", "8": "AZ CO ID NM NV UT WY", "9": "AK CA HI OR WA",
}
_STATE_TO_DIGIT = {st: d for d, sts in ZIP_FIRST_DIGIT.items() for st in sts.split()}


def _applies_zip_state(df):
    return cat(df["state"]).map(_STATE_TO_DIGIT).notna() & cat(df["zip_code"]).str.fullmatch(r"[0-9]{5}")


def _rule_zip_matches_state(df):
    exp = cat(df["state"]).map(_STATE_TO_DIGIT)
    return _applies_zip_state(df) & (cat(df["zip_code"]).str[0] != exp)


def _rule_fixed_holiday_trading_day(df):
    d = to_date(df["date"])
    md = d.dt.strftime("%m-%d")
    return d.notna() & md.isin(["01-01", "07-04", "12-25"]) & (cat(df["is_trading_day"]) == "1")


def _rule_txn_amount_recompute(df):
    calc = (to_num(df["shares"]).abs() * to_num(df["price"])).round(2)
    amt = to_num(df["amount"])
    return calc.notna() & amt.notna() & ((calc - amt).abs() > 0.011)


def _applies_txn_recompute(df):
    return to_num(df["shares"]).notna() & to_num(df["price"]).notna() & to_num(df["amount"]).notna()


ROW_RULES = [
    ("dim_client", "client_tier matches initial_aum band (<$0.5M Retail, <$5M HNW, else UHNW)",
     "Consistency", "ERROR", _rule_client_tier_vs_aum, None),
    ("dim_client", "zip_code first digit is consistent with state (USPS area)",
     "Accuracy/Plausibility", "INFO", _rule_zip_matches_state, _applies_zip_state),
    ("dim_date", "year/quarter/month/week/day names/period-end flags agree with date",
     "Consistency", "ERROR", _rule_date_attributes, None),
    ("dim_date", "weekend dates are not trading days", "Accuracy/Plausibility", "ERROR",
     _rule_weekend_trading_day, None),
    ("dim_date", "fixed market holidays (Jan 1, Jul 4, Dec 25) are not trading days",
     "Accuracy/Plausibility", "INFO", _rule_fixed_holiday_trading_day, None),
    ("dim_security", "is_etf is True exactly when asset_class is not Equity", "Consistency", "ERROR",
     _rule_security_etf_vs_class, None),
    ("dim_security", "ETFs have no sector and single stocks have no expense ratio (structural nulls)",
     "Consistency", "ERROR", _rule_structural_nulls_security, None),
    ("fact_fees", "amount = round(aum_basis x bps_charged / 10,000 / 12, 2)", "Accuracy/Plausibility",
     "ERROR", _rule_fee_amount_recompute, None),
    ("fact_fees", "fee_date falls on the 1st of the month (monthly grain)", "Validity", "ERROR",
     _rule_first_of_month("fee_date"), None),
    ("fact_fees", "aum_basis is not the $1,000 placeholder floor", "Accuracy/Plausibility", "WARN",
     _rule_aum_floor("aum_basis"), None),
    ("fact_portfolio_snapshot", "year and month agree with snapshot_date", "Consistency", "ERROR",
     _rule_snapshot_year_month, None),
    ("fact_portfolio_snapshot", "snapshot_date falls on the 1st of the month (monthly grain)",
     "Validity", "ERROR", _rule_first_of_month("snapshot_date"), None),
    ("fact_portfolio_snapshot", "active_alpha_ytd = return_ytd - benchmark_return_ytd",
     "Accuracy/Plausibility", "ERROR", _rule_alpha_recompute, None),
    ("fact_portfolio_snapshot", "aum is not the $1,000 placeholder floor", "Accuracy/Plausibility",
     "WARN", _rule_aum_floor("aum"), None),
    ("fact_portfolio_snapshot", "|active_alpha_ytd| <= 0.50 (within 50 points of benchmark)",
     "Accuracy/Plausibility", "WARN", _rule_extreme_alpha, None),
    ("fact_transactions", "security_id/shares/price present for Buy/Sell/Dividend and absent otherwise",
     "Completeness", "ERROR", _rule_txn_security_presence, None),
    ("fact_transactions", "shares is positive (direction comes from txn_type)", "Validity", "ERROR",
     _rule_txn_shares_sign, _applies_shares),
    ("fact_transactions", "amount = round(|shares| x price, 2) for security rows",
     "Accuracy/Plausibility", "ERROR", _rule_txn_amount_recompute, _applies_txn_recompute),
    ("fact_transactions", "Dividend amount is not the full position value (shares x price)",
     "Accuracy/Plausibility", "INFO", _rule_dividend_equals_position_value, _applies_dividend),
]


def rule_function(name):
    """Look up a row or cross-table rule's violation function by its description."""
    for r in ROW_RULES + CROSS_RULES:
        if r[1] == name:
            return r[4]
    raise KeyError(name)


# ---------------------------------------------------------------------------
# Cross-table business rules: facts that disagree with dimensions or with
# each other. Same tuple shape as ROW_RULES, but violates()/applies() receive
# the dict of tables and return a Series aligned to the named table.
# ---------------------------------------------------------------------------

def _lookup(child, child_col, parent, parent_key, parent_col):
    """Map each child row's key to a parent attribute (NaN where no parent)."""
    p = parent.assign(_k=norm_key(parent[parent_key]))
    p = p[p["_k"] != ""].drop_duplicates("_k").set_index("_k")[parent_col]
    return norm_key(child[child_col]).map(p)


def _month_key(df, client_col, date_col):
    return norm_key(df[client_col]) + "|" + to_date(df[date_col]).dt.strftime("%Y-%m")


def _cross_advisor_matches_client(fact):
    def f(t):
        df = t[fact]
        cli_adv = _lookup(df, "client_id", t["dim_client"], "client_id", "advisor_id")
        return cli_adv.notna() & (norm_key(df["advisor_id"]) != norm_key(cli_adv))
    return f


def _cross_snapshot_account_type(t):
    df = t["fact_portfolio_snapshot"]
    acct = _lookup(df, "client_id", t["dim_client"], "client_id", "primary_account_type")
    return acct.notna() & (cat(df["account_type"]) != cat(acct))


def _snapshot_aum_by_month(t):
    snap = t["fact_portfolio_snapshot"]
    aum = pd.Series(to_num(snap["aum"]).values, index=_month_key(snap, "client_id", "snapshot_date"))
    return aum[~aum.index.duplicated()]


def _cross_fee_basis_vs_snapshot(t):
    fees = t["fact_fees"]
    snap_aum = _month_key(fees, "client_id", "fee_date").map(_snapshot_aum_by_month(t))
    return snap_aum.notna() & ((to_num(fees["aum_basis"]) - snap_aum).abs() > 0.011)


def _cross_fee_has_snapshot(t):
    fees, snap = t["fact_fees"], t["fact_portfolio_snapshot"]
    return ~_month_key(fees, "client_id", "fee_date").isin(set(_month_key(snap, "client_id", "snapshot_date")))


def _cross_snapshot_has_fee(t):
    fees, snap = t["fact_fees"], t["fact_portfolio_snapshot"]
    return ~_month_key(snap, "client_id", "snapshot_date").isin(set(_month_key(fees, "client_id", "fee_date")))


def _is_advisory_fee(t):
    return cat(t["fact_transactions"]["txn_type"]) == "Advisory Fee"


def _billed_fee(t):
    fees = t["fact_fees"]
    fee_amt = pd.Series(to_num(fees["amount"]).values, index=_month_key(fees, "client_id", "fee_date"))
    fee_amt = fee_amt[~fee_amt.index.duplicated()]
    return _month_key(t["fact_transactions"], "client_id", "txn_date").map(fee_amt)


def _cross_advisory_fee_no_fee_row(t):
    return _is_advisory_fee(t) & _billed_fee(t).isna()


def _cross_advisory_fee_amount_differs(t):
    billed = _billed_fee(t)
    amt = to_num(t["fact_transactions"]["amount"])
    return _is_advisory_fee(t) & billed.notna() & ((amt - billed).abs() > 0.011)


def _cross_txn_on_fixed_holiday(t):
    tx, d = t["fact_transactions"], t["dim_date"]
    hol = _rule_fixed_holiday_trading_day(d)
    return cat(tx["txn_date"]).isin(set(cat(d.loc[hol, "date"])))


def _is_trade(t):
    return cat(t["fact_transactions"]["txn_type"]).isin(["Buy", "Sell"])


def _cross_trade_on_non_trading_day(t):
    tx, d = t["fact_transactions"], t["dim_date"]
    cal = d.assign(_d=cat(d["date"])).drop_duplicates("_d").set_index("_d")["is_trading_day"]
    flag = cat(tx["txn_date"]).map(cal)
    return _is_trade(t) & (cat(flag) == "0")


def _last_snapshot_month(t, keys):
    snap = t["fact_portfolio_snapshot"]
    last = to_date(snap["snapshot_date"]).groupby(norm_key(snap["client_id"])).max()
    return norm_key(keys).map(last)


def _cross_txn_after_last_snapshot(t):
    tx = t["fact_transactions"]
    last_month = _last_snapshot_month(t, tx["client_id"])
    txn_month = to_date(tx["txn_date"]).dt.to_period("M").dt.to_timestamp()
    return last_month.notna() & txn_month.notna() & (txn_month > last_month)


def _cross_txn_before_client_since(t):
    tx = t["fact_transactions"]
    since = to_date(_lookup(tx, "client_id", t["dim_client"], "client_id", "client_since"))
    return since.notna() & (to_date(tx["txn_date"]) < since)


def _cross_inactive_with_latest_snapshot(t):
    cli = t["dim_client"]
    client_last = _last_snapshot_month(t, cli["client_id"])
    latest = to_date(t["fact_portfolio_snapshot"]["snapshot_date"]).max()
    active = cat(cli["is_active"])
    known = client_last.notna() & active.isin(["True", "False"])
    return known & ((active == "True") != (client_last == latest))


CROSS_RULES = [
    ("fact_transactions", "advisor_id matches the client's advisor in dim_client", "Consistency",
     "ERROR", _cross_advisor_matches_client("fact_transactions"), None),
    ("fact_fees", "advisor_id matches the client's advisor in dim_client", "Consistency", "ERROR",
     _cross_advisor_matches_client("fact_fees"), None),
    ("fact_portfolio_snapshot", "advisor_id matches the client's advisor in dim_client",
     "Consistency", "ERROR", _cross_advisor_matches_client("fact_portfolio_snapshot"), None),
    ("fact_portfolio_snapshot", "account_type matches the client's primary_account_type",
     "Consistency", "ERROR", _cross_snapshot_account_type, None),
    ("fact_fees", "aum_basis equals the snapshot aum for the same client and month",
     "Accuracy/Plausibility", "ERROR", _cross_fee_basis_vs_snapshot, None),
    ("fact_fees", "every fee row has a portfolio snapshot for the same client and month",
     "Consistency", "ERROR", _cross_fee_has_snapshot, None),
    ("fact_portfolio_snapshot", "every snapshot month has a fee row (fee billed for the month)",
     "Completeness", "INFO", _cross_snapshot_has_fee, None),
    ("fact_transactions", "Advisory Fee debit has a fact_fees row for that client-month",
     "Consistency", "INFO", _cross_advisory_fee_no_fee_row, _is_advisory_fee),
    ("fact_transactions", "Advisory Fee debit equals the fact_fees amount for that client-month",
     "Consistency", "INFO", _cross_advisory_fee_amount_differs, _is_advisory_fee),
    ("fact_transactions", "Buy/Sell trades fall on a trading day in dim_date",
     "Accuracy/Plausibility", "WARN", _cross_trade_on_non_trading_day, _is_trade),
    ("fact_transactions", "transaction not dated on a fixed market holiday that dim_date marks as trading",
     "Accuracy/Plausibility", "INFO", _cross_txn_on_fixed_holiday, None),
    ("fact_transactions", "no transaction after the client's last portfolio snapshot month",
     "Consistency", "WARN", _cross_txn_after_last_snapshot, None),
    ("fact_transactions", "no transaction before the client's client_since date", "Consistency",
     "ERROR", _cross_txn_before_client_since, None),
    ("dim_client", "is_active = True exactly when the client has a snapshot in the latest month",
     "Consistency", "ERROR", _cross_inactive_with_latest_snapshot, None),
]
