"""
hw03_timeline.py

Builds a timeline linking each executive event (8-K filings) to the nearest
earnings filing for the same company.

Inputs  (in the hw03/ folder):
    earnings_history.csv   - company, ticker, cik, filing_date, period,
                             revenue_reported, eps_diluted, net_income
    executive_events.csv   - company, ticker, cik, filing_date, event_type,
                             person_name, title, effective_date
Output:
    corporate_events_timeline.csv

Run from the repo root:  python hw03/hw03_timeline.py

Design choices (see also comments below):
  * One output row per executive event (events are the unit of analysis).
    The nearest earnings filing's columns are attached to that row.
  * company / ticker / cik appear once (they are the join keys and match by
    construction). filing_date exists in both tables with different meanings,
    so it is kept twice: event_filing_date and earnings_filing_date.
  * days_to_nearest_earnings = absolute number of calendar days between the
    event filing date and the nearest earnings filing date.
  * event_timing precedence: 'same week' (|days| <= 7) wins; otherwise
    'before earnings' / 'after earnings' based on direction.
  * Values such as "NOT_FOUND" are written back out exactly as they came in.
"""

from pathlib import Path
import sys

import pandas as pd

# Resolve paths relative to this script so it works from the repo root
# (python hw03/hw03_timeline.py) or from inside hw03/.
HW_DIR = Path(__file__).resolve().parent
EARNINGS_CSV = HW_DIR / "earnings_history.csv"
EVENTS_CSV = HW_DIR / "executive_events.csv"
OUTPUT_CSV = HW_DIR / "corporate_events_timeline.csv"

SAME_WEEK_DAYS = 7
MISSING_TOKENS = {"", "NOT_FOUND", "NAN", "NONE", "N/A", "NA"}

EARNINGS_COLS = ["company", "ticker", "cik", "filing_date", "period",
                 "revenue_reported", "eps_diluted", "net_income"]
EVENT_COLS = ["company", "ticker", "cik", "filing_date", "event_type",
              "person_name", "title", "effective_date"]


