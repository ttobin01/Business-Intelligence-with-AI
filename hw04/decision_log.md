# HW4 Decision Log — Wildcat Capital Data Cleaning

**Author:** Tyler Tobin | **Course:** MIS3060 | **Written:** after the Part A audit and *before* any cleaning code
**Evidence source:** `reports/profile_raw.csv` and `reports/dq_summary_raw.csv`, produced by `scripts/01_profile.py`. Finding IDs (F0xx) refer to that summary.

This log is the prompt for the cleaning program (`scripts/02_clean.py`). Every issue the audit raised has an entry, including the ones I decided to **leave as is**. The guiding rule: fix only what can be fixed **without inventing data**. Where a value can be recomputed from other columns or confirmed in another table, I use that to verify the repair. Where it can't, I flag it or quarantine it and say so.

**Note on counts:** some issues overlap (e.g. one full state name sits on a duplicate client). Where an earlier step removes rows, the entry gives both the raw count from the audit and the count that remains for the later step. The remaining counts were confirmed when `02_clean.py` first ran; no decision changed as a result.

**Contents:** issues 1–6 repaired or quarantined · issue 7 left blank on purpose · issues 8–11 flagged (cannot be corrected without inventing data) · issues 12–23 investigated and left as is · the order of operations.

---

## A. Defects: repair, quarantine, or a deliberate decision not to impute

### 1. Duplicate client records entered under new IDs
| Field | Entry |
|---|---|
| **Table / column** | `dim_client` (whole row; key `client_id`) |
| **Evidence** | **F002:** 25 rows duplicate another client. `client_id` 2501–2525 each match an existing client (e.g. 674 *Taylor* vs 2501 *Taylo*, 889 *Pace* vs 2515 *Pacen*) on **all 12 attributes other than the id and last name**, including `initial_aum` to the cent and `client_since`. The 2501–2525 copies have **0** rows in `fact_transactions`, `fact_fees` and `fact_portfolio_snapshot`; the originals carry all the activity (2,874 transaction, 1,296 fee and 1,374 snapshot rows). Removing the copies brings the tier counts to Retail 1,510 / HNW 737 / UHNW 253 = 2,500. `client_id` itself is unique, so a plain `.duplicated()` on the key misses this. |
| **Dimension violated** | Uniqueness |
| **Decision** | **Quarantine** the 25 higher-numbered copies (2501–2525) to `data/audit/quarantine_dim_client_duplicates.csv`, recording which `client_id` each one duplicates. |
| **Justification** | A client counted twice inflates client counts, tier mix and client-level AUM (`initial_aum`). We keep the lower id because it holds all the facts and the correctly spelled name; the copy's last name is a truncation or typo of the original. Before quarantining, the script re-checks that every one of the 12 attributes matches and that the copy has zero fact rows. |
| **Risk** | If a "copy" were really a different person (e.g. a relative with the same profile), we would drop a real client. This is very unlikely given 12 identical fields, including a cent-exact AUM, and it is reversible: the rows are kept in quarantine. |

### 2. State stored as full names
| Field | Entry |
|---|---|
| **Table / column** | `dim_client.state` |
| **Evidence** | **F001:** 78 rows (3.09%) hold full names instead of USPS codes: Pennsylvania 25, Florida 15, New York 14, New Jersey 13, California 5, Illinois 4, Texas 2. One of the 78 is on a duplicate removed in issue 1, so **77 rows** remain to standardize. |
| **Dimension violated** | Consistency, Validity |
| **Decision** | **Standardize** with an explicit map (`Pennsylvania → PA`, …). The script stops if any value is not in the map or is not a valid code afterwards. |
| **Justification** | A state slicer would show "PA" and "Pennsylvania" as two states, splitting counts and AUM by geography. An explicit dictionary is deterministic, and every name present maps to a code that already exists in the column. |
| **Risk** | A misspelled or new state name would fall outside the map. The script **asserts** that no value is left unmapped, so this fails loudly instead of silently. |

### 3. `security_id` stored as decimals (`45.0`)
| Field | Entry |
|---|---|
| **Table / column** | `fact_transactions.security_id` |
| **Evidence** | **F004:** all 197,175 non-blank values are written `45.0`, `174.0`, …, while `dim_security.security_id` is the integer `45`. The other 101,597 rows are blank by design (issue 14). |
| **Dimension violated** | Validity (would also break Referential Integrity once loaded) |
| **Decision** | **Convert** to integer text (`45.0 → 45`). The script asserts that the numeric value is unchanged and that every converted id exists in `dim_security`. |
| **Justification** | A BI tool would type this column as Decimal and the dimension key as Whole Number, so the relationship would not join. Every value ends in `.0`, so no information is lost. |
| **Risk** | A true non-integer id (e.g. `45.5`) would be silently truncated. The script asserts that the fractional part is exactly 0 for every value before converting. |

