# HW2 Validation — Wildcat Capital Transaction EDA

**Author:** Tyler Tobin | **Course:** MIS3060 | **Script validated:** `hw02/hw02_eda.py`
**Run date:** 2026-09-21

---

## 2A — Known-Answer Benchmarks

| Check | Expected | Your Script Produced | Match? | Notes |
|---|---|---|---|---|
| Dataset shape | (298772, 9) | (298772, 9) | Y | |
| Null count — `security_id` | 101,597 | 101,597 | Y | |
| Null count — `amount` | 0 | 0 | Y | |
| Unique `txn_type` values | 6 | 6 | Y | |
| Count of `Buy` transactions | 83,556 | 83,556 | Y | Confirmed twice more in 2C cross-validation |
| `txn_date` data type | object | object | Y | |
| Earliest `txn_date` | 2020-01-01 | 2020-01-01 | Y | |
| Latest `txn_date` | 2024-12-30 | 2024-12-30 | Y | |
| Duplicate `txn_id` count | 0 | 0 | Y | |
| Mean `amount` | $54,075.17 | $54,075.17 | Y | |
| Median `amount` | $41,220.48 | $41,220.49 | **N** | See explanation below |
| Skewness of `amount` | 1.15 | 1.15 | Y | |
| Correlation `shares`–`amount` | 0.65 | 0.65 | Y | |
| Correlation `price`–`amount` | 0.64 | 0.64 | Y | |
| Correlation `shares`–`price` | 0.00 | 0.00 | Y | |
| Negative `shares` count (Buy only) | 836 | 836 (all in Buy) | Y | |
| Profile file created | Yes | Yes | Y | `hw02/hw02_profile.txt` |
| Chart files created (3) | Yes | Yes | Y | Viewed all three; match expected shapes |

**Discrepancy — median `amount`:** The script prints $41,220.49; the independently-calculated benchmark is $41,220.48. I traced this: the true median value is `41220.485000000000582...` — the float representation sits *just* above the exact .485 halfway point. Python's `round()` function rounds-half-to-even at a true tie and gives `.48`, while the `:.2f` string formatting used in the print statement rounds based on the actual (slightly-above-.485) binary value and gives `.49`. Both are defensible; this is a floating-point rounding-boundary artifact, not a bug in the grouping, filtering, or loading logic — every other value derived from the same column (mean, skew, the by-type grouping) matches the benchmark exactly. No code change was needed; documenting it here per the "any row where Match = No" instruction.

---

## 2B — Explain the Code and Output

Per the Week 4 slides ("the session that generated the code is not a neutral reviewer" / "known-answer testing should not be done by the same AI that generated the code"), this review was run in a **separate, independent Claude session with no knowledge of how `hw02_eda.py` was written** — it was handed only the raw script text and, in a second turn, the raw terminal output, cold. Full transcript in `hw02/cowork_review_transcript.md`.

**Prompt 1 — "Walk me through each section... what should I see in the terminal?"**
The reviewer correctly predicted, from reading the code alone (no data access): the 9-column schema and that `txn_date` would load as `object` since no `parse_dates` is used; that `shares`/`price`/`amount` would be floats; that missing values were most plausible in `shares`/`price`/`amount`; that `amount` would very likely show mean > median with positive skew (predicted skew "meaningfully greater than 0, roughly >1"); that the correlation step reduces to just the 3 possible pairs re-ranked, not a real filter; and — most notably — that negative share counts would be "suspicious on a Buy/Deposit-type row" and worth flagging if they appeared. It explicitly labeled its specific numbers as illustrative placeholders since it had no access to the CSV.

**Prompt 2 — pasted the actual terminal output, asked what each value means / what's unexpected.**
Top flags raised: (1) 836 negative-share `Buy` rows as "the single most concerning finding," (2) that `Sell`/`Dividend` shares are *all* positive while `Buy` carries the negatives — backwards from the sign convention you'd expect, worth confirming with a data owner; (3) `Advisory Fee`'s mean ($7,375) being ~8.6x its median ($859), indicating a small number of unusually large fee rows; (4) that the 101,597 nulls in `security_id`/`shares`/`price` map *exactly* onto `Advisory Fee` + `Deposit` + `Withdrawal` (35,766 + 35,981 + 29,850 = 101,597) and are "almost certainly by design."