def read_csv_as_text(path, expected_cols):
    """Read every column as text so values like NOT_FOUND or leading-zero
    CIKs are preserved exactly. Works even if the file has only a header."""
    if not path.exists():
        sys.exit(f"ERROR: input file not found: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in expected_cols if c not in df.columns]
    if missing:
        sys.exit(f"ERROR: {path.name} is missing columns: {missing}")
    return df


def parse_date(series):
    """Convert text dates to datetimes; NOT_FOUND / blanks / junk -> NaT."""
    cleaned = series.astype(str).str.strip()
    cleaned = cleaned.where(~cleaned.str.upper().isin(MISSING_TOKENS))
    return pd.to_datetime(cleaned, errors="coerce", format="mixed")


def company_key(df):
    """Key used to decide 'same company'. CIK is the most reliable identifier
    (leading zeros stripped so 0000320193 == 320193); fall back to the
    upper-cased ticker if the CIK is missing."""
    cik = df["cik"].astype(str).str.strip().str.lstrip("0")
    cik_ok = cik.str.isdigit()
    ticker = df["ticker"].astype(str).str.strip().str.upper()
    return ("CIK:" + cik).where(cik_ok, "TICKER:" + ticker)


def main():
    earnings = read_csv_as_text(EARNINGS_CSV, EARNINGS_COLS)
    events = read_csv_as_text(EVENTS_CSV, EVENT_COLS)

    earnings["_key"] = company_key(earnings)
    earnings["_date"] = parse_date(earnings["filing_date"])
    events["_key"] = company_key(events)
    events["_date"] = parse_date(events["filing_date"])

    # Only earnings rows with a usable filing date can be "nearest".
    valid_earnings = earnings.dropna(subset=["_date"])

    # ---- Steps 1 & 2: nearest earnings filing + timing category ----------
    matched_rows = []   # index into `earnings` for each event (or None)
    days_list = []
    timing_list = []
    signed_list = []    # [Adjustment] signed gap, so 'same week' events still show a direction

    for _, ev in events.iterrows():
        candidates = valid_earnings[valid_earnings["_key"] == ev["_key"]]
        if pd.isna(ev["_date"]) or candidates.empty:
            matched_rows.append(None)
            signed_list.append(None)
            days_list.append(pd.NA)
            timing_list.append("no earnings match")
            continue

        # Signed difference: negative = event before earnings filing.
        signed = (ev["_date"] - candidates["_date"]).dt.days
        # Nearest = smallest absolute gap. Tie-break (event exactly halfway
        # between two filings): prefer the EARLIER earnings filing, so the
        # choice is deterministic.
        order = pd.DataFrame({"abs": signed.abs(),
                              "date": candidates["_date"]}).sort_values(
            ["abs", "date"])
        best_idx = order.index[0]
        diff = int(signed.loc[best_idx])

        matched_rows.append(best_idx)
        signed_list.append(diff)
        days_list.append(abs(diff))
        if abs(diff) <= SAME_WEEK_DAYS:
            timing_list.append("same week")
        elif diff < 0:
            timing_list.append("before earnings")
        else:
            timing_list.append("after earnings")

    # ---- Step 3: build the combined table --------------------------------
    out = events[EVENT_COLS].copy().reset_index(drop=True)
    out = out.rename(columns={"filing_date": "event_filing_date"})

    earnings_part_cols = ["filing_date", "period", "revenue_reported",
                          "eps_diluted", "net_income"]
    earn_part = pd.DataFrame(
        [earnings.loc[i, earnings_part_cols].to_dict() if i is not None
         else {c: "" for c in earnings_part_cols} for i in matched_rows],
        columns=earnings_part_cols,
    ).rename(columns={"filing_date": "earnings_filing_date"})

    out = pd.concat([out, earn_part], axis=1)
    out["days_to_nearest_earnings"] = pd.Series(days_list, dtype="Int64")
    out["event_timing"] = timing_list

    final_cols = ["company", "ticker", "cik",
                  "event_filing_date", "event_type", "person_name", "title",
                  "effective_date",
                  "earnings_filing_date", "period", "revenue_reported",
                  "eps_diluted", "net_income",
                  "days_to_nearest_earnings", "event_timing"]
    out = out[final_cols]
    out.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved {len(out)} row(s) to {OUTPUT_CSV}\n")

    # ---- Step 4: per-company summary -------------------------------------
    # Companies come from BOTH tables so a company with no events still shows.
    names = {}
    for df in (earnings, events):
        for _, r in df.iterrows():
            names.setdefault(r["_key"], (r["company"], r["ticker"]))
    out["_key"] = events["_key"].values if len(events) else []
    out["_signed"] = signed_list

    print("=" * 70)
    print("EXECUTIVE EVENTS BY COMPANY")
    print("=" * 70)
    for key, (company, ticker) in sorted(names.items(),
                                         key=lambda kv: kv[1][0].upper()):
        print(f"\n{company} ({ticker})")
        rows = out[out["_key"] == key]
        if rows.empty:
            print("  No executive events found.")
            continue
        for _, r in rows.sort_values("event_filing_date").iterrows():
            who = r["person_name"] or "(name not given)"
            title = f", {r['title']}" if r["title"] else ""
            desc = f"{r['event_type'] or 'event'}: {who}{title}"
            if r["event_timing"] == "no earnings match":
                where = ("event filing date missing/unreadable"
                         if pd.isna(parse_date(pd.Series([r["event_filing_date"]]))[0])
                         else "no earnings filing to compare against")
            else:
                # [Adjustment] always say before/after, even for 'same week' events.
                direction = "before" if r["_signed"] < 0 else ("after" if r["_signed"] > 0 else "same day as")
                where = (f"{r['event_timing']} "
                         f"({r['days_to_nearest_earnings']} days {direction} the "
                         f"{r['earnings_filing_date']} earnings filing)")
            print(f"  - {r['event_filing_date']}  {desc}  ->  {where}")

    # ---- Step 5: final counts --------------------------------------------
    counts = out["event_timing"].value_counts()
    n_before = int(counts.get("before earnings", 0))
    n_after = int(counts.get("after earnings", 0))
    n_same = int(counts.get("same week", 0))
    n_none = int(counts.get("no earnings match", 0))

    print("\n" + "=" * 70)
    print(f"FINAL COUNT (all {len(names)} companies, {len(out)} events)")
    print("=" * 70)
    print(f"  Before earnings : {n_before}")
    print(f"  After earnings  : {n_after}")
    print(f"  Same week (within {SAME_WEEK_DAYS} days, counted separately): "
          f"{n_same}")
    if n_same:
        same = out[out["event_timing"] == "same week"]["_signed"]
        print(f"      of which filed before earnings: {int((same < 0).sum())}, "
              f"after earnings: {int((same > 0).sum())}, same day: {int((same == 0).sum())}")
    # [Adjustment] several rows can come from one 8-K, so also count distinct filings.
    if len(out):
        filings = out.drop_duplicates(["_key", "event_filing_date"])
        fc = filings["event_timing"].value_counts()
        print(f"  Distinct 8-K filings: {len(filings)} "
              f"(before: {int(fc.get('before earnings', 0))}, "
              f"after: {int(fc.get('after earnings', 0))}, "
              f"same week: {int(fc.get('same week', 0))})")
    if n_none:
        print(f"  No earnings match: {n_none}")
    if len(out) == 0:
        print("  (The executive events file has no events, so all counts "
              "are zero.)")


if __name__ == "__main__":
    main()
