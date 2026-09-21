# HW2 — Part 2B Independent Review Transcript

This review was conducted in a session with no knowledge of how `hw02_eda.py`
was generated, per the Week 4 instruction that known-answer/code/output
review should not be done by the same session that wrote the code.

---

## Prompt 1

"Walk me through each section of this script, including the grouping,
correlation, and charting steps. What should I see in the terminal when I
run it? List each expected output value explicitly."

(Full script pasted, no other context given.)

### Response

Predicted, section by section, that the schema would show 9 columns with
`txn_date` as `object` (no `parse_dates` used), `shares`/`price`/`amount`
as floats; that missing values were most plausible in `shares`/`price`/
`amount`; that `amount` would likely show mean > median with positive
skew; that the 3-variable correlation step reduces to just the 3 possible
pairs re-ranked rather than a true filter; and that negative share counts
would be suspicious specifically on a Buy/Deposit-type row. All specific
numbers were explicitly flagged as illustrative, since the script was read
without access to the CSV.

---

## Prompt 2

"Here is the terminal output from running an EDA script on a wealth
management transaction dataset. What does each value mean? Flag anything
that looks unexpected or that I should investigate before using this data
in an analysis."

(Full terminal output pasted — see hw02/hw02_profile.txt for the same
content.)

### Response — top flags

1. 836 negative-share `Buy` transactions — "the single most concerning
   finding in the output."
2. `Sell`/`Dividend` shares are all positive while `Buy` carries the
   negatives — backwards from the sign convention you'd normally expect;
   worth confirming with whoever owns the source data.
3. `Advisory Fee` mean ($7,375.17) is ~8.6x its median ($859.12) — a small
   number of unusually large fee rows are pulling the average up.
4. The 101,597 nulls in `security_id`/`shares`/`price` line up exactly
   with `Advisory Fee` + `Deposit` + `Withdrawal` row counts
   (35,766 + 35,981 + 29,850 = 101,597) — "almost certainly by design."

Section-by-section notes covered: `client_id` range (1-3,192) having gaps
relative to the 2,700 unique clients actually present; `advisor_id` and
`security_id` being fully contiguous (25 and 500, matching their ranges
exactly); `price` hitting exact round bounds ($10-$500), suggesting a
generated/bounded field rather than real market prices; shares-price
correlation near 0.00 as a secondary sign of independently-generated
fields; and that all three charts should visually surface the negative-
share Buy anomaly once viewed.

---

## Follow-up question

"If I wanted to distinguish 'this is realistic-enough teaching data' from
'this indicates a genuine bug in how the dataset was built,' what's the
single most useful additional check I could run on this data to tell the
difference?"

### Response

Compute the residual `amount - (|shares| * price)` for every row where
`shares`/`price` are populated. A residual near zero across the board
confirms `amount` is a deterministic function of the other two fields
(fine for teaching data); a large or scattered residual would mean the
three fields don't actually agree with each other, which is a real
internal-consistency bug.

**This check was run** (see hw02/validation.md, 2B Q6): across all 197,175
applicable rows, the residual has mean ~$0.00 and max absolute value
$0.005 — sub-penny, floating-point rounding only. `amount` is internally
consistent with `shares x price` for every trade-type row.
