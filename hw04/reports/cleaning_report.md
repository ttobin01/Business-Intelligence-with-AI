# Wildcat Capital: Data Cleaning Report

**To:** Portfolio Committee | **From:** Tyler Tobin, MIS3060 | **Date:** October 19, 2026
**Scope:** the eight-table warehouse extract (5 dimension and 3 fact tables, 2020–2024)
**Sources:**
- `decision_log.md`
- `data/audit/cleaning_log.csv`
- `reports/data_quality_scorecard.csv`
- the printed output of `scripts/01_profile.py`, `02_clean.py` and `03_validate.py`

## Executive summary

The extract was largely sound, but it was not safe to report from as delivered. The audit ran 277 checks and found **6 ERROR-level defects**:

1. 25 duplicate client records
2. 200 transactions ($10,888,495.37) for clients who do not exist
3. 836 Buy trades with negative share counts
4. 300 returns stored as text percentages
5. 78 states spelled out in full
6. every one of the 197,175 security IDs in the transactions table stored in a format that would not join in Power BI

All six were resolved by **verified** repairs or by quarantine. No figure was imputed and no row was deleted silently: 225 rows went to quarantine files, and 198,256 cell-level changes are logged.

**The resulting clean data has:**
- 100% key uniqueness and type validity in every table, and 100% referential match in every table that has foreign keys
- 2,500 clients, 298,572 transactions, 122,197 fee rows and 129,547 monthly snapshots

Four kinds of suspicious values could not be corrected without inventing data. Those are **flagged, not changed**, in five new 0/1 flag columns.

**What the committee should take away:**
- Fee revenue ($204,675,583.12) and December-2024 ending AUM ($12,729,572,078.86 across 2,325 active clients) are reliable. Every fee reconciles exactly to its AUM basis × rate.
- Net cash flow falls from $327,788,721.46 to $327,439,026.62 once the unattributable transactions are removed.
- Client-level returns must be read with care. The simple average December-2024 YTD return is 33.49%. Weighted by AUM it is 20.0%, and excluding flagged extreme rows the simple average is 18.81%.

## Cleaning summary

| # | Table | Issue (audit evidence) | Action | Rows | Verified by |
|---|---|---|---|---:|---|
| 1 | dim_client | Same client entered twice under ids 2501–2525 (name truncated) | Quarantine | 25 | 12 identical attributes; one-letter last-name change; copies have 0 fact rows |
| 2 | dim_client | State as full name ("Pennsylvania") | Standardize to code | 77 | Explicit map; per-state counts add up |
| 3 | fact_transactions | client_id 2702–3192 not in any table | Quarantine | 200 | RI match 99.93% → 100% |
| 4 | fact_transactions | security_id stored as `45.0` | Convert to integer | 197,044 | Value unchanged; 100% join to dim_security |
| 5 | fact_transactions | Negative shares on Buy | Absolute value | 835 | amount = \|shares\| × price on every row |
| 6 | fact_portfolio_snapshot | return_ytd as `"9.28%"` | Recompute = benchmark + alpha | 300 | Agrees with percent ÷ 100 within 0.00005 |
| 7 | fact_transactions | Buy/Sell on a weekend | Flag | 40,630 | dim_date trading-day flag |
| 8 | fact_transactions | Activity after an account's last snapshot | Flag | 2,410 | All 131 clients are inactive |
| 9 | snapshot / fees | Balance exactly $1,000.00 | Flag | 420 / 386 | Flags agree across both tables |
| 10 | fact_portfolio_snapshot | Return > 50 points from benchmark | Flag | 3,875 | alpha = return − benchmark still holds |
| 11 | dim_client | Risk profile blank | Leave blank | 75 | Gaps evenly spread (MCAR-like) |

Counts differ slightly from the raw audit (78 states, 836 share signs, 40,649 weekend trades) because one state name and some negative-share and weekend rows sat on records that were quarantined first.

**Scorecard (raw → clean):**

| Table | Measure | Raw | Clean |
|---|---|---:|---:|
| fact_transactions | Type validity | 91.73% | 100% |
| fact_transactions | Referential match | 99.982% | 100% |
| dim_client | Key uniqueness | 99.01% | 100% |
| fact_portfolio_snapshot | Type validity | 99.982% | 100% |

Rule pass stays below 100% in three fact tables (fact_fees 99.977%, fact_portfolio_snapshot 99.826%, fact_transactions 98.901%) because the flagged WARN issues (balance floors, extreme returns, weekend trades, post-closure activity) are still counted as rule failures. The scorecard shows these limitations instead of hiding them; dim_client moves from 99.742% to 100%.

## Key judgment calls

**1. Quarantine, not repair, the 200 orphan transactions.**
- *Justification:* the client IDs exist nowhere in the extract, so any reassignment would be fabrication.
- *Risk:* if these clients exist in another system, $10.9M of activity is under-reported until `dim_client` is completed. The rows are preserved and can be restored.

**2. Do not impute missing risk profiles (75 clients).**
- *Justification:* the course lab filled these with the mode ("Balanced"), but a risk profile is a suitability judgment about a real person. The gaps show no pattern by tier, activity, onboarding year or advisor, so leaving them blank does not bias the firm-wide risk mix.
- *Risk:* risk-based analysis has a 3% "(Blank)" group. If the gaps are not random, that group could hide a pattern.

**3. Repair only what another column can prove.**
- *Justification:* share signs were corrected only because `amount = |shares| × price` held on all 835 rows. Returns were recomputed from benchmark + alpha only after confirming they matched the stored percentages.
- *Risk:* if the reference column were itself wrong, the error would be copied. Both identities hold on 100% of the untouched rows, which makes this unlikely.

**4. Flag implausible but uncorrectable values instead of changing or dropping them.**
- *Justification:* 3,875 snapshots show returns more than 50 points away from their benchmark, apparently driven by deposits and withdrawals. 40,630 trades are dated on weekends. The true values are unknown.
- *Risk:* users who ignore the flags will over-state performance. The simple average return of 33.49% vs the AUM-weighted 20.0% shows the size of the distortion.

## Limitations (not fixed, by design)

- **Addresses:** ZIP and state disagree for 2,260 of 2,500 clients (90.4%). Use state, not ZIP, for geography.
- **Dividends:** dividend amounts equal the full position value on all 53,826 Dividend rows, so they overstate income.
- **Advisory Fee debits:** these do not tie to billed fees (35,741 debits, all but one, differ). Use `fact_fees` for revenue: it reconciles exactly.
- **Missing fees:** 7,350 client-months (5.7%) have a snapshot but no fee. These may be waivers or missed billing; this needs a check with billing operations.
- **Holidays:** `dim_date` treats market holidays as trading days, so 1,508 holiday-dated transactions are not flagged.
- **Outlier flags:** IQR rules flag 10.2% of snapshot balances and 9.3% of fee amounts. **A flag does not mean a value is wrong:** client wealth is highly skewed, so legitimate UHNW accounts fall outside the fences. A flag only marks a value for review.

---
AI-assisted report — reviewed for factual accuracy on [date] by Tyler Tobin
