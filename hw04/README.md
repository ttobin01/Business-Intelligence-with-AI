# HW4: Cleaning the Wildcat Capital Data

**Tyler Tobin** | MIS3060 Business Intelligence with AI | Villanova University

This folder audits the eight Wildcat Capital tables, cleans them without inventing data, and proves that the cleaning worked. The deliverables are:

- a clean copy of all eight tables;
- a full audit trail;
- a raw-vs-clean data-quality scorecard;
- a report for the portfolio committee.

## Folder structure

```
hw04/
├── README.md                      this file
├── decision_log.md                Part B - one entry per issue (written before the cleaning code)
├── scripts/
│   ├── wildcat_schema.py          shared declarations: keys, types, allowed values, ranges,
│   │                              13 relationships, row and cross-table rules
│   ├── 01_profile.py              Part A - generic profiler + 4 groups of audit checks
│   ├── 02_clean.py                Part C - cleaning program (raw -> clean + quarantine + audit trail)
│   └── 03_validate.py             Part D - check_referential_integrity(), rule checks,
│                                  reconciliations, IQR flags, scorecard
├── data/
│   ├── raw/                       the 8 source CSVs (not committed; see "How to run")
│   ├── clean/                     8 clean CSVs + README_clean.md
│   └── audit/                     cleaning_log.csv, value_changes.csv, quarantine_*.csv
└── reports/
    ├── profile_raw.csv            one row per table x column (Part A)
    ├── dq_summary_raw.csv         every check, PASS/FAIL, tagged ERROR/WARN/INFO (Part A)
    ├── data_quality_scorecard.csv one row per table per stage, raw vs clean (Part D)
    ├── validation_details.csv     every check behind the scorecard (Part D)
    └── cleaning_report.md         1-2 page report for the portfolio committee (Part E)
```

`wildcat_schema.py` holds the business rules (declarations only) so that the audit, the cleaning checks and the scorecard all test the *same* definitions. The profiler engine itself is generic: `python hw04/scripts/01_profile.py any_file.csv` profiles any CSV with inferred types.

## How to run

Requires Python 3.10+ with `pandas` (2.x or 3.x) and `numpy`.

1. Copy the eight Wildcat Capital CSVs into `hw04/data/raw/`. They are excluded from git as raw data, and the scripts never modify them.
2. From the repository root, run the three scripts in order:

```bash
python hw04/scripts/01_profile.py    # ~1 min  -> reports/profile_raw.csv, reports/dq_summary_raw.csv
python hw04/scripts/02_clean.py      # ~25 s   -> data/clean/, data/audit/
python hw04/scripts/03_validate.py   # ~1 min  -> reports/data_quality_scorecard.csv, validation_details.csv
```

Every file is read as text (`dtype=str`, `keep_default_na=False`), and each column is converted on purpose.

`02_clean.py` stops with an `AssertionError` if any step does not do what the decision log says, including any count that differs from the documented one. It finishes by proving three things:

- clean keys + quarantined keys = raw keys for every table;
- quarantined rows are unchanged from raw;
- every changed cell is listed in `value_changes.csv`.

The full pipeline was run on pandas 3.0.2 (Python 3.11) and pandas 2.3.3 (Python 3.11 and 3.10), and every output file is byte-identical across all three runs. Files are written with `\n` line endings, so they match across Windows and macOS.

## Results at a glance

| | Raw | Clean |
|---|---:|---:|
| `dim_client` rows | 2,525 | 2,500 (25 duplicates quarantined) |
| `fact_transactions` rows | 298,772 | 298,572 (200 orphans quarantined) |
| Cells corrected (logged in `value_changes.csv`) | — | 198,256 |
| Flag columns added | — | 5 |
| `fact_transactions` type validity | 91.73% | 100% |
| `fact_transactions` referential match | 99.982% | 100% |
| `dim_client` key uniqueness | 99.01% | 100% |

See `reports/cleaning_report.md` for the business summary and `data/clean/README_clean.md` for how to load the clean tables in a BI tool.

## Code review findings and what I did about them

The scripts were reviewed in two rounds:

1. **Round 1 — separate Claude sessions** that had not written the code, using the course's review prompts (tables below the Claude Code section).
2. **Round 2 — Claude Code in VS Code.** I opened the repository in VS Code and gave the Claude Code extension one review prompt per script. It read the code and confirmed each suspicion on the real data or a small test case. Its findings, and what I did about each, are in the first set of tables below.

The prompts asked about:

- null handling;
- checks applied in the wrong direction;
- silent failures and unmapped values;
- whether every step has a before/after check;
- edge cases;
- pandas 2 vs 3 compatibility.

Every finding below was resolved (fixed, or kept on purpose with a reason) before the final run.

### Round 2: Claude Code (VS Code) review

**Prompts used:**