### 4. Transactions for clients that do not exist (orphans)
| Field | Entry |
|---|---|
| **Table / column** | `fact_transactions.client_id → dim_client.client_id` |
| **Evidence** | **F006:** 200 rows (0.067%) reference 200 distinct `client_id` values (2702–3192) that are not in `dim_client`, nor in `fact_fees` or `fact_portfolio_snapshot`. They are one contiguous block, `txn_id` 298573–298772 (the last 200 rows), and total $10,888,495.37 across every `txn_type`. |
| **Dimension violated** | Referential Integrity |
| **Decision** | **Quarantine** the 200 rows to `data/audit/quarantine_fact_transactions_orphans.csv`. |
| **Justification** | A transaction we cannot attribute to a client cannot be reported by client, advisor or tier. In a BI model it would appear under a blank client and distort totals such as net cash flow. Reassigning them to real clients would be inventing data. The contiguous id block suggests a bad batch load, which the data owner should investigate. |
| **Risk** | If these clients exist in another system, we under-report $10.9M of activity until `dim_client` is fixed. Keeping the rows in quarantine (not deleting them) makes them easy to restore. |

### 5. Negative share counts on Buy transactions
| Field | Entry |
|---|---|
| **Table / column** | `fact_transactions.shares` |
| **Evidence** | **F005:** 836 rows (all `txn_type = Buy`, 692 clients) have negative `shares`. One of them is among the orphan rows quarantined in issue 4, so **835** are repaired. For **all 836**, `amount` equals `round(|shares| × price, 2)` exactly (max difference $0.00), the same identity that holds on all 197,175 security rows. Direction is carried by `txn_type`, and every Sell and Dividend row has positive shares. |
| **Dimension violated** | Validity (sign rule), Accuracy |
| **Decision** | **Convert** to the absolute value. The repair is verified by reconciling to `amount`. |
| **Justification** | The stored `amount` confirms the magnitude, so only the sign is wrong. Left alone, any share-based measure (net shares bought, position size) would be understated. |
| **Risk** | If some of these were really reversals or cancellations, flipping the sign would hide them. But a reversal would be coded `Sell`, and its amount would not reconcile with a positive Buy, so this is unlikely. Each change is logged in `value_changes.csv` and can be undone. |

### 6. `return_ytd` stored as percent strings
| Field | Entry |
|---|---|
| **Table / column** | `fact_portfolio_snapshot.return_ytd` |
| **Evidence** | **F003:** 300 values (0.23%, 279 clients) are strings such as `9.28%` while every other value is a decimal (`0.0928`). Parsing would fail or, if `%` were stripped, give 100× the true value. For all 300, `benchmark_return_ytd + active_alpha_ytd` equals the percent value ÷ 100 to within 0.00005 (the rounding of a 2-decimal percent). The same identity holds within the 0.00001 tolerance on the other 129,247 rows (reconciliation R4 in `03_validate.py`). |
| **Dimension violated** | Validity, Consistency |
| **Decision** | **Convert** by **recomputing** `return_ytd = benchmark_return_ytd + active_alpha_ytd` (6 decimals). The script asserts the result agrees with `percent ÷ 100` within 0.00005 for every row. |
| **Justification** | Recomputing from the two other stored columns restores full 6-decimal precision. Simply dividing by 100 would keep only 4 decimals. Because the percent value confirms the recomputed one, this is a verified repair, not a guess. |
| **Risk** | If alpha were wrong on these rows, we would copy that error into the return. The ≤0.00005 agreement with the independent percent string rules this out. |

