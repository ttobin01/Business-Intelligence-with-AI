# HW3 Validation: SEC 8-K Pipelines

**Author:** Tyler Tobin | **Course:** MIS3060 | **Run date:** 2026-09-30
**Scripts validated:** `hw03/hw03_earnings.py`, `hw03/hw03_executives.py`, `hw03/hw03_timeline.py`

> **How the pipelines were run.** Both SEC pipelines were run live against EDGAR (`data.sec.gov` and `www.sec.gov`) on 2026-09-30. They ran as unmodified Python, in a Python runtime inside a browser on this computer, because the terminal sandbox had no route to sec.gov. Each request carried the User-Agent `MIS3060 Villanova ttobin01@villanova.edu` on every request. I logged every HTTP call across all runs (251 in total), and every one carried that header. After each run, I checked that the script executed was byte-for-byte identical to the committed file by comparing SHA-256 hashes.
>
> Current hashes: `hw03_earnings.py` = `25a4c7ca…`, `hw03_executives.py` = `a35c7edb…`, `hw03_timeline.py` = `f43b0537…`.
>
> `hw03_timeline.py` was run in the repo's own `.venv`, and its output matched a second run byte-for-byte (same MD5).
>
> **Note on re-running:** `hw03_executives.py` computes its 12-month window from *today's* date, so re-running it on a later day can change the event count. For example, from 2026-10-01 onward the MSFT 2025-09-30 filing (Carlos Rodriguez) falls outside the window. All figures in this document are from the 2026-09-30 run.

---

## 5A: Known-Answer Check (Earnings)

**Company / quarter:** Apple Inc., fiscal 2026 third quarter (ended June 27, 2026), from the 8-K filed 2026-07-30.