- **`01_profile.py` + `wildcat_schema.py`:** does either mis-handle nulls or apply a check in the wrong direction; could a check silently produce a wrong count; is the profiler generic; which edge cases would you test?
- **`02_clean.py` vs `decision_log.md`:** does every step have a before/after validation print; could any mapping or merge silently produce a wrong value; does any step silently change the row count?
- **`03_validate.py`:** do `check_referential_integrity` or `iqr_flags` mis-handle nulls or check in the wrong direction; which edge cases would you test?

**What Claude Code confirmed was already correct:**

- Range checks are in the right direction.
- No mapping or merge can silently write a wrong value; every lookup raises on a miss.
- No step can silently change the row count.
- String replacements go the right way (`\.0+$`, `lstrip("-")`).
- NaN comparisons fail safe.
- The RI direction (child → parent) and the IQR fence direction are correct.

After the fixes, the full pipeline was re-run.

- `profile_raw.csv`, every clean table and every audit file are byte-identical to the previous run.
- The only output changes come from finding P2: one new audit finding (F003), so the later finding IDs moved up by one (`decision_log.md` was renumbered to match), and `dim_client`'s raw rule-pass score moved from 99.742% to 99.663%.

#### `01_profile.py` and `wildcat_schema.py`

| # | Claude Code flagged | What I did |
|---|---|---|
| P1 | In generic mode the key-uniqueness check could never fail: `infer_key` only picked a column that was already unique, so a duplicated id made the check disappear. | **Fixed.** A column named `id`/`*_id` is always the candidate key, so duplicates now FAIL (tested: `client_id = 1,1,2` → FAIL, 2 rows). |
| P2 | The `is_active` cross-table rule skipped clients with no snapshot. 24 of the 25 duplicate clients say `is_active=True` with no snapshot, and the rule scored them as passing. | **Fixed.** No snapshot + `True` is now a violation. The raw audit now reports F003 (24 rows, ERROR). These are the same records as the duplicate defect, so no cleaning step changed. The decision log (issues 1, 9, 22) and the report were updated. |
| P3 | `_lookup`, `_snapshot_aum_by_month` and `_billed_fee` kept the *first* row when a key was duplicated, so a rule could compare against an arbitrary row. | **Fixed.** A shared `_unique_lookup` drops ambiguous keys (those rows are not evaluated) and prints a warning. The data has no duplicated keys, so the counts are unchanged. |
| P4 | `to_date` accepted `2020-1-5`, which the type check rejects. An unparseable date gave a NaN month key, and `isin` matched NaN to NaN. | **Fixed.** `to_date` requires exactly `yyyy-mm-dd`. Month keys with a bad date are excluded from both fee↔snapshot rules. |
| P5 | The "null FK where required" check used `blank()`, not the RI null definition (`NULL`, `NA`, …). | **Fixed.** It uses `norm_key()`, like the RI check. |
| P6 | Row and cross-table rules did not intersect violations with the rule's scope, so a pass % could exceed 100%. | **Fixed.** `bad &= scope`. |
| P7 | "Orphan keys found in other tables" compared raw text, so `45.0` ≠ `45`. | **Fixed** (`norm_key` on both sides). |
| P8 | `astype(str)` before `blank()` would turn a real NaN into the text `"nan"` on pandas 2. | **Fixed.** Real missing values become `''` first. |
| P9 | `norm_key` treats the text `NA` as null, which is wrong for a text key such as a country code. | **Kept, documented.** Every Wildcat key is numeric or a date. This is noted in the `check_referential_integrity` docstring. |
| P10 | `_evidence` and the near-duplicate/orphan detail text name Wildcat columns; the ETF-vs-asset-class rule is a domain assumption. | **Kept.** These only enrich the detail text (counts are schema-driven) or belong to the Wildcat schema, which generic mode does not load. |

#### `02_clean.py`

| # | Claude Code flagged | What I did |
|---|---|---|
| C1 | The flag steps (7a–7e) printed only "N flagged"; the before/after proof was an assert. | **Fixed.** Each flag step now prints a Before line (rows × columns, flag absent) and an After line. |
| C2 | The trading calendar used `drop_duplicates("date")`, but only `date_id` was asserted unique. | **Fixed.** The script stops if `dim_date.date` is not unique. |
| C3 | Decision log #3 said 197,175 ids, but the code expects 197,044. | **Fixed (documentation).** 131 orphan rows carry a `security_id` and are quarantined first. This is now stated in issue #3 and in the report. |
| C4 | Decision log #2 says every name maps to a code already in the column, but nothing asserted it. | **Fixed.** Now asserted. |
| C5 | The log notes hard-coded "78 in raw" and "836 in raw". | **Fixed.** Computed from the raw tables. |
| C6 | Dedupe groups on raw text, so a copy written `PA` vs `Pennsylvania` would be missed. | **Kept.** `check_count(25)` would stop the script, so this fails loudly, not silently. |
| C7 | The $1,000 floor is an exact `==`, so `999.99` is not flagged. | **Kept on purpose, documented** in decision log #10: the placeholder is exactly 1000.0. |