### 7. Risk profile missing for 76 clients
| Field | Entry |
|---|---|
| **Table / column** | `dim_client.risk_profile` |
| **Evidence** | **F007:** 76 blanks (3.01%). One belongs to a duplicate removed in issue 1, so **75 remain**. The F007 missingness check shows the blank rate is similar across tiers (Retail 3.2%, HNW 2.4%, UHNW 3.5%), account types (1.9%–3.8%) and active status (3.1% vs 2.3%), with 7–10 blanks in every onboarding year 2015–2022. No group stands out, so it looks MCAR. |
| **Dimension violated** | Completeness |
| **Decision** | **Leave as is** (keep blank; documented as a known limitation). No mode fill. |
| **Justification** | A risk profile is a regulatory suitability judgment about a specific client. Filling in "Balanced" (the mode) would put an invented suitability rating on a real person. Because the gaps look random, leaving them blank does not bias firm-wide risk-mix analysis. In BI the blanks show as "(Blank)", an honest unknown. |
| **Risk** | Analyses grouped by risk profile will have a small "(Blank)" bucket (3%). If the gaps are not random (e.g. one onboarding channel skipped the questionnaire), conclusions about that group could be biased. That has to be disclosed rather than hidden by imputation. |

### 8. Trades dated on weekends (non-trading days)
| Field | Entry |
|---|---|
| **Table / column** | `fact_transactions.txn_date` (Buy/Sell) vs `dim_date.is_trading_day` |
| **Evidence** | **F011:** 40,649 Buy/Sell rows (Buy 23,718, Sell 16,931; 2,519 clients) fall on dates `dim_date` marks as non-trading (Saturdays and Sundays). That is 28.4% of the 143,311 Buy/Sell trades (F004 gives Buy 83,556 + Sell 59,755) and 13.6% of the table. 19 of them are orphan rows quarantined in issue 4, so 40,630 are flagged. |
| **Dimension violated** | Accuracy / Plausibility (cross-table) |
| **Decision** | **Flag** with `trade_on_non_trading_day_flag` = 1. Keep the date. |
| **Justification** | Markets are closed on weekends, so these dates are probably entry or posting dates rather than trade dates. The true trade date is unknown, so moving the row to the "nearest" trading day would invent data. A flag lets an analyst exclude or study these rows. |
| **Risk** | Daily or weekday-level trading analysis would be distorted if the flag is ignored. Monthly and annual totals are unaffected. |

### 9. Activity after a client's account closed
| Field | Entry |
|---|---|
| **Table / column** | `fact_transactions.txn_date` vs the last `fact_portfolio_snapshot.snapshot_date` per client |
| **Evidence** | **F012:** 2,410 transactions (0.8%) for **131 clients** are dated in a month after that client's last monthly snapshot. They span all six types (Buy 689, Sell 482, Dividend 439, Advisory Fee 284, Deposit 278, Withdrawal 238). The cross-table rule "`is_active` = True exactly when the client has a December-2024 snapshot" passes, so every client whose snapshots stop early is inactive. `02_clean.py` asserts that all 131 are inactive. |
| **Dimension violated** | Consistency (cross-table) |
| **Decision** | **Flag** with `txn_after_last_snapshot_flag` = 1. Keep the rows. |
| **Justification** | Either the snapshot history ends too early or these transactions are late or misdated. From the data I cannot tell which table is wrong, so deleting rows would be a guess. The flag makes the conflict visible. |
| **Risk** | Revenue or flow reports for closed accounts may include activity that never happened, or snapshot-based AUM may omit real months. The flag lets either reading be tested. |

## B. More suspicious values that cannot be corrected (flag only)

### 10. `$1,000.00` placeholder balances
| Field | Entry |
|---|---|
| **Table / column** | `fact_portfolio_snapshot.aum` and `fact_fees.aum_basis` |
| **Evidence** | **F009 / F008:** 420 snapshot rows (92 clients) and 386 fee rows (90 clients) have a balance of exactly **1000.0**. For example, snapshot_id 1463 and 1464 (client 29, Feb and Mar 2021) both hold `aum` 1000.0 with `return_ytd` −0.97695. Fee amounts on these rows still reconcile to `aum_basis × bps / 120,000`, and fees `aum_basis` equals snapshot `aum` on every client-month. |
| **Dimension violated** | Accuracy / Plausibility |
| **Decision** | **Flag** with `aum_floor_flag` = 1 in both tables. |
| **Justification** | An exact, repeated round balance after a −97% "return" looks like a system floor or placeholder, not a market value. The real balance can't be recovered, so the value stays and the row is flagged. The two tables agree with each other, so the flag is consistent across them. |
| **Risk** | Ending AUM is slightly understated if these accounts really held more. Excluding flagged rows changes total AUM by at most $1,000 per row, which is immaterial to firm totals but matters for client-level returns. |

