# HW3 AI Usage Log

**Author:** Tyler Tobin | **Course:** MIS3060 | **Tool:** Claude Cowork | **Date:** 2026-09-30

Each of the three generation prompts below was sent as the opening message of its own **separate** Claude Cowork session, with no shared context. Follow-up fixes were requested only after reading the live output against the source filings.

---

## Prompt 1: Specification A (earnings pipeline → `hw03/hw03_earnings.py`)

> Write a Python script saved as `hw03/hw03_earnings.py` that builds a quarterly earnings history for five companies from their SEC Form 8-K earnings press releases. Use only the `requests` and `beautifulsoup4` packages plus the Python standard library (`re`, `csv`, `time`, `os`, etc.). The script is run from the repository root with `python hw03/hw03_earnings.py`, so all file paths should be relative to the repo root (or built from the script's own folder).
>
> **1. Identify yourself to the SEC on every request.** Define one headers dictionary at the top of the script, `{"User-Agent": "MIS3060 Villanova ttobin01@villanova.edu"}`, and pass it on *every* `requests.get()` call in the script — the submissions API call, the filing-index call, and the exhibit download — not just the first one. SEC EDGAR rejects requests without an identifying User-Agent. Also pause about 0.2 seconds between requests so the script stays well under the SEC's 10-requests-per-second fair-access limit, and use a timeout on every request.
>
> **2. Find the earnings 8-Ks.** Hard-code these five companies and use these CIKs exactly (do not look them up): Apple Inc. (AAPL, 0000320193), Microsoft Corporation (MSFT, 0000789019), NVIDIA Corporation (NVDA, 0001045810), JPMorgan Chase & Co. (JPM, 0000019617), Walmart Inc. (WMT, 0000104169). For each company, request `https://data.sec.gov/submissions/CIK{cik}.json` (10-digit, zero-padded CIK). In the JSON, `filings.recent` holds parallel lists (`form`, `filingDate`, `accessionNumber`, `items`, `primaryDocument`); loop over them by index and keep filings where the form is exactly `"8-K"` (ignore `8-K/A` amendments so a quarter is not double-counted) and the `items` string contains `"2.02"` (Results of Operations and Financial Condition).
>
> **3. Keep the four most recent.** The list is already newest-first. Keep the first **four** matching filings per company — one per quarter.
>
> **4. Locate and download the press release.** For each filing, build the filing index URL `https://www.sec.gov/Archives/edgar/data/{cik without leading zeros}/{accession number without dashes}/{accession number with dashes}-index.htm`. Parse the document table on that page and pick the earnings press release exhibit: the `.htm` document whose Type is `EX-99.1` (fall back to any `.htm` whose Type starts with `EX-99`, and then to any `.htm` file whose name contains `ex99`/`ex-99`/`ex991`). Some companies (e.g., JPMorgan) attach a second EX-99 exhibit with a long financial supplement — prefer EX-99.1, which is the press release. Download the exhibit and strip the HTML to plain text with BeautifulSoup (`get_text(" ")`), then collapse all runs of whitespace (including non-breaking spaces) to single spaces. If no exhibit can be found, or any request for that filing fails, **do not crash**: print a clear warning such as `WARNING: [Ticker] filing {accession}: press release exhibit not found — skipping`, and continue with the next filing.
>
> **5. Extract four fields from the plain text with regular expressions.** Company press releases word things differently, so try several patterns for each field in order and take the first match:
> - **Quarterly revenue** — phrasings such as "revenue of $109.4 billion", "revenue was $76.4 billion", "Revenue for the quarter was $X", "total revenue of $X", "reported revenue of $X", "net revenue of $X" and (for banks) "Reported revenue ... $X billion". Capture the number *and* its unit (million or billion) and convert it to a number in **millions of US dollars** (e.g., $109.4 billion → `109400`; $46,743 million → `46743`). If the only match is a figure from a statement table, use it only if it clearly belongs to the current quarter's total revenue (e.g., "Total net sales", "Total revenue", "Total net revenue").
> - **Diluted EPS** — phrasings such as "diluted earnings per share was $2.02", "diluted earnings per share of $X", "EPS of $X", "earnings per share of $X", or a "Diluted earnings per share" / "Diluted" row in the income statement table. Store it as a plain decimal number (e.g., `2.02`).
> - **Net income** — phrasings such as "net income of $X billion", "net income was $X billion", "reported net income of $X", "consolidated net income attributable to …", or the "Net income" row of the condensed income statement table (where figures are in millions). Convert to **millions of US dollars** the same way as revenue.
> - **Reporting period** — the text description of the quarter, e.g., "fourth quarter fiscal 2024", "fiscal 2026 third quarter", "second-quarter 2026", "Q2 FY27". Return the phrase as written in the release (lightly cleaned), not a date.
> Search the headline and first few paragraphs first, since that is where current-quarter figures appear; do not accidentally pick up the prior-year comparison figure.
>
> **6. Print a progress line for every filing** as it is processed, exactly in this format: `[Ticker] | [Period] | Revenue: $X | EPS: $X | Net Income: $X`, e.g., `AAPL | fiscal 2026 third quarter | Revenue: $109,400M | EPS: $2.02 | Net Income: $29,789M`. Missing values print as `NOT_FOUND`.
>
> **7. Save the results.** Write all rows to `hw03/earnings_history.csv` (create the `hw03` folder if needed; overwrite the file on each run so reruns don't duplicate rows) with exactly these columns in this order: `company`, `ticker`, `cik`, `filing_date`, `period`, `revenue_reported`, `eps_diluted`, `net_income`. `cik` is the 10-digit CIK string, `filing_date` is `YYYY-MM-DD`, and `revenue_reported` and `net_income` are in millions of USD. After saving, print `Saved N rows to hw03/earnings_history.csv`.
>
> **8. Missing data is explicit.** Whenever a regex returns no match for a field, store the literal string `"NOT_FOUND"` in that cell — never `None`, `NaN`, or an empty string. A blank cell and "we looked and it wasn't there" mean two different things. The script must finish and write the CSV even if some fields (or whole filings) fail.
>
> Organize the code into small functions (get filings, find exhibit, fetch text, extract each field, write CSV) with a `main()` guarded by `if __name__ == "__main__":`, and add short comments explaining each regex.

## Prompt 2: Specification B (executive events pipeline → `hw03/hw03_executives.py`)

> Write a Python script saved as `hw03/hw03_executives.py` that builds a table of executive and director departures and appointments for five companies from their SEC Form 8-K filings. Use only `requests`, `beautifulsoup4` and the Python standard library. The script is run from the repository root with `python hw03/hw03_executives.py`.
>
> **1. Identify yourself to the SEC on every request.** Use the headers dictionary `{"User-Agent": "MIS3060 Villanova ttobin01@villanova.edu"}` on *every* `requests.get()` call (submissions API and filing documents alike), with a timeout and a ~0.2-second pause between requests.
>
> **2. Find the Item 5.02 filings from the past 12 months.** Use the same five companies and CIKs as the earnings pipeline: Apple Inc. (AAPL, 0000320193), Microsoft Corporation (MSFT, 0000789019), NVIDIA Corporation (NVDA, 0001045810), JPMorgan Chase & Co. (JPM, 0000019617), Walmart Inc. (WMT, 0000104169). For each company, request `https://data.sec.gov/submissions/CIK{cik}.json` and loop over the parallel lists in `filings.recent`. Keep filings where the form is exactly `"8-K"` (skip `8-K/A` amendments, which re-report an event already filed), the `items` string contains `"5.02"` (Departure of Directors or Certain Officers; Election of Directors; Appointment of Certain Officers; Compensatory Arrangements), and the `filingDate` is on or after the date exactly 12 months before the day the script is run (compute this from today's date — do not hard-code it).
>
> **3. Download and read each filing.** The main 8-K document is at `https://www.sec.gov/Archives/edgar/data/{cik without leading zeros}/{accession without dashes}/{primaryDocument}`. Download it, strip the HTML to plain text with BeautifulSoup, and collapse whitespace. Isolate the Item 5.02 section — the text from the "Item 5.02" heading up to the next "Item X.XX" heading or the signature block — and extract from it:
> - **event_type** — `"departure"` (resign, retire, step down, depart, leave, not stand for re-election, terminate, cease to serve), `"appointment"` (appoint, elect, name, promote, join, succeed, become), or `"both"` when the same person is leaving one role and taking another in the same sentence (e.g., an officer who steps down as CFO and becomes a senior advisor, or a COO who is promoted to CEO).
> - **person_name** — the full name of the person the event is about (e.g., "Jeffrey Williams", "Jennifer Newstead"), typically the capitalized name that appears near the event verb or after "Mr."/"Ms.". Drop honorifics and trailing commas.
> - **title** — the role being left or taken (e.g., "Chief Financial Officer", "Senior Vice President and General Counsel", "member of the Board of Directors").
> - **effective_date** — the date the change takes effect, taken from phrases such as "effective January 1, 2026", "effective as of …", "on or about …", or "as of the close of …", converted to `YYYY-MM-DD`. If the text only gives a filing/notification date and no effective date, use `NOT_FOUND`.
> Any field the patterns cannot find is stored as the literal string `"NOT_FOUND"`, never blank.
>
> **4. One row per event.** A filing can report more than one event — for example one executive's departure and a successor's appointment, or two new directors. Split the Item 5.02 section into sentences, detect each distinct person/event, and create a **separate row for each event** (don't create duplicate rows for the same person and same event type mentioned in several sentences). If an Item 5.02 filing only describes compensation arrangements (a new equity award, pay plan or employment agreement) with no departure or appointment, print `[Ticker] | [Date] | no departure/appointment found (compensation-only 5.02) — no event row` and do not create a row.
>
> **5. Print each event as it is processed**, exactly: `[Ticker] | [Date] | [Event Type] | [Name] | [Title]` using the filing date, e.g., `AAPL | 2026-04-20 | departure | Jane Doe | Senior Vice President`.
>
> **6. Zero-event companies are valid data.** If a company has no Item 5.02 8-Ks in the past 12 months, print `[Ticker]: No executive events in past 12 months` and move on — this is a legitimate finding, not an error, and must not crash the script. Likewise, if any single filing fails to download or parse, print a warning and continue.
>
> **7. Save the results** to `hw03/executive_events.csv` (overwrite on each run) with exactly these columns in this order: `company`, `ticker`, `cik`, `filing_date`, `event_type`, `person_name`, `title`, `effective_date`. If no events at all are found, still write the file with just the header row. Finish by printing `Saved N events to hw03/executive_events.csv`.
>
> Organize the code into small, commented functions with a `main()` guarded by `if __name__ == "__main__":`.

## Prompt 3: Timeline prompt (→ `hw03/hw03_timeline.py`), sent verbatim from the assignment

> Write a Python script that reads `hw03/earnings_history.csv` and `hw03/executive_events.csv`. Do the following:
>
> 1. For each executive event in the events table, calculate the number of days between the executive event's `filing_date` and the nearest earnings filing date for the same company in the earnings table. Call this `days_to_nearest_earnings`.
> 2. Add a column `event_timing` that categorizes each executive event as: `'before earnings'` if the event came before the nearest earnings filing, `'after earnings'` if it came after, or `'same week'` if within 7 days of an earnings filing.
> 3. Save the combined table to `hw03/corporate_events_timeline.csv` with all columns from both source tables plus `days_to_nearest_earnings` and `event_timing`.
> 4. Print a summary: for each company, list any executive events and whether they occurred before or after the nearest earnings announcement.
> 5. Print a final count: how many events occurred before vs. after an earnings announcement across all five companies.

---

## Which companies' extractions required iteration

### Earnings pipeline (1 iteration, `period` field only)

- **Result of the first live run:** 20 of 20 rows, with **no `NOT_FOUND` values in any field**. So the assignment's fallback step for revenue (pasting 3,000 characters of raw text and asking for a better revenue regex) was not needed for any company.
- **What still needed fixing:** checking every row against its press release found two wrong `period` values:
  - **Apple (AAPL), 2025-10-30 filing:** extracted `fourth quarter of 2024` from a footnote; the correct value is `fiscal 2025 fourth quarter`.
  - **NVIDIA (NVDA), 2026-02-25 filing:** extracted `first quarter of fiscal 2027` from the Outlook section; the correct value is `Fourth Quarter and Fiscal 2026`.
- **Follow-up prompt:** *"`extract_period()` returned 'fourth quarter of 2024' for Apple's Q4 FY25 release (it matched a footnote) and 'first quarter of fiscal 2027' for NVIDIA's Q4 FY26 release, whose headline reads 'Fourth Quarter and Fiscal 2026'. Change it so that, among the patterns that name both a quarter and a year, it returns the match that appears earliest in the text, and add a pattern for '<ordinal> Quarter and Fiscal <year>'."*
- **Result:** both rows corrected; no other value changed. Before/after details are in `validation.md` §5A.

### Executive events pipeline (2 iterations)

- **Result of the first live run:** 26 rows, with no crashes. It correctly skipped the 3 compensation-only filings (MSFT, NVDA, JPM) and correctly split multi-person filings into separate rows.
- **Iteration 1 prompt (summarized):** *"Comparing the output with the filings: (1) Apple's 2026-04-20 filing says Tim Cook 'will transition from his role as Chief Executive Officer to Executive Chair', which was missed — treat 'transition from X to Y' as both. (2) People who are succeeded or whose duties transition away ('Mr. Borders succeeds Chris Kondo', 'a transition of duties from Kate Adams') should get a departure row. (3) 'Ms. Nora Johnson' produced a duplicate of 'Suzanne Nora Johnson'. (4) Resolve defined dates like 'effective September 1, 2026 (the "Transition Date")' so 'effective on the Transition Date' gets a date, and handle 'will become ... on March 1, 2026' and 'effective upon the commencement of his employment ... on May 4, 2026'. (5) Titles: stop at 'on <date>' and 'since', drop a trailing 'of Microsoft Corporation', and use 'resigned from the Board' as the title for board resignations."*
  - **Companies affected:**
    - **Apple:** Cook transition, Kondo, Adams, defined "Transition Date".
    - **NVIDIA:** Nora Johnson duplicate, Gawel and Parker dates, Drell title.
    - **Microsoft:** title cleanup.
    - **Walmart:** Furner succession, defined "Effective Date" for the Nicholas and Watkins dates.
- **Iteration 2 prompt (summarized):** *"Iteration 1 now reads NVIDIA's 'a seamless transition to his successor' (Ajay Puri) as an appointment — require 'transition to the role/position'. Also capture 'continue to serve as Controller until the close of business on January 31, 2026' as the effective date (Walmart, David Chojnowski), and keep multi-part titles such as 'Executive Vice President, President and Chief Executive Officer, Walmart U.S.' together across commas."*
  - **Companies affected:** **NVIDIA** and **Walmart**.
- **Final result:** 30 events. Every row was confirmed against the filing text (see `validation.md` §5B).
- **JPMorgan:** needed no fixes.

---

## One thing the generated script did that I would not have thought to specify

**The earnings script filters out segment-level and non-GAAP numbers before it accepts a match.**

- **What the generated `hw03_earnings.py` added:**
  - A `SEGMENT_WORDS` screen: "data center", "cloud", "iPhone", "services", "Walmart U.S.", "CCB", "noncontrolling", and so on.
  - A `NON_GAAP_WORDS` screen: "adjusted", "non-GAAP", "managed", "excluding", "core".
  - Each match is rejected if one of these words appears just before it.
- **Why that matters:** I only asked it to avoid the prior-year comparison figure. But these press releases put segment and adjusted figures right next to the headline numbers. NVIDIA's release has "Data Center revenue of $89.0 billion" in its second bullet. Walmart's says "GAAP EPS of $0.80; **Adjusted EPS** of $0.81". JPMorgan reports both "reported" and "managed" revenue.
- **Was it correct?** Yes.
  - I checked all 20 rows against the source text.
  - Every revenue, EPS and net-income value is the total-company GAAP/reported figure: NVIDIA $96.2B not $89.0B, Walmart EPS $0.80 not $0.81, JPMorgan reported revenue $57.3B not managed revenue $58.0B.
  - No adjustment was needed.

*Also noted:*

- **Generated timeline script:** it resolved an ambiguity in the prompt sensibly. Events within 7 days of earnings are labelled `same week` in preference to before/after, and the two `filing_date` columns are kept as `event_filing_date` and `earnings_filing_date`.
- **My adjustment to the timeline script:** the step-4 summary now still says "before"/"after" for same-week events (e.g., Walmart's CEO succession was 6 days *before* earnings). The final count now also reports distinct 8-K filings, since one filing can contain several events.
