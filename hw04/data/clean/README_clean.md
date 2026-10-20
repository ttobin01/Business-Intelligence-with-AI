# Wildcat Capital — Clean Data (`data/clean/`)

Produced by `scripts/02_clean.py` from the eight raw files in `data/raw/`. The raw files are never modified. Each file keeps the same name and the same columns as its raw table. A few `0/1` flag columns were added (listed below). Every change is traceable in `data/audit/`, and the reasoning is in `decision_log.md`.

| File | Raw rows | Clean rows | Quarantined | Grain (one row = …) | Primary key |
|---|---:|---:|---:|---|---|
| `dim_advisor.csv` | 25 | 25 | 0 | advisor | `advisor_id` |
| `dim_benchmark.csv` | 8 | 8 | 0 | benchmark | `benchmark_id` |
| `dim_client.csv` | 2,525 | 2,500 | 25 | client | `client_id` |
| `dim_date.csv` | 1,827 | 1,827 | 0 | calendar day, 2020-01-01 to 2024-12-31 | `date_id` (business key `date`) |
| `dim_security.csv` | 500 | 500 | 0 | security or ETF | `security_id` |
| `fact_fees.csv` | 122,197 | 122,197 | 0 | client × month (fee charge) | `fee_id` |
| `fact_portfolio_snapshot.csv` | 129,547 | 129,547 | 0 | client × month-start snapshot | `snapshot_id` |
| `fact_transactions.csv` | 298,772 | 298,572 | 200 | client transaction | `txn_id` |

Raw rows = clean rows + quarantined rows holds for every table. `02_clean.py` asserts this.

## Relationships (13): all many-to-one, dimension filters fact

| # | From (many) | To (one) | Notes |
|---|---|---|---|
| 1 | `dim_client.advisor_id` | `dim_advisor.advisor_id` | |
| 2 | `dim_security.benchmark_id` | `dim_benchmark.benchmark_id` | |
| 3 | `fact_transactions.client_id` | `dim_client.client_id` | 100% match after quarantine |
| 4 | `fact_transactions.advisor_id` | `dim_advisor.advisor_id` | Equals the client's advisor on every row |
| 5 | `fact_transactions.security_id` | `dim_security.security_id` | Blank on purpose for Deposit, Withdrawal and Advisory Fee rows (101,528 rows) |
| 6 | `fact_fees.client_id` | `dim_client.client_id` | |
| 7 | `fact_fees.advisor_id` | `dim_advisor.advisor_id` | |
| 8 | `fact_portfolio_snapshot.client_id` | `dim_client.client_id` | |
| 9 | `fact_portfolio_snapshot.advisor_id` | `dim_advisor.advisor_id` | |
| 10 | `fact_portfolio_snapshot.benchmark_id` | `dim_benchmark.benchmark_id` | Only ids 1, 3 and 8 are used |
| 11 | `fact_transactions.txn_date` | `dim_date.date` | |
| 12 | `fact_fees.fee_date` | `dim_date.date` | Always the 1st of the month |
| 13 | `fact_portfolio_snapshot.snapshot_date` | `dim_date.date` | Always the 1st of the month |

Every non-blank foreign key resolves to its parent (see `reports/data_quality_scorecard.csv`).

## Column types a BI tool needs (set these in Power Query; do not accept the auto-detected types)

| Type | Columns |
|---|---|
| **Whole Number** | All `*_id` keys, including `security_id`, which is now integer text (`45`, not `45.0`). Also `age`, `years_experience`, `aum_target_mm`, `year`, `quarter`, `month`, `week_of_year`. |
| **Date** | `date`, `client_since`, `txn_date`, `fee_date`, `snapshot_date` (all ISO `yyyy-mm-dd`) |
| **Decimal / Fixed decimal** | `initial_aum`, `aum`, `aum_basis`, `amount`, `price`, `shares`, `bps_charged`, `expense_ratio_bps`, `return_ytd`, `benchmark_return_ytd`, `active_alpha_ytd`, `cash_pct`. A few tiny returns are written in scientific notation (e.g. `9.9e-05`); they are valid decimals. |
| **Text (must stay text)** | `zip_code` (many ZIPs start with `0`, e.g. `03897`), `primary_account_type` and `account_type` (the value `529` is a plan type, not a number), `ticker`, `ticker_proxy`, names, `certifications` |
| **True/False** | `is_active`, `is_etf` (stored as `True`/`False`) |
| **Whole Number 0/1** | `dim_date` flags (`is_month_end`, `is_quarter_end`, `is_year_end`, `is_trading_day`) and all added `*_flag` columns |