### 11. Extreme year-to-date returns
| Field | Entry |
|---|---|
| **Table / column** | `fact_portfolio_snapshot.return_ytd` / `active_alpha_ytd` |
| **Evidence** | **F010:** 3,875 rows (3.0%, 381 clients) differ from their benchmark by more than 50 percentage points year to date. `return_ytd` ranges from −99.4% to +9,467% while `benchmark_return_ytd` stays between −24.0% and +27.4%. `alpha = return − benchmark` still holds on these rows (R4), so the columns are internally consistent; the values themselves are implausible. |
| **Dimension violated** | Accuracy / Plausibility |
| **Decision** | **Flag** with `extreme_return_flag` = 1 where \|`active_alpha_ytd`\| > 0.50. Keep the values. |
| **Justification** | A diversified advised portfolio does not beat or trail its benchmark by 50+ points in a year. These "returns" appear to include deposits and withdrawals rather than investment performance. The true investment return can't be rebuilt from this table, so the rows are flagged instead of changed. 0.50 is a deliberately loose bound, so only clearly implausible rows are caught. |
| **Risk** | An unweighted average return would be dominated by these rows. The committee should use AUM-weighted returns or exclude flagged rows. A threshold that is too loose leaves some distortion in; one that is too tight flags real outperformance. |

## C. Investigated and left as is (legitimate structure or not fixable)

| # | Table / column | Evidence | Dimension | Decision | Justification | Risk |
|---|---|---|---|---|---|---|
| 12 | `dim_security.sector` / `expense_ratio_bps` | **F019 / F018:** 219 blank sectors = exactly the 219 ETFs; 281 blank expense ratios = exactly the 281 single stocks (`is_etf` False). | Completeness | **Leave as is** | **Legitimate structure:** ETFs don't have one sector and stocks don't have an expense ratio. Filling either would invent attributes. | Low. A BI table visual shows blanks; documented in `README_clean.md`. |
| 13 | `dim_advisor.certifications` | **F013:** 6 advisors have the text `None`. | Validity | **Leave as is** | `None` means "no certification" (a real category), not a missing value. It is only dangerous if read with default `pd.read_csv`, which turns it into NaN. That is why every script reads with `keep_default_na=False`. | A tool that treats `None` as null would undercount advisors in a certification breakdown. Documented. |
| 14 | `fact_transactions.security_id` / `shares` / `price` blanks | **F024–F026:** 101,597 blanks in each column. The row rule "security_id/shares/price present for Buy/Sell/Dividend and absent otherwise" passes on all 298,772 rows, so the blanks are exactly the Deposit, Withdrawal and Advisory Fee rows. | Completeness | **Leave as is** | **Legitimate structure:** cash flows and fee debits don't involve a security. | None if documented. The RI null-key rate for `security_id` (34%) is expected, not a defect. |
| 15 | `fact_portfolio_snapshot.return_ytd`, `active_alpha_ytd` scientific notation | **F022 / F021:** 135 (`return_ytd`) + 756 (`active_alpha_ytd`) tiny values written like `9.9e-05`. | Consistency | **Leave as is** | Valid numbers that every parser (pandas, Power BI) reads correctly. Changing them would add no information. | None. |
| 16 | `dim_client.zip_code` and `primary_account_type`; `fact_portfolio_snapshot.account_type` | **F015:** 232 ZIPs start with `0` (e.g. `03897`). **F014 / F020:** account type `529` looks numeric. | Validity | **Leave as is**, keep as **text** | These are codes, not numbers. They are already correct as text and only break if a tool converts them to numbers. `README_clean.md` tells the BI tool to type them as Text. | Losing leading zeros if someone re-imports with default typing. |
| 17 | `dim_client.zip_code` vs `state` | **F016:** 2,211 of the 2,447 clients whose state is already a code (90.4%) have a ZIP whose first digit belongs to a different USPS area than the state (e.g. PA client with ZIP 75726). After state names are standardized (issue 2), the check covers every client: 2,260 of 2,500 (90.4%). It is reported as INFO, not WARN: it fails almost everywhere, so it describes the source data rather than pointing to specific bad rows. | Accuracy / Plausibility | **Leave as is** (documented limitation) | The mismatch is so widespread that the address fields look synthetic or unvalidated. Nothing tells us which field is right, and neither is used as a key. Correcting either would be a guess. | Geographic analysis by ZIP is unreliable; use `state`. |
| 18 | `fact_transactions.amount` on Dividend rows | **F027:** all 53,864 Dividend rows have `amount = shares × price`, i.e. the full market value of the position, not a typical 1–5% payout. | Accuracy / Plausibility | **Leave as is** (documented limitation) | This is a systematic definition issue in the source, not a row-level error. The true dividend per share is not in the data. | Dividend "income" is overstated if summed as income. Flagged in the report. |
| 19 | `fact_transactions` Advisory Fee rows vs `fact_fees` | **F028 / F029:** of the 35,766 Advisory Fee debits, 2,297 have no `fact_fees` row for that client-month, and 33,468 have a fee row with a different amount. Together that is 35,765 of 35,766, so the two tables almost never agree. | Consistency | **Leave as is** (documented limitation) | The two tables describe different things (cash debits vs. billed fees) from different systems. Forcing them to agree would invent data. Fee revenue should come from `fact_fees`, the billing record, whose amounts reconcile exactly (issue 22). | Using `fact_transactions` for fee revenue would give a different answer. Documented. |
| 20 | `fact_portfolio_snapshot` months without a fee | **F023:** 7,350 snapshot client-months (5.7%) have no `fact_fees` row; every fee row does have a snapshot (rule passes). | Completeness | **Leave as is** | A missing bill can't be created without inventing a fee type and rate. It may be a legitimate waiver or billing holiday. | Fee revenue may be understated if these were missed bills. Reported to the committee as a question for billing operations. |
| 21 | `dim_date.is_trading_day` | **F017:** the flag marks weekdays only. 9 fixed market holidays (e.g. 2020-01-01, 2023-12-25) are flagged as trading days. **F030:** 1,508 transactions are dated on them. | Accuracy / Plausibility | **Leave as is** (documented limitation) | The calendar is internally consistent: all date attributes check out (rule passes), and weekends are 0. A full exchange-holiday calendar is outside this data. The trading-day flag in issue 8 inherits this limitation. | Holiday trades are not caught by `trade_on_non_trading_day_flag`. |
| 22 | Columns that **passed** reconciliation | `fact_fees.amount = round(aum_basis × bps / 10,000 / 12, 2)` on 122,197/122,197 rows. `fees.aum_basis = snapshot.aum` on all 122,197 client-months. `fact_transactions.amount = round(\|shares\| × price, 2)` on 197,175/197,175 rows. `advisor_id` in every fact equals the client's advisor (0 mismatches). Snapshot `account_type = primary_account_type` (0 mismatches). `client_tier` matches the `initial_aum` band (0 mismatches). Snapshot `year`/`month` match the date. `is_active` matches having a Dec-2024 snapshot. | — | **Leave as is** | These are good news, and they are also what makes the repairs in issues 5 and 6 verifiable. | None. |
| 23 | Same security name, different tickers | `profile_raw.csv`: `dim_security.name` has 497 distinct values in 500 rows while `ticker` has 500. Three names appear twice, e.g. "Jones Inc Fund" = OLAB (Alternative) and YXPS (Fixed Income). | Uniqueness | **Leave as is** | Different tickers, asset classes and benchmarks: these are two products from the same issuer, not duplicates. `ticker` is unique. | None. |