**Answers to the assignment's six questions:**

1. **Did predictions match the actual terminal output?** Structurally, yes — every qualitative prediction held (dtype pattern, mean>median right-skew, the negative-shares red flag, the correlation-reduces-to-3-pairs behavior, missing-value columns). The only "misses" were in illustrative numeric guesses the reviewer explicitly flagged as placeholders (e.g., it guessed a steeper skew of ~3.85 vs. the actual 1.15, and guessed the date range might run through 2024-12-31 vs. the actual 2024-12-30) — expected, since it never had the CSV.
2. **What did Claude flag as unexpected/worth investigating?** The four items above: negative-share Buys, the inverted-looking Buy/Sell sign pattern, the skewed Advisory Fee amounts, and (as a secondary note) that `price` hits exact round bounds ($10–$500) and has ~0 correlation with `shares`, suggesting these two fields may have been generated independently rather than reflecting real market dynamics.
3. **Did Claude mention the 101,597 nulls in `security_id`? What explanation?** Yes — it identified that the null count is identical across `security_id`, `shares`, and `price`, tied it exactly to the `Advisory Fee` + `Deposit` + `Withdrawal` row counts, and concluded this is structural by design (those transaction types don't touch a specific security), not a data-quality defect.
4. **Did Claude flag `txn_date` as a concern? Why would it matter for time-series analysis?** Yes, in Prompt 1: it noted the column is never actually converted in the DataFrame itself (only a local copy is parsed for the min/max check), so downstream code that tries date arithmetic directly on `df['txn_date']` (e.g., `.diff()` to get days between transactions) would either raise a `TypeError` on string subtraction, or — worse — silently sort incorrectly if the date strings weren't in a sortable ISO format, producing wrong "days between transactions" figures with no error at all.
5. **Do the charts match the explanation?** Yes. I opened all three PNGs myself: the histogram shows the expected right-skew with the mean line sitting to the right of the median line; the box plot shows `Advisory Fee` as a visibly compressed box near zero with a long tail of high outliers (exactly as predicted from its mean/median gap); the scatter plot shows the `Buy` series (only) extending into negative-shares territory on the left, distinctly separated from the `Sell`/`Dividend` cluster on the right — the 836-row anomaly is visually obvious. No differences worth flagging.
6. **One follow-up question and answer:** *"If I wanted to distinguish 'this is realistic-enough teaching data' from 'this indicates a genuine bug,' what's the single most useful additional check I could run?"* → The reviewer suggested computing the residual `amount - (|shares| × price)` for every row where `shares`/`price` are populated: a near-zero residual across the board would confirm `amount` is a consistent, deterministic function of the other two fields (fine for teaching data); a large/scattered residual would mean the three fields don't actually agree with each other internally, which is a real bug. **I ran this check**: across all 197,175 rows with non-null `shares`/`price`, the residual has mean ≈ $0.00, max absolute value $0.005 (i.e., sub-penny, floating-point rounding only), and 100% of rows fall within $0.01. This confirms `amount` is internally consistent with `shares × price` for every trade-type row — the dataset's math is self-consistent even where the sign convention looks unusual.

---

## 2C — Business Check & Cross-Validation

> **Note:** The items below are drafted as a starting point. Per the assignment's own instruction ("answer in your own words... do not paste Claude's response as your answer"), these should be reviewed, adjusted, and put in your own words before this file is submitted — this is exactly the section your professor designed to check your own understanding, not Claude Cowork's.

### Business-reasonableness questions (draft)

**1. Which three transaction types would have no security, and do the counts add up?**
`Deposit`, `Withdrawal`, and `Advisory Fee` — none of these involve buying or selling a specific holding; a cash deposit, a cash withdrawal, and a fee charge don't reference a security. Counts: 35,981 + 29,850 + 35,766 = **101,597**, which matches the null count in `security_id` exactly.

**2. More Buys (83,556) than Sells (59,755) over five years — what does that mean for the firm?**
Draft interpretation: a wealth-management book where buys structurally outpace sells over a multi-year window is usually a sign of net asset growth — new client contributions, dividend reinvestment, and a client base still in an accumulation phase (working, adding to accounts) rather than a decumulating one (retirees drawing down). It isn't inherently alarming; the concern would only be if sells were *disproportionately* rare relative to what the fee/dividend activity implies.

**3. `txn_date` stored as a string — what breaks if computing average days between transactions on the strings directly?**
Draft: pandas/Python can't do date arithmetic on strings — `date2 - date1` on two string values either raises a `TypeError` (if attempted directly) or, if someone works around it by treating them as sortable text, produces meaningless results the moment the format isn't a sortable ISO pattern. Even where ISO strings happen to sort correctly, you still can't compute a numeric "days between" without first converting to `datetime` — the string itself carries no notion of duration.

**4. Is ~108 clients per advisor (2,700 ÷ 25) plausible for an RIA?**
Sourced check: industry data compiled from the Investment Adviser Association/FINRA (via SmartAsset) puts the *median* at about 73 clients per advisor, with a commonly-cited "sustainable practice" range of roughly 50–150 clients depending on firm structure and niche; the headline "average" of ~173 is skewed upward by very large firms. Wildcat's ~108 sits comfortably inside that sustainable 50–150 range — plausible for a firm of this size, not a red flag. (Source: SmartAsset, "Average Number of Clients Per Financial Advisor," citing Investment Adviser Association / FINRA data.)

**5. 836 negative-share Buy transactions — two plausible explanations, and next step?**
Draft: (a) a sign-convention/data-entry error, where a same-day correction or a partially-cancelled Buy order was recorded by negating the share count on the original `Buy` row instead of using a distinct reversal/adjustment type; (b) a legitimate correction or custodian adjustment entry, deliberately using a negative quantity on the same transaction type to net out an erroneous trade without inventing a new category. What I'd do next: pull the 836 rows and check whether they cluster on specific dates, clients, or advisors (a cluster would point to a systemic entry pattern rather than random typos), and check whether each has a matching offsetting trade nearby in time. Note from the internal-consistency check above: `amount` still equals `|shares| × price` for these rows, meaning whatever produced the negative sign did so consistently — it didn't corrupt the dollar amount, which is at least reassuring.

### Cross-validation — Buy count

- **Prompt A** (direct filter, `hw02/crossval/prompt_a_count_buy.py`): counted rows where `txn_type == 'Buy'` → **83,556**
- **Prompt B** (subtraction, `hw02/crossval/prompt_b_subtract.py`): total rows (298,772) minus rows where `txn_type` is Sell/Deposit/Withdrawal/Dividend/Advisory Fee (215,216) → **83,556**

6. **What did each script return?** Both returned 83,556.
7. **Do the results agree?** Yes, exactly — matches the known-answer benchmark as well.
8. **Why is subtraction useful as a second check, not just direct filtering?** Direct filtering and subtraction share the same source data but exercise different logic paths (an equality filter vs. a set-membership filter plus arithmetic). If, say, `txn_type` had a hidden 7th category, a stray whitespace variant of "Buy", or a case-sensitivity issue, the direct filter and the subtraction approach could diverge and expose it — agreement here raises confidence that "Buy" is a clean, exhaustively-categorized value, not proof by itself, since a systematic error present in *both* scripts (e.g., loading the wrong CSV) wouldn't be caught by this check alone.

---

## Environment / setup note

`verify_setup.py` reported 14/14 required libraries installed correctly before the script was run (see terminal log). Script runtime: ~6 seconds for all 14 sections plus 3 charts on the full 298,772-row file — well under the 15–45 second range noted in the assignment as normal, and far under the 2-minute concern threshold.