Read CSVs with `keep_default_na=False` (pandas) or check the "null" handling in Power Query. `certifications = None` means *no certification*, not a missing value.

**Measure additivity:**
- `amount` (fees and transactions) is additive. Transaction amounts are always positive; the direction comes from `txn_type`.
- `aum` and `aum_basis` are semi-additive. Never sum them across months.
- Ratios (`bps_charged`, `return_ytd`, `cash_pct`, …) must be weighted by AUM, not added or simply averaged.

## Flag columns added (0 = no, 1 = yes)

| Table | Column | Rows = 1 | Meaning (decision-log issue) |
|---|---|---:|---|
| `fact_transactions` | `trade_on_non_trading_day_flag` | 40,630 | Buy/Sell dated on a day `dim_date` marks as non-trading (weekend). The real trade date is unknown, so the date is kept (#8). |
| `fact_transactions` | `txn_after_last_snapshot_flag` | 2,410 | Transaction dated after the client's last monthly snapshot. These are 131 inactive clients; it is unclear which table is wrong (#9). |
| `fact_portfolio_snapshot` | `aum_floor_flag` | 420 | `aum` is exactly $1,000.00, which looks like a placeholder floor rather than a market value (#10). |
| `fact_fees` | `aum_floor_flag` | 386 | `aum_basis` is exactly $1,000.00. It matches the snapshot flag for the same client-month on every row (#10). |
| `fact_portfolio_snapshot` | `extreme_return_flag` | 3,875 | \|`active_alpha_ytd`\| > 0.50. The return is implausibly far from its benchmark, apparently driven by cash flows (#11). |

Values that **were** corrected are not flagged; they are listed cell by cell in `data/audit/value_changes.csv`:

| Table | Column | Cells changed | Change |
|---|---|---:|---|
| `dim_client` | `state` | 77 | Full state name → USPS code |
| `fact_transactions` | `security_id` | 197,044 | Decimal format → integer (`45.0` → `45`) |
| `fact_transactions` | `shares` | 835 | Negative Buy shares → absolute value |
| `fact_portfolio_snapshot` | `return_ytd` | 300 | Percent string → `benchmark_return_ytd + active_alpha_ytd` |

## Quarantined rows (`data/audit/quarantine_*.csv`)

- **`quarantine_dim_client_duplicates.csv` (25 rows):** clients 2501–2525. Each is a copy of an existing client (column `duplicate_of_client_id`) with a truncated last name, and has no fact rows.
- **`quarantine_fact_transactions_orphans.csv` (200 rows):** `txn_id` 298573–298772. These reference `client_id` 2702–3192, which exist in no table. Total amount $10,888,495.37. Values are kept exactly as received.

## Known limitations (chosen not to fix, with reasons)

1. **`dim_client.risk_profile` is blank for 75 clients (3.0%).** Filling in a suitability rating would invent a regulatory judgment about a real client. The gaps look random across tier, status, year and advisor. They show as "(Blank)".
2. **ZIP code and state disagree on 2,260 of 2,500 clients (90.4%)** (by USPS first digit). The address fields look unvalidated or synthetic, and nothing says which one is right. Use `state` for geography; do not use `zip_code` for location analysis.
3. **Dividend amounts equal the full position value** (`shares × price`) on all 53,826 Dividend rows. Summing them as "dividend income" would overstate income; the true dividend per share is not in the data.
4. **Advisory Fee transactions do not tie to `fact_fees`.** 35,741 debits (all but one) differ from the billed amount for the same client-month. Use `fact_fees.amount` for fee revenue: it reconciles exactly to `aum_basis × bps_charged / 120,000`.
5. **7,350 snapshot client-months (5.7%) have no fee row.** They may be waivers or missed bills. A fee can't be created without inventing its type and rate.
6. **`dim_date.is_trading_day` only excludes weekends.** For example, 2020-01-01 and 2023-12-25 are marked as trading days. The non-trading-day flag therefore misses holiday trades (1,508 transactions fall on fixed holidays).
7. **Flagged values are kept** (weekend trades, post-closure activity, $1,000 floors, extreme returns). Filter on the flag columns, or use AUM-weighted measures, when these would distort a figure.