| Check | Official Source | Your CSV | Match? |
|---|---|---|---|
| Apple Q3 FY26 Revenue | $109.4 billion ([Apple Newsroom, "Apple reports third quarter results," Jul 30 2026](https://www.apple.com/newsroom/2026/07/apple-reports-third-quarter-results/)) | `109400` ($ millions = $109.4B) | **Yes** |
| Apple Q3 FY26 EPS Diluted | $2.02 (same Apple Newsroom release) | `2.02` | **Yes** |

Independent press coverage agrees. MacRumors reported "$29.8B Profit on $109.4B Revenue" ([MacRumors, Jul 30 2026](https://www.macrumors.com/2026/07/30/apple-3q-2026-earnings/)), which also matches our `net_income` of `29789` ($29.789B).

**Full audit beyond the one required check.** I checked every one of the 20 rows by printing the text around each extracted value from the downloaded press release.

- **Revenue, EPS and net income:** all 60 values are the current-quarter GAAP figures.
  - No row picked up a prior-year comparison, an adjusted (non-GAAP) figure or a segment figure.
  - JPMorgan's rows use *reported* revenue, not *managed* revenue.
  - Walmart's rows use net income *attributable to Walmart*.
- **Period:** 2 of 20 rows were wrong on the first run. This is the one regex iteration on the earnings pipeline:

| Filing | Period extracted (first run) | Cause | Fix | Period after fix |
|---|---|---|---|---|
| AAPL 2025-10-30 | `fourth quarter of 2024` | The first pattern in the list matched a footnote about a prior-year tax charge before the pattern for Apple's own wording "fiscal 2025 fourth quarter" was tried. | Among the named-quarter patterns, take the match that appears **earliest in the text** (the headline or first paragraph) instead of the first pattern that matches anywhere. | `fiscal 2025 fourth quarter` ✓ |
| NVDA 2026-02-25 | `first quarter of fiscal 2027` | NVIDIA's year-end headline says "Fourth Quarter and Fiscal 2026", which no pattern covered, so the Outlook section ("Beginning in the first quarter of fiscal 2027…") matched instead. | Added the pattern `{ordinal} quarter and fiscal {year}`. | `Fourth Quarter and Fiscal 2026` ✓ |

- Before (single pattern list, first match wins): `rf"\b{ordinal}[\s-]quarter(?:\s+of)?\s+(?:fiscal\s+(?:year\s+)?)?(?:19|20)\d{{2}}\b"` was tried first, then the fiscal-year-first pattern, and so on.
- After ("tier 1" patterns, earliest position wins): the same patterns plus `rf"\b{ordinal}[\s-]quarter\s+and\s+fiscal\s+(?:year\s+)?(?:19|20)\d{{2}}\b"`, with the result chosen by `min(hits, key=lambda m: m.start())`.
- The fix resolved both rows. The other 18 periods did not change, and no revenue, EPS or net income value changed.

---

## 5B: Known-Answer Check (Executive Events)

**Event checked:** `NVIDIA Corporation, NVDA, 2026-04-27, appointment, Scott Gawel, VP and CAO, 2026-05-04`

| Check | News Source Confirms? | Notes |
|---|---|---|
| Person name and title | **Yes** | StreetInsider (Apr 27 2026): Scott Gawel "was appointed as vice president and chief accounting officer" ([link](https://www.streetinsider.com/Corporate+News/NVIDIA+names+former+Intel+executive+as+chief+accounting+officer/26374874.html)). Our title `VP and CAO` is the filing's own abbreviation of that title. |
| Event type (departure/appointment) | **Yes** | An appointment. Shacknews (Apr 28 2026) confirms he replaces Donald Robertson, who is retiring ([link](https://www.shacknews.com/article/148884/nvidia-nvda-chief-accounting-officer-donald-robertson-retires)). Our CSV has the matching `departure` row for Robertson from the same filing, which shows the "one filing, two events → two rows" edge case. |
| Effective date | **Yes** | Both sources give May 4, 2026 ("Gawel will fill the position starting on the same day"), which matches our `2026-05-04`. |

**Full audit beyond the one required check.** I read the Item 5.02 text of all 19 in-window filings and compared it with the CSV.

- **Events found:** all 30 rows are real events described in the filings. The 3 filings with no event row are compensation-only (MSFT 2025-12-08 stock plan, NVDA 2026-03-06 variable pay plan, JPM 2026-01-22 CEO pay), and the script correctly printed the "compensation-only 5.02" message for each.
- **Iteration:** the first run of the generated script found 26 rows. Checking them against the filings led to the fixes below (logged in `ai_usage_log.md`), which brought the final count to 30 rows:
  - Tim Cook's CEO → Executive Chair transition was missed, because the verb list had no "transition."
  - Chris Kondo, Kate Adams and David Chojnowski were missed. They are named only as the person being succeeded, or as the one whose duties "transition from" them.
  - Suzanne Nora Johnson appeared twice ("Ms. Nora Johnson" was read as a second person).
  - Some effective dates were missed because they were written as a defined term ("effective on the Transition Date") or as "will become … on March 1, 2026".
  - A second iteration removed a spurious Ajay Puri "appointment" that came from "a seamless transition to his successor."
- **Known remaining limitations (not errors in event detection):**
  - 8 `effective_date` values are `NOT_FOUND`. In every case the filing gives no calendar date: "effective immediately", "until the Annual Meeting", "upon the commencement of his successor's employment" or "late 2026".
  - A few titles are shortened when the appositive has commas, e.g. Ajay Puri shows `Executive Vice President` instead of "Executive Vice President, Worldwide Field Operations".
  - Chris Kondo's and John Furner's effective dates, and Kondo's title, are inferred from their successor, because the successor takes over the same role on the same day. Furner's title is inferred the same way.

---

## 5C: Cross-Validation (Earnings via Yahoo Finance)

**Prompt:** *"Write Python using yfinance to get the most recent quarterly revenue and net income for AAPL."* This produced `hw03/crossval_yfinance.py`, which reads `yf.Ticker("AAPL").quarterly_income_stmt` and prints the latest quarter's *Total Revenue* and *Net Income*.

**Run locally on 2026-09-30** (Windows, Python 3.14, yfinance 1.7.0) with `python hw03/crossval_yfinance.py`. Output:

```
AAPL most recent quarter (Yahoo period end 2026-06-30):
  Total Revenue: $109,417M
  Net Income:    $29,789M
```

| Metric | From 8-K text extraction | From yfinance (Yahoo, quarter labeled 2026-06-30) | Match? |
|---|---|---|---|
| Revenue | $109,400M (from the prose "quarterly revenue of $109.4 billion") | $109,417M | **Within rounding.** Differs by $17M (0.016%). |
| Net Income | $29,789M | $29,789M | **Yes, exact.** |

**Why revenue differs:** this is a precision difference in the metric's definition, not an extraction error. The pipeline takes revenue from the headline sentence, which Apple rounds to one decimal place in billions ($109.4B). Yahoo uses the exact figure from the financial statements, where "Total net sales" is $109,417M in the release's own table. Net income matches exactly because, for Apple, our script reads it from that same statement table. Yahoo also labels Apple's quarter as ending 2026-06-30 instead of Apple's actual fiscal quarter end of June 27, 2026. This is a period-labeling convention, not a different quarter, as the net income match confirms.

---

## 5D: Pipeline Integrity Checks

| Check | Expected | Actual | Pass/Fail |
|---|---|---|---|
| `earnings_history.csv` row count | Up to 20 (5 companies × 4 quarters) | 20 (4 per company) | **Pass** |
| `executive_events.csv` row count | At least 0 (document actual) | 30 events from 16 filings (19 Item 5.02 8-Ks in window; 3 compensation-only produced no rows). Breakdown: 16 appointment, 12 departure, 2 both | **Pass** |
| `corporate_events_timeline.csv` created | Yes | Yes. 30 rows, 15 columns, 0 rows with "no earnings match" | **Pass** |
| Rows with all three fields `"NOT_FOUND"` | 0 (investigate if > 0) | 0. No earnings field is `NOT_FOUND` at all. | **Pass** |

**Additional checks run**

- **Earnings pipeline:**
  - Every `requests.get()` call goes through a helper that passes the header dict and a timeout.
  - A deliberately bad accession number printed `WARNING: AAPL filing …: request failed … — skipping` and returned no row, without crashing.
  - A text with no figures returned `NOT_FOUND` for all four fields.
- **Executive events pipeline:**
  - Zero-event edge case: with a cutoff date in the future, `process_company` printed `AAPL: No executive events in past 12 months` and returned `[]`.
  - A missing document printed a warning and the script continued.
  - With no events, the CSV is still written with its header row.
- **Both-events-in-one-filing edge case:** passed on live data. For example, NVDA 2026-04-27 (Robertson departure + Gawel appointment) and WMT 2025-11-14 (McMillon departure + Furner appointment) each produced two rows.
- **Timeline:**
  - All 30 values of `days_to_nearest_earnings`, `earnings_filing_date` and `event_timing` were recomputed with plain Python datetime arithmetic, independently of pandas. There were **0 mismatches**.
  - With a header-only `executive_events.csv`, the script wrote an empty timeline and printed all-zero counts, without crashing.