#### `03_validate.py`

| # | Claude Code flagged | What I did |
|---|---|---|
| V1 | `match_rate` leaves out null keys, so a required FK that is 50% null could score 100%. | **Fixed.** A new `required=` argument (True or a row mask) counts required-row nulls as failures (`required_null_rows`). The scorecard passes each FK's required mask. Structural nulls (e.g. `security_id` on a Deposit) are still not scored. No required FK has nulls in this data. |
| V2 | `dim_key_duplicates` counts extra rows, not distinct keys, and the docstring was wrong. Blank parent keys were dropped silently. | **Fixed.** The docstring is corrected. The function also returns `dim_duplicate_key_values` and `dim_null_keys`. |
| V3 | A `datetime64` child column against a text date key made every row an orphan; a float id `1e16` became `"1e+16"`. | **Fixed.** Datetimes are compared as `yyyy-mm-dd`, and whole-number floats are written without exponent (both tested: 0 orphans). A missing column now raises `KeyError`. |
| V4 | All-null input gives `match_rate = NaN`. | **Kept on purpose** (round 1, #2). NaN means "nothing to score"; the scorecard leaves the cell blank. |
| V5 | `iqr_flags` returned 0 flags when IQR = 0, so the caller could not tell "no outliers" from "test not possible". | **Fixed.** `flags.attrs["status"]` is `ok`, `no data` or `iqr is 0`, and `run_iqr` stops if a scored column is not `ok`. |
| V6 | `iqr_flags` silently dropped text (`"1,000,000"`, `"9%"`) and accepted `k ≤ 0`. | **Fixed.** Non-numeric input raises `TypeError`, and `k ≤ 0` raises `ValueError`. |
| V7 | `045` vs `45` and `ABC` vs `abc` are reported as orphans. | **Kept, documented.** These are real key mismatches. |
| V8 | IQR fences on mixed or skewed data (`fact_transactions.amount`, AUM) are not very informative. | **Kept** (round 1, #7): the assignment asks for 1.5×IQR, and the report says "flagged ≠ wrong". |

### Round 1: separate Claude sessions

#### `01_profile.py` and `wildcat_schema.py`

| # | Flagged | What I did |
|---|---|---|
| 1 | The orphan-key detail called `.astype(int)`, so the audit would crash on a non-numeric orphan (e.g. a bad date `01/01/2020`). | **Fixed.** Ranges are printed numerically only when every key parses; otherwise as text. Re-tested with a bad date: no crash, orphan reported. |
| 2 | A duplicate date in `dim_date` crashed the weekend-trade rule (`.map` needs a unique index). | **Fixed.** The calendar lookup is de-duplicated first. Re-tested with a duplicated row: it is reported as "parent key not unique" instead of crashing. |
| 3 | The mixed-format check crashed on a column with no valid values. | **Fixed** (empty-column guard). |
| 4 | "Latest snapshot month" was the *text* maximum of the date, so one junk date would silently change a rule. | **Fixed.** Dates are parsed before taking the maximum. |
| 5 | `txn_type` was not stripped in some rules, so `'Dividend '` would skip the required-field checks. | **Fixed.** One `cat()` helper strips every category comparison. |
| 6 | The advisor cross-check compared un-normalised parent keys (`22.0` ≠ `22`). | **Fixed.** Both sides use `norm_key()`. |
| 7 | Primary-key uniqueness counted blank keys as duplicates and missed `1` vs `1.0`. | **Fixed.** Uses `norm_key()`, ignores blanks (counted by completeness) and reports rows sharing a key. |
| 8 | Some date rules counted blank inputs as violations, duplicating the completeness check. | **Fixed.** Blanks are excluded from rule violations. |
| 9 | Numeric min/max skipped values in the wrong format (e.g. all `45.0` ids gave no min/max). | **Fixed.** Min/max covers every value that parses. |
| 10 | Generic mode had limits: type inference needed 95%, there was no key check, and a file named like a Wildcat table pulled in Wildcat rules. | **Fixed.** Inference now needs ≥50%, so bad values show up as type failures. A candidate key is inferred. Business rules run only with the schema. |
| 11 | `inf` / `Infinity` counted as valid floats. | **Fixed.** Non-finite values fail the type check. |
| 12 | The Advisory Fee rule mixed two causes. | **Fixed.** Split into "no fee row" (2,297) and "different amount" (33,468). |
| 13 | The ZIP-vs-state rule fails ~90% of rows and dominated `dim_client`'s rule-pass score. | **Changed to INFO.** It describes the (synthetic) address data rather than specific bad rows. Documented in decision log #17. |
| 14 | Rule pass rates used every row as the denominator (e.g. weekend trades showed 13.6% instead of 28.4% of Buy/Sell trades). | **Fixed.** Each rule declares the rows it applies to. |
| 15 | `shares == 0` passed the "positive" rule; `[0-9]` vs `\d` behaves differently with/without pyarrow; tied `top_values` ordered differently on pandas 2 vs 3. | **Fixed** all three. |
| 16 | Null-like token list was missing pandas defaults (`#N/A`, `<NA>`, …). | **Fixed.** Tokens are reported as INFO. In keys they are treated as null, not as orphans. |
| 17 | A UTF-8 / cp1252 problem could appear with Excel-saved CSVs or redirected Windows output. | **Not changed:** the eight source files are plain ASCII/UTF-8. Noted as a limit of generic mode. |

#### `02_clean.py`

| # | Flagged | What I did |
|---|---|---|
| 1 | Bare `assert` statements disappear under `python -O`. The reviewer showed an unmapped state (`Ohio`) silently becoming blank. | **Fixed.** Every check uses `check()`, which raises even under `-O`. Re-tested: `python -O` with `Ohio` injected now stops with "state values with no mapping". |
| 2 | "raw = clean + quarantined" only compared counts, so swapped rows would pass. | **Fixed.** Now proven by key: the key sets don't overlap and together equal the raw keys. Quarantined rows must equal their raw rows. |
| 3 | "Every change is logged" only compared counts. | **Fixed.** The set of changed (key, column, old, new) cells must equal `value_changes.csv` exactly. |
| 4 | The security-id join check normalised `45.0` itself, so it would pass even if the conversion had not run. | **Fixed.** An exact text match against `dim_security` is required. |
| 5 | Some checks were true by construction (the 12-attribute duplicate test) or passed on empty masks, and documented counts were not asserted. | **Fixed.** Duplicates must differ only by a one-letter last-name truncation (Taylor/Taylo, Pace/Pacen). Each step requires a non-empty mask. Every count in the decision log is asserted (`EXPECTED`). The weekend flag is cross-checked against the weekday. |
| 6 | Windows would write CRLF line endings, so unchanged tables would differ from raw byte for byte. | **Fixed.** `lineterminator="\n"` on every output. |
| 7 | The cleaning log lacked entries for several "leave as is" decisions; the reload did not compare column headers. | **Fixed.** The log now has a "leave as is" entry for decision log #7 and #12–#21, and the reload checks the columns. |
| 8 | The orphan cross-check against other fact tables did not normalise keys. | **Fixed** (`norm_key`). |

#### `03_validate.py`

| # | Flagged | What I did |
|---|---|---|
| 1 | `check_referential_integrity` crashed on real NaN keys (pandas 3) and counted them as orphans (pandas 2). | **Fixed.** `norm_key()` turns NaN/None/null tokens into null keys. Re-tested with float, `Int64`, NaN, `' 45'`, `'045'`, `'NULL'`, empty and all-null inputs on both pandas versions. |
| 2 | An all-null relationship reported a 100% match. | **Fixed.** `match_rate` is NaN when there are no non-null keys. The scorecard leaves such cells blank. |
| 3 | `iqr_flags`: one `inf` disabled all flags; constant columns flagged any other value; the pass % used the wrong denominator. | **Fixed.** Non-finite values are ignored, IQR = 0 returns no flags, and the denominator is non-null values. Tested on all-NaN, empty, constant and `inf` inputs. |
| 4 | `% rule pass` mixed denominators. | **Fixed** (rule applicability, see `01_profile.py` #14). |
| 5 | `key_uniqueness` and the R5 advisor reconciliation did not normalise keys. | **Fixed.** |
| 6 | R4 counts unparseable `return_ytd` (the 300 `%` strings) as "not reconciled", while the row rule skips them. | **Kept on purpose:** for a reconciliation, a value that cannot be compared has not been reconciled. This is stated in the detail column. |
| 7 | All IQR lower fences are negative, so only the high tail is flagged; a log scale would be more informative. | **Kept** the standard 1.5×IQR rule the assignment asks for. **Flagged does not mean wrong:** wealth is highly skewed, so legitimate UHNW balances and large trades fall outside the fences. |

## Notes

- `data/raw/` is excluded from git (raw data stays out of the repo, per the course `.gitignore`). The clean data, audit trail and reports are committed through `.gitignore` exceptions for `hw04/data/clean/`, `hw04/data/audit/` and `hw04/reports/`.
- `value_changes.csv` is large (198,256 rows, ~10 MB) because converting `security_id` from `45.0` to `45` touches 197,044 cells, each logged individually.
