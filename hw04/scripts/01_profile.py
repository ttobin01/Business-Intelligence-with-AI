"""
01_profile.py - Generic data profiler and data-quality audit (HW4 Part A).

    python hw04/scripts/01_profile.py                 # audit the 8 raw Wildcat tables
    python hw04/scripts/01_profile.py some_file.csv   # profile ANY csv (generic checks only)

Every file is read as text (dtype=str, keep_default_na=False) so nothing is
silently converted before we look at it.

Outputs (default run):
    reports/profile_raw.csv     one row per table x column (profile metrics)
    reports/dq_summary_raw.csv  one row per finding, tagged ERROR / WARN / INFO,
                                in four check groups:
                                  1 Column level   2 Single-table rules
                                  3 Referential integrity   4 Cross-table rules

The profiler (profile_table) and the column-level checks are generic: they
work on any DataFrame. Business knowledge - expected types, allowed values,
ranges, keys and relationships - is declared once in wildcat_schema.py.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wildcat_schema as ws  # noqa: E402

# Reuse the ONE referential-integrity function that lives in 03_validate.py
_spec = importlib.util.spec_from_file_location(
    "validate_mod", Path(__file__).resolve().parent / "03_validate.py")
_validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_validate)
check_referential_integrity = _validate.check_referential_integrity

SEVERITY_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}
FACT_TABLES = {}   # filled by audit() so dimension checks can count related fact rows


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def value_shapes(s):
    """Abstract each value to its 'shape': letter runs -> A/a, digit runs -> 9.

    'Pennsylvania' -> 'Aa', 'PA' -> 'A', '45.0' -> '9.9', '9.28%' -> '9.9%',
    '-7.6e-05' -> '-9.9a-9'. Different shapes in one column = mixed formats.
    (Vectorised over a whole Series for speed.)
    """
    s = s.astype(str)
    s = s.str.replace(r"[A-Z]+", "A", regex=True).str.replace(r"[a-z]+", "a", regex=True)
    s = s.str.replace(r"[0-9]+", "9", regex=True).str.replace(r"(Aa)+", "Aa", regex=True)
    return s


def infer_type(s):
    """Guess a column's type from its non-blank values (used when no schema exists).

    Picks the most specific type that at least half of the values fit, so a
    numeric column with a few bad entries is still treated as numeric and its
    bad entries are reported as type failures (rather than hidden as 'text').
    """
    t = s[~ws.blank(s)].astype(str).str.strip()
    if t.empty:
        return "text"
    for col_type in ("flag01", "bool_tf", "int", "float", "date"):
        if ws.valid_type_mask(t, col_type).mean() >= 0.5:
            return col_type
    return "text"


def infer_key(df):
    """Generic mode: the candidate primary key.

    The first column NAMED like a key ('id' or '*_id') is the candidate whether
    or not its values are unique, so a duplicated id makes the uniqueness check
    FAIL instead of making the check disappear. Without such a name, the first
    column is used only if it is complete and unique (otherwise there is no key)."""
    if not len(df.columns):
        return None
    named = [c for c in df.columns if c.lower() == "id" or c.lower().endswith("_id")]
    if named:
        return named[0]
    k = ws.norm_key(df[df.columns[0]])
    return df.columns[0] if len(df) and (k != "").all() and k.is_unique else None


def profile_table(df, table_name, schema=None):
    """Profile every column of any DataFrame read as text.

    Returns one row per column with: blank/null counts, null-like tokens,
    distinct count, top values, dominant value shapes, number of formats,
    share failing to parse as the expected type, whitespace problems, and
    numeric (or date) min/max.
    """
    cols_spec = (schema or {}).get("columns", {})
    rows = []
    n = len(df)
    for col in df.columns:
        # real NaN/None -> '' first: astype(str) alone would turn NaN into the text 'nan' on pandas 2
        s = df[col].astype(object).where(df[col].notna(), "").astype(str)
        spec = cols_spec.get(col, {})
        col_type = spec.get("type") or infer_type(s)
        is_blank = ws.blank(s)
        non_blank = s[~is_blank]
        stripped = non_blank.str.strip()

        shapes = value_shapes(non_blank).value_counts()
        # A leading minus sign is a value, not a format
        formats = value_shapes(non_blank.str.lstrip("-")).value_counts()
        type_ok = ws.valid_type_mask(non_blank, col_type)
        whitespace = (non_blank != stripped) | non_blank.str.contains(r"\s{2,}", regex=True)

        req_blank = ""
        if spec:
            req_blank = int((is_blank & ws.required_mask(df, spec)).sum())

        # min/max over every value that parses as a number/date (even if it is in
        # the wrong format for the column, e.g. '45.0' in an int column)
        vmin = vmax = ""
        if col_type in ("int", "float"):
            num = ws.to_num(stripped)
            if num.notna().any():
                vmin, vmax = num.min(), num.max()
        elif col_type == "date":
            d = ws.to_date(stripped)
            if d.notna().any():
                vmin, vmax = d.min().date().isoformat(), d.max().date().isoformat()
        vc = non_blank.value_counts()
        top = sorted(vc.items(), key=lambda kv: (-kv[1], str(kv[0])))[:3]   # deterministic ties

        rows.append({
            "table": table_name,
            "column": col,
            "rows": n,
            "expected_type": col_type,
            "type_source": "schema" if spec.get("type") else "inferred",
            "blank_count": int(is_blank.sum()),
            "blank_pct": round(100 * is_blank.mean(), 3) if n else 0.0,
            "required_blank_count": req_blank,
            "null_like_token_count": int(stripped.str.lower().isin(ws.NULL_LIKE_TOKENS).sum()),
            "distinct_count": int(non_blank.nunique()),
            "top_values": "; ".join(f"{k}={v}" for k, v in top),
            "dominant_shapes": "; ".join(f"'{k}'={v}" for k, v in shapes.head(4).items()),
            "n_formats": int(len(formats)),
            "type_fail_count": int((~type_ok).sum()),
            "type_fail_pct_of_nonblank": round(100 * (~type_ok).mean(), 3) if len(non_blank) else 0.0,
            "whitespace_count": int(whitespace.sum()),
            "min": vmin,
            "max": vmax,
        })
    return pd.DataFrame(rows)


class Findings:
    """Collects audit findings in one consistent shape."""

    def __init__(self):
        self.rows = []

    def add(self, table, column, group, check, dimension, severity, affected, total,
            example="", detail="", record_pass=True):
        """Record one check. A check with 0 affected rows is kept as status=PASS
        (severity INFO) so the summary shows what was tested, not only what failed."""
        if affected == 0:
            if not record_pass:
                return
            status, severity, example, detail = "PASS", "INFO", "", "checked - no violations"
        else:
            status = "FAIL"
        self.rows.append({
            "status": status,
            "table": table, "column": column, "check_group": group, "check": check,
            "dimension": dimension, "severity": severity, "rows_affected": int(affected),
            "pct_of_rows": round(100 * affected / total, 3) if total else 0.0,
            "example": str(example)[:200], "detail": detail,
        })

    def frame(self):
        cols = ["status", "table", "column", "check_group", "check", "dimension", "severity",
                "rows_affected", "pct_of_rows", "example", "detail"]
        out = pd.DataFrame(self.rows, columns=cols)
        if out.empty:
            return out
        out["_s"] = out["severity"].map(SEVERITY_ORDER)
        out["_p"] = (out["status"] == "PASS").astype(int)
        out = out.sort_values(["_p", "_s", "table", "check_group", "column"], kind="stable")
        out = out.drop(columns=["_s", "_p"])
        out.insert(0, "finding_id", [f"F{i:03d}" for i in range(1, len(out) + 1)])
        return out


def _examples(series, k=3):
    return ", ".join(repr(v) for v in series.unique()[:k])


def _range_text(s):
    """Min-max of a key column: numeric if every value is a number, else as text."""
    num = ws.to_num(s)
    if len(s) and num.notna().all():
        return f"{num.min():g}-{num.max():g}"
    t = sorted(ws.norm_key(s).unique())
    return f"{t[0]}..{t[-1]}" if t else ""


def _evidence(df, mask):
    """Drill-down for a failed rule: distinct clients affected and the mix of
    categorical columns such as txn_type (helps tell a defect from structure)."""
    parts = []
    if mask.any():
        if "client_id" in df.columns:
            parts.append(f"{df.loc[mask, 'client_id'].nunique():,} distinct clients")
        for col in ("txn_type", "fee_type", "client_tier", "is_active"):
            if col in df.columns:
                vc = df.loc[mask, col].value_counts()
                parts.append(f"{col}: " + ", ".join(f"{k} {v:,}" for k, v in vc.items()))
    return "; ".join(parts)


def missingness_profile(df, col, max_levels=10):
    """MCAR/MAR probe: blank rate of `col` within each level of every other
    low-cardinality column. Large differences suggest the gaps are NOT random."""
    miss = ws.blank(df[col])
    out = []
    for other in df.columns:
        if other == col:
            continue
        levels = df[other].nunique()
        if 2 <= levels <= max_levels:
            rates = miss.groupby(df[other]).mean()
            out.append((other, rates.max() - rates.min(),
                        ", ".join(f"{k} {100 * v:.1f}%" for k, v in rates.sort_index().items())))
    # also by year of any date column (e.g. onboarding year)
    for other in df.columns:
        if other != col and df[other].astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}").mean() > 0.95:
            yr = df[other].str[:4]
            counts = miss.groupby(yr).sum()
            out.append((f"{other} year (blank count)", np.nan,
                        ", ".join(f"{k} {int(v)}" for k, v in counts.sort_index().items())))
    return out


# ---------------------------------------------------------------------------
# Group 1 - column level (generic engine + declared expectations)
# ---------------------------------------------------------------------------

def column_checks(df, table, schema, prof, f):
    n = len(df)
    spec_cols = (schema or {}).get("columns", {})
    pk = (schema or {}).get("pk")
    fk_cols = {c for (t, c, _, _) in ws.RELATIONSHIPS if t == table}
    G = "1 Column level"

    for _, p in prof.iterrows():
        col = p["column"]
        s = df[col].astype(str)
        st = s.str.strip()
        spec = spec_cols.get(col, {})
        is_key = col == pk or col in fk_cols
        nb = ~ws.blank(s)

        # Type validity (text columns accept any string, so nothing to test)
        bad_type = nb & ~ws.valid_type_mask(s, p["expected_type"])
        if p["expected_type"] != "text":
            f.add(table, col, G, f"value does not parse as {p['expected_type']}", "Validity",
                  "ERROR", bad_type.sum(), n, _examples(s[bad_type]),
                  "Wrong format for the column's type; breaks numeric math or joins; "
                  f"formats: {value_shapes(s[bad_type]).value_counts().head(4).to_dict()}; "
                  + _evidence(df, bad_type))

        # Mixed formats among values that DO parse (e.g. scientific notation)
        if p["n_formats"] > 1 and p["expected_type"] in ("int", "float", "date"):
            good = s[nb & ws.valid_type_mask(s, p["expected_type"])]
            fm = value_shapes(good.str.lstrip("-"))
            minority = (fm != fm.value_counts().index[0]) if len(fm) else fm.astype(bool)
            f.add(table, col, G, "mixed representations of valid values", "Consistency",
                  "INFO", minority.sum(), n, _examples(good[minority]),
                  "Parses correctly, but is written in a different format from most values",
                  record_pass=False)

        # Completeness: required blanks vs structural blanks
        if spec:
            req = ws.required_mask(df, spec)
            miss_req = (~nb) & req
            detail = "Blank where the business requires a value"
            if miss_req.any() and not is_key:
                probe = missingness_profile(df, col)
                detail += ". Blank rate by group (MCAR check): " + " | ".join(
                    f"{o}: {txt}" for o, _, txt in probe)
            f.add(table, col, G, "required value is blank", "Completeness",
                  "ERROR" if is_key else "WARN", miss_req.sum(), n, "", detail)
            struct = (~nb) & ~req
            f.add(table, col, G, "blank by design (structural null)", "Completeness",
                  "INFO", struct.sum(), n, "",
                  "Blank is legitimate for these rows (e.g. no security on a cash flow); do not fill",
                  record_pass=False)
        elif (~nb).any():
            f.add(table, col, G, "blank values", "Completeness", "WARN", (~nb).sum(), n,
                  record_pass=False)

        # Null-like tokens that default parsers turn into NaN
        tok = st.str.lower().isin(ws.NULL_LIKE_TOKENS)
        f.add(table, col, G, "null-like token stored as text", "Validity", "INFO", tok.sum(), n,
              _examples(s[tok]), "a default parser may read this as missing (pandas turns 'None', "
              "'NULL', 'NaN', 'N/A' into NaN); decide whether it is a value or a gap",
              record_pass=False)

        # Whitespace
        wsp = nb & ((s != st) | s.str.contains(r"\s{2,}", regex=True))
        f.add(table, col, G, "leading/trailing or double whitespace", "Consistency", "WARN",
              wsp.sum(), n, _examples(s[wsp]), record_pass=False)

        # Leading zeros / numeric-looking codes held as text
        if spec.get("type") == "text" and st[nb].str.fullmatch(r"\d+").any():
            lz = nb & st.str.fullmatch(r"0\d+")
            numeric_like = nb & st.str.fullmatch(r"\d+")
            f.add(table, col, G, "numeric-looking code that must stay text", "Validity", "INFO",
                  lz.sum() if lz.any() else numeric_like.sum(), n,
                  _examples(s[lz] if lz.any() else s[numeric_like]),
                  "Leading zeros / codes are lost if a tool types this column as a number",
                  record_pass=False)

        if not spec:
            continue
        typed_ok = nb & ws.valid_type_mask(s, spec["type"])

        # Allowed values
        if "allowed" in spec:
            bad = typed_ok & ~st.isin(spec["allowed"])
            f.add(table, col, G, "value not in allowed list", "Validity / Consistency", "ERROR",
                  bad.sum(), n, _examples(s[bad]),
                  "Values found: " + ", ".join(f"{k} {v}" for k, v in s[bad].value_counts().items())
                  + f". Allowed: {', '.join(map(str, spec['allowed']))[:100]}")

        # Pattern
        if "pattern" in spec:
            bad = typed_ok & ~st.str.fullmatch(spec["pattern"])
            f.add(table, col, G, f"value does not match pattern {spec['pattern']}", "Validity",
                  "ERROR", bad.sum(), n, _examples(s[bad]))

        # Range
        if ("min" in spec or "max" in spec) and spec["type"] in ("int", "float", "date"):
            v = ws.to_date(st) if spec["type"] == "date" else ws.to_num(st)
            lo = pd.Timestamp(spec["min"]) if spec["type"] == "date" and "min" in spec else spec.get("min")
            hi = pd.Timestamp(spec["max"]) if spec["type"] == "date" and "max" in spec else spec.get("max")
            out = pd.Series(False, index=df.index)
            if lo is not None:
                out |= typed_ok & (v < lo)
            if hi is not None:
                out |= typed_ok & (v > hi)
            f.add(table, col, G, f"value outside range [{spec.get('min', '')}, {spec.get('max', '')}]",
                  "Accuracy/Plausibility", "ERROR", out.sum(), n, _examples(s[out]))

    # Key uniqueness (keys normalised like the RI check, so 45 and 45.0 collide;
    # blank keys are counted by the completeness check, not here)
    key = pk or (infer_key(df) if not schema else None)
    if key:
        k = ws.norm_key(df[key])
        dup = (k != "") & k.duplicated(keep=False)
        f.add(table, key, G, "primary key is not unique (rows sharing a key value)" if pk else
              f"candidate key '{key}' is not unique", "Uniqueness", "ERROR", dup.sum(), n,
              _examples(df.loc[dup, key]))


# ---------------------------------------------------------------------------
# Group 2 - single-table rules
# ---------------------------------------------------------------------------

def single_table_checks(df, table, schema, f):
    n = len(df)
    G = "2 Single-table rules"
    pk = (schema or {}).get("pk") or (None if schema else infer_key(df))
    non_key = [c for c in df.columns if c != pk]

    exact = df.duplicated(subset=non_key, keep="first")
    f.add(table, "(all columns)", G, "exact duplicate rows (ignoring the id)", "Uniqueness",
          "ERROR", exact.sum(), n, _examples(df.loc[exact, pk]) if pk else "")

    nd_keys = (schema or {}).get("near_dup_keys")
    if nd_keys:
        near = df.duplicated(subset=nd_keys, keep="first") & ~exact
        detail = f"Same values in {', '.join(nd_keys)} under a different id"
        ex = ""
        if near.any() and pk:
            k = df.loc[near, nd_keys].iloc[0]
            match = (df[nd_keys] == k).all(axis=1)
            ex = " vs ".join(f"{pk}={r[pk]}" + (f" ({r['last_name']})" if "last_name" in df else "")
                             for _, r in df[match].iterrows())
        if near.any() and table == "dim_client" and FACT_TABLES:
            copies = set(df.loc[near, pk])
            originals = set(df.loc[df.duplicated(subset=nd_keys, keep=False) & ~near, pk])
            detail += "; fact rows on copies / originals: " + ", ".join(
                f"{t} {int(FACT_TABLES[t]['client_id'].isin(copies).sum())}/"
                f"{int(FACT_TABLES[t]['client_id'].isin(originals).sum())}" for t in FACT_TABLES)
            grp = df[df.duplicated(subset=nd_keys, keep=False)].groupby(nd_keys)
            differ = [c for c in df.columns if c not in nd_keys + [pk] and (grp[c].nunique() > 1).any()]
            detail += f"; columns that differ inside the pairs: {', '.join(differ) or 'none'}"
        f.add(table, "(" + "+".join(nd_keys[:3]) + ("+..." if len(nd_keys) > 3 else "") + ")", G,
              "near-duplicate records (same entity / same grain)",
              "Uniqueness", "ERROR", near.sum(), n, ex, detail)

    if not schema:          # generic mode: business rules belong to the Wildcat schema only
        return
    for (t, rule, dim, sev, func, applies) in ws.ROW_RULES:
        if t != table:
            continue
        scope = applies(df).fillna(False).astype(bool) if applies else pd.Series(True, index=df.index)
        bad = func(df).fillna(False).astype(bool) & scope     # a failure outside the rule's scope is not counted
        f.add(table, "(row rule)", G, rule, dim, sev, bad.sum(), int(scope.sum()),
              _examples(df.loc[bad, pk]) if pk else "",
              f"rule applies to {int(scope.sum()):,} rows; examples are {pk} values; " + _evidence(df, bad))


# ---------------------------------------------------------------------------
# Groups 3 and 4 - across tables
# ---------------------------------------------------------------------------

def referential_checks(tables, f, ri_rows):
    G = "3 Referential integrity"
    for child, ckey, parent, pkey in ws.RELATIONSHIPS:
        r = check_referential_integrity(tables[child], ckey, tables[parent], pkey)
        ri_rows.append({"child": f"{child}.{ckey}", "parent": f"{parent}.{pkey}",
                        **{k: v for k, v in r.items() if k != "orphan_rows"}})
        detail = f"{r['distinct_orphan_keys']} distinct orphan keys; match rate {r['match_rate']:.4%}"
        o = r["orphan_rows"]
        if len(o):
            pkc = ws.SCHEMA[child]["pk"]
            detail += f"; orphan {ckey} range {_range_text(o[ckey])}; {pkc} range {_range_text(o[pkc])}"
            ids = ws.to_num(o[pkc])
            if ids.notna().all():
                detail += " (contiguous)" if ids.max() - ids.min() + 1 == len(o) else " (not contiguous)"
            if "amount" in o.columns:
                detail += f"; amount total {ws.to_num(o['amount']).sum():,.2f}"
            others = [t for (t, c, p, _) in ws.RELATIONSHIPS if p == parent and c == pkey and t != child]
            found = {t: int(ws.norm_key(o[ckey]).isin(set(ws.norm_key(tables[t][ckey]))).sum()) for t in others}
            detail += "; orphan keys found in other tables: " + ", ".join(f"{t} {v}" for t, v in found.items())
            if "txn_type" in o.columns:
                detail += "; " + _evidence(o, pd.Series(True, index=o.index))
        f.add(child, ckey, G, f"orphan foreign key -> {parent}.{pkey}", "Referential Integrity",
              "ERROR", r["orphan_row_count"], r["rows"],
              ", ".join(r["orphan_key_sample"][:5]), detail)
        spec = ws.SCHEMA[child]["columns"][ckey]
        req = ws.required_mask(tables[child], spec)
        null_req = ((ws.norm_key(tables[child][ckey]) == "") & req).sum()   # same null definition as the RI check
        f.add(child, ckey, G, f"null foreign key where a {parent} link is required",
              "Referential Integrity / Completeness", "ERROR", null_req, r["rows"])
        f.add(parent, pkey, G, f"parent key unique for join from {child}.{ckey}", "Uniqueness",
              "ERROR", r["dim_key_duplicates"], len(tables[parent]), record_pass=False)


def cross_table_checks(tables, f):
    G = "4 Cross-table rules"
    for (table, rule, dim, sev, func, applies) in ws.CROSS_RULES:
        df = tables[table]
        scope = applies(tables).fillna(False).astype(bool) if applies else pd.Series(True, index=df.index)
        bad = func(tables).fillna(False).astype(bool) & scope
        pk = ws.SCHEMA[table]["pk"]
        f.add(table, "(cross-table rule)", G, rule, dim, sev, bad.sum(), int(scope.sum()),
              _examples(df.loc[bad, pk]),
              f"rule applies to {int(scope.sum()):,} rows; examples are {pk} values; " + _evidence(df, bad))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def audit(folder, stage):
    tables = ws.load_tables(folder)
    FACT_TABLES.update({k: v for k, v in tables.items() if k.startswith("fact_")})
    profiles, f, ri_rows = [], Findings(), []

    for name in ws.TABLE_ORDER:
        df, schema = tables[name], ws.SCHEMA[name]
        print(f"Profiling {name:25s} {df.shape[0]:>8,} rows x {df.shape[1]} cols")
        if len(df) != schema["rows"] and stage == "raw":
            print(f"  NOTE: expected {schema['rows']:,} rows from the data inventory")
        prof = profile_table(df, name, schema)
        profiles.append(prof)
        column_checks(df, name, schema, prof, f)
        single_table_checks(df, name, schema, f)

    print("Checking referential integrity (13 relationships) and cross-table rules ...")
    referential_checks(tables, f, ri_rows)
    cross_table_checks(tables, f)

    ws.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    profile_df = pd.concat(profiles, ignore_index=True)
    findings = f.frame()
    profile_path = ws.REPORTS_DIR / f"profile_{stage}.csv"
    summary_path = ws.REPORTS_DIR / f"dq_summary_{stage}.csv"
    profile_df.to_csv(profile_path, index=False, lineterminator="\n")
    findings.to_csv(summary_path, index=False, lineterminator="\n")

    print(f"\nSaved {profile_path.relative_to(ws.HW_DIR)} ({len(profile_df)} column profiles)")
    print(f"Saved {summary_path.relative_to(ws.HW_DIR)} ({len(findings)} findings)")
    fails = findings[findings["status"] == "FAIL"]
    print(f"\nChecks run: {len(findings)} | failed: {len(fails)} | passed: {len(findings) - len(fails)}")
    print("Failed checks by severity:", fails["severity"].value_counts().to_dict())
    print("Checks by group (pass+fail):", findings["check_group"].value_counts().sort_index().to_dict())
    print("\nERROR and WARN findings:")
    show = fails[fails["severity"] != "INFO"]
    for _, r in show.iterrows():
        print(f"  {r['finding_id']} {r['severity']:5s} {r['table']}.{r['column']}: {r['check']} "
              f"-> {r['rows_affected']:,} rows ({r['pct_of_rows']}%)")
        if r["example"]:
            print(f"        e.g. {r['example']}")
        if r["detail"] and r["detail"] != "checked - no violations":
            print(f"        {r['detail']}")
    print("\nINFO findings (legitimate structure or worth knowing):")
    for _, r in fails[fails["severity"] == "INFO"].iterrows():
        print(f"  {r['finding_id']} {r['table']}.{r['column']}: {r['check']} -> {r['rows_affected']:,} rows")
    return profile_df, findings


def profile_any_csv(path):
    """Generic mode: profile a single CSV that is not part of the Wildcat schema."""
    df = ws.read_table(path)
    prof = profile_table(df, Path(path).stem)
    f = Findings()
    column_checks(df, Path(path).stem, None, prof, f)
    single_table_checks(df, Path(path).stem, None, f)
    pd.set_option("display.width", 200)
    print(prof.drop(columns=["top_values"]).to_string(index=False))
    print(f.frame().to_string(index=False) if f.rows else "No generic findings.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        profile_any_csv(sys.argv[1])
    else:
        audit(ws.RAW_DIR, "raw")