---

## Order of operations (and why)

1. **Read every file as text.** Nothing is converted until a step does so on purpose.
2. **Dimensions before facts.**
   - **dim_client duplicates (issue 1) first,** so every later check and join runs against one row per client. This also confirms the 25 copies have no fact rows before they leave.
   - **dim_client state (issue 2).**
3. **Quarantine orphans (issue 4) before any value repairs on `fact_transactions`.**
   - The quarantine file keeps the rows exactly as received (raw values).
   - No repair is spent on rows that leave, and every logged value change refers to a row in the clean table.
   - This order is safe because the referential-integrity check compares keys numerically (`45.0` = `45`). The format problem cannot create false orphans.
4. **Then fix the `security_id` format (issue 3) and prove every id joins.** After conversion, the security relationship is re-checked: 100% of ids must exist in `dim_security`.
5. **Value repairs that can be reconciled:** shares sign (issue 5, checked against `amount`) and `return_ytd` (issue 6, checked against benchmark + alpha and the percent string).
6. **Flags last (issues 8–11),** computed on the cleaned tables. The "after last snapshot" flag depends on the final snapshot table and the final client list.
7. **Final proof** for every table:
   - raw rows = clean rows + quarantined rows;
   - reload the clean files as text and confirm the shape and columns, with flags as the only additions.
