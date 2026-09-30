"""
hw03_earnings.py - Build a quarterly earnings history for five companies from
their SEC Form 8-K (Item 2.02) earnings press releases.

Run from the repository root:
    python hw03/hw03_earnings.py

Output: hw03/earnings_history.csv (overwritten on every run).
Only requests + beautifulsoup4 + the standard library are used.
"""

import csv
import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# One headers dict, passed on EVERY requests.get() call. SEC EDGAR rejects
# requests that don't carry an identifying User-Agent.
HEADERS = {"User-Agent": "MIS3060 Villanova ttobin01@villanova.edu"}

REQUEST_PAUSE = 0.2      # seconds between requests (SEC limit is 10 req/sec)
REQUEST_TIMEOUT = 30     # seconds; used on every request
FILINGS_PER_COMPANY = 4  # the four most recent earnings 8-Ks
LEAD_CHARS = 5000        # "headline + first few paragraphs" search window
NOT_FOUND = "NOT_FOUND"

# Hard-coded companies and CIKs (10-digit, zero-padded) - not looked up.
COMPANIES = [
    {"company": "Apple Inc.", "ticker": "AAPL", "cik": "0000320193"},
    {"company": "Microsoft Corporation", "ticker": "MSFT", "cik": "0000789019"},
    {"company": "NVIDIA Corporation", "ticker": "NVDA", "cik": "0001045810"},
    {"company": "JPMorgan Chase & Co.", "ticker": "JPM", "cik": "0000019617"},
    {"company": "Walmart Inc.", "ticker": "WMT", "cik": "0000104169"},
]

# Paths are built from this script's own folder (hw03/), so the script works
# when run from the repo root as `python hw03/hw03_earnings.py`.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "earnings_history.csv")
CSV_DISPLAY_PATH = "hw03/earnings_history.csv"

CSV_COLUMNS = ["company", "ticker", "cik", "filing_date", "period",
               "revenue_reported", "eps_diluted", "net_income"]


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def sec_get(url):
    """GET a URL from SEC with the identifying headers, a timeout, and a pause.

    Retries once (after a longer wait) if SEC answers 429/503 (rate limited).
    Raises requests.RequestException on failure so callers can skip cleanly.
    """
    for attempt in range(2):
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        time.sleep(REQUEST_PAUSE)  # stay well under 10 requests/second
        if resp.status_code in (429, 503) and attempt == 0:
            time.sleep(2)
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------------------
# Step 2-3: find the four most recent earnings 8-Ks
# ---------------------------------------------------------------------------

def get_earnings_filings(cik, limit=FILINGS_PER_COMPANY):
    """Return up to `limit` newest 8-K filings whose items include 2.02."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    data = sec_get(url).json()
    recent = data.get("filings", {}).get("recent", {})

    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    items_list = recent.get("items", [])
    primary_docs = recent.get("primaryDocument", [])

    filings = []
    for i in range(len(forms)):
        items = items_list[i] if i < len(items_list) else ""
        # Exactly "8-K" (8-K/A amendments excluded) and Item 2.02 present.
        if forms[i] == "8-K" and "2.02" in (items or ""):
            filings.append({
                "filing_date": dates[i],
                "accession": accessions[i],
                "items": items,
                "primary_document": primary_docs[i] if i < len(primary_docs) else "",
            })
            if len(filings) == limit:  # list is newest-first already
                break
    return filings


# ---------------------------------------------------------------------------
# Step 4: locate and download the press-release exhibit
# ---------------------------------------------------------------------------

def filing_index_url(cik, accession):
    """Build the EDGAR filing index URL for an accession number."""
    cik_no_zeros = str(int(cik))
    acc_no_dashes = accession.replace("-", "")
    return (f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/"
            f"{acc_no_dashes}/{accession}-index.htm")


def _clean_href(href):
    """Turn an index-page link into an absolute document URL.

    Inline-XBRL documents are linked as /ix?doc=/Archives/...; strip that
    viewer prefix so we download the raw document.
    """
    if href.startswith("/ix?doc="):
        href = href[len("/ix?doc="):]
    return urljoin("https://www.sec.gov", href)


def find_exhibit_url(cik, accession):
    """Return the URL of the EX-99.1 press release, or None if not found."""
    resp = sec_get(filing_index_url(cik, accession))
    soup = BeautifulSoup(resp.content, "html.parser")

    # Collect (document name, type, url) from the document table(s).
    docs = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["th", "td"])]
        if "document" not in header or "type" not in header:
            continue
        doc_col, type_col = header.index("document"), header.index("type")
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(doc_col, type_col):
                continue
            link = cells[doc_col].find("a", href=True)
            if not link:
                continue
            url = _clean_href(link["href"])
            name = url.rsplit("/", 1)[-1]
            doc_type = cells[type_col].get_text(" ", strip=True).upper()
            docs.append((name, doc_type, url))

    htm_docs = [d for d in docs if re.search(r"\.html?$", d[0], re.I)]

    # 1st choice: Type is exactly EX-99.1 (also tolerate "EX-99.01").
    for name, doc_type, url in htm_docs:
        if re.fullmatch(r"EX-99\.0?1", doc_type):
            return url
    # 2nd choice: any EX-99.x exhibit.
    for name, doc_type, url in htm_docs:
        if doc_type.startswith("EX-99"):
            return url
    # 3rd choice: file name looks like an exhibit 99 (ex99, ex-99, ex991...).
    for name, doc_type, url in htm_docs:
        if re.search(r"ex-?99", name, re.I):
            return url
    return None


def fetch_text(url):
    """Download an exhibit and return it as whitespace-collapsed plain text."""
    resp = sec_get(url)
    soup = BeautifulSoup(resp.content, "html.parser")
    # Drop non-visible content (scripts, styles, hidden inline-XBRL header).
    for tag in soup(["script", "style", "ix:header"]):
        tag.decompose()
    text = soup.get_text(" ")
    text = text.replace("\xa0", " ")        # non-breaking spaces
    text = re.sub(r"\s+", " ", text)         # collapse all whitespace runs
    return text.strip()


# ---------------------------------------------------------------------------
# Step 5: regex extraction helpers
# ---------------------------------------------------------------------------

# A dollar amount with a written unit: "$109.4 billion", "$ 46,743 million",
# "$27.2B". Group 1 = number, group 2 = unit.
MONEY_WITH_UNIT = r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(billion|million|bn|mm|b|m)\b"

# A statement-table figure right after a row label: "$ 94,036", "7,026",
# "(141)". Requires thousands commas or a decimal so a bare year like "2025"
# is never mistaken for a value. Group 1 = "(" if negative, group 2 = number.
TABLE_NUMBER = r"\s*\$?\s*(\()?\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+)\s*\)?(?!\s*%)"

# Words that, if they appear right before a revenue / income phrase, mean the
# figure belongs to a segment or product line rather than the whole company.
SEGMENT_WORDS = re.compile(
    r"data center|gaming|professional visualization|automotive|segment|"
    r"cloud|productivity|personal computing|iphone|\bmac\b|ipad|wearables|"
    r"services|international|sam's club|walmart u\.s\.|e-?commerce|"
    r"advertising|consumer & community|\bccb\b|\bcib\b|commercial|"
    r"asset & wealth|\bawm\b|markets|investment banking|payments|"
    r"noncontrolling|non-controlling",
    re.I,
)

# Qualifiers that mean the figure is not the GAAP/reported number.
NON_GAAP_WORDS = re.compile(r"\badjusted\b|non-gaap|\bmanaged\b|\bexcluding\b|\bcore\b", re.I)


def to_millions(number_str, unit):
    """Convert '109.4' + 'billion' -> 109400 ; '46,743' + 'million' -> 46743."""
    value = float(number_str.replace(",", ""))
    unit = (unit or "million").lower()
    if unit in ("billion", "bn", "b"):
        value *= 1000
    value = round(value, 1)
    return int(value) if value.is_integer() else value


def _preceding(text, pos, width=30):
    """The `width` characters of text just before position `pos`."""
    return text[max(0, pos - width):pos]


def _search_money(patterns, scopes, exclude=None, qualifier_check=True):
    """Try each pattern in order on each scope; return value in $ millions.

    Each pattern must end in MONEY_WITH_UNIT (number, unit). A match is
    rejected if the text just before it (or the gap between keyword and $)
    names a segment, or labels the figure as adjusted/non-GAAP.
    """
    for scope in scopes:
        for pat in patterns:
            for m in re.finditer(pat, scope, re.I):
                context = _preceding(scope, m.start()) + m.group(0)
                if exclude is not None and exclude.search(context):
                    continue
                if qualifier_check and NON_GAAP_WORDS.search(_preceding(scope, m.start(), 25)):
                    continue
                return to_millions(m.group(1), m.group(2))
    return None


def _search_table(labels, text, unit_default="million"):
    """Find the first figure after a statement-table row label (in millions).

    The first number after the label is the current-quarter column, because
    press-release tables list the current period first.
    """
    for label in labels:
        m = re.search(label + TABLE_NUMBER, text, re.I)
        if m:
            value = to_millions(m.group(2), unit_default)
            return -value if m.group(1) else value
    return None


def extract_revenue(text):
    """Quarterly revenue in $ millions, or NOT_FOUND."""
    lead = text[:LEAD_CHARS]
    prose_patterns = [
        # "total revenue of $X billion" / "total net revenue was $X"
        r"total (?:net )?revenues? (?:of|was|were)\s*" + MONEY_WITH_UNIT,
        # JPMorgan: "Reported revenue of $44.9 billion"
        r"reported revenues?\b[^$]{0,40}?" + MONEY_WITH_UNIT,
        # "net revenue of $X" / "net revenues were $X"
        r"net revenues? (?:of|was|were)\s*" + MONEY_WITH_UNIT,
        # "Revenue for the quarter was $X" / "revenue for the fiscal quarter of $X"
        r"revenues? for the (?:fiscal )?quarter (?:was|were|of|totaled)\s*" + MONEY_WITH_UNIT,
        # "quarterly revenue of $X", "Consolidated revenue of $X",
        # "Revenue was $X", "reported revenue for the ... of $X" (NVIDIA)
        r"revenues? (?:of|was|were|totaled|reached|came in at)\s*" + MONEY_WITH_UNIT,
        r"reported revenues? for the [^$]{0,80}?\bof\s*" + MONEY_WITH_UNIT,
        # "net sales of $X" / "net sales were $X"
        r"net sales (?:of|was|were)\s*" + MONEY_WITH_UNIT,
        # Loosest: "revenue ... $X billion" within 60 characters
        # (e.g., "revenue grew 16% to $X billion").
        r"revenues?\b[^$]{0,60}?" + MONEY_WITH_UNIT,
    ]
    value = _search_money(prose_patterns, [lead, text], exclude=SEGMENT_WORDS)
    if value is not None:
        return value

    # Statement-table fallback: only labels that clearly mean total revenue.
    table_labels = [
        r"\bTotal net sales",                     # Apple
        r"\bTotal net revenues?",                 # banks / others
        r"\bTotal revenues?",                     # Microsoft, NVIDIA
        r"\bTotal revenues?,? net of interest expense",  # JPMorgan
        r"\bNet revenues?,? (?:-|–)?\s*reported",  # JPMorgan summary table
    ]
    value = _search_table(table_labels, text)
    return NOT_FOUND if value is None else value


def extract_eps(text):
    """Diluted EPS as a float (e.g., 2.02), or NOT_FOUND."""
    lead = text[:LEAD_CHARS]
    # Dollar-and-cents amount, optional parentheses for a loss: "$2.02", "$(0.12)"
    eps_num = r"\$\s?(\()?\s*(\d{1,3}\.\d{2,3})\)?"
    prose_patterns = [
        # "diluted earnings per share was $2.02" / "of $X" / "were $X"
        r"diluted earnings per (?:common )?share (?:was|were|of|came in at|totaled)\s*" + eps_num,
        # NVIDIA: "earnings per diluted share for the quarter were $1.08"
        r"earnings per diluted share\b[^$]{0,40}?" + eps_num,
        # "diluted EPS of $X" / "diluted EPS was $X"
        r"diluted EPS (?:was|were|of)\s*" + eps_num,
        # "EPS of $0.88" (Walmart GAAP EPS, JPMorgan)
        r"\bEPS (?:was|were|of)\s*" + eps_num,
        # "earnings per share of $5.24" / "was $X"
        r"earnings per (?:common )?share (?:was|were|of)\s*" + eps_num,
        # "$5.24 per share" / "($5.24 per diluted share)" - checked for 'dividend'
        eps_num + r"\s*per (?:diluted )?share",
    ]
    for scope in (lead, text):
        for pat in prose_patterns:
            for m in re.finditer(pat, scope, re.I):
                before = _preceding(scope, m.start(), 60)
                if NON_GAAP_WORDS.search(_preceding(scope, m.start(), 25)):
                    continue  # skip "Adjusted EPS of $X", "non-GAAP ..."
                if re.search(r"dividend|book value", before, re.I):
                    continue  # "$1.40 per share dividend" is not EPS
                value = float(m.group(2))
                return -value if m.group(1) else value

    # Statement-table fallback: "Diluted earnings per share $ 3.65" or the
    # "Diluted $ 1.64" row under "Earnings per share:". Requires cents
    # (\d.\d\d) so a diluted-share-count row is never picked up.
    for label in (r"\bDiluted earnings per (?:common )?share", r"\bDiluted net income per share",
                  r"\bDiluted"):
        m = re.search(label + r"\s*:?\s*\$?\s*(\()?\s*(\d{1,3}\.\d{2,3})\b\)?", text, re.I)
        if m:
            value = float(m.group(2))
            return -value if m.group(1) else value
    return NOT_FOUND


def extract_net_income(text):
    """Net income in $ millions, or NOT_FOUND."""
    lead = text[:LEAD_CHARS]
    prose_patterns = [
        # "consolidated net income attributable to Walmart of $X billion"
        r"(?:consolidated )?net income attributable to (?!non-?controlling)[^$]{1,40}?"
        r"(?:was|were|of|totaled)?\s*" + MONEY_WITH_UNIT,
        # "net income of $X billion" / "net income was $X billion" /
        # "reported net income of $X"
        r"(?:reported )?net income (?:of|was|were|totaled|came in at)\s*" + MONEY_WITH_UNIT,
        # Loose: "net income increased 12% to $X billion"
        r"net income\b[^$]{0,40}?" + MONEY_WITH_UNIT,
    ]
    value = _search_money(prose_patterns, [lead, text], exclude=SEGMENT_WORDS)
    if value is not None:
        return value

    # Statement-table fallback (figures in millions). The Walmart-style
    # "attributable to <company>" row is preferred over plain "Net income",
    # and the noncontrolling-interest row is explicitly skipped.
    table_labels = [
        r"\bConsolidated net income attributable to (?!non-?controlling)[A-Za-z.,&' ]{1,40}?",
        r"\bNet income attributable to (?!non-?controlling)[A-Za-z.,&' ]{1,40}?",
        r"\bNet income(?! per)(?! attributable)",
    ]
    value = _search_table(table_labels, text)
    return NOT_FOUND if value is None else value


def extract_period(text):
    """Reporting-period phrase as written (lightly cleaned), or NOT_FOUND."""
    lead = text[:LEAD_CHARS]
    ordinal = r"(?:first|second|third|fourth)"
    # Tier 1: phrases that name the quarter AND the (fiscal) year. Among these
    # we take the one that appears EARLIEST in the text (the headline / first
    # paragraph), not simply the first pattern that matches anywhere.
    # [Fix after first live run: Apple's Q4 FY25 release returned "fourth
    # quarter of 2024" from a footnote, and NVIDIA's Q4 FY26 release returned
    # "first quarter of fiscal 2027" from its Outlook section.]
    tier1 = [
        # "fourth quarter fiscal 2024", "second-quarter 2026",
        # "Second Quarter of Fiscal Year 2026"
        rf"\b{ordinal}[\s-]quarter(?:\s+of)?\s+(?:fiscal\s+(?:year\s+)?)?(?:19|20)\d{{2}}\b",
        # "fiscal 2026 third quarter", "fiscal year 2025 fourth quarter"
        rf"\bfiscal\s+(?:year\s+)?(?:19|20)\d{{2}}\s+{ordinal}[\s-]quarter\b",
        # NVIDIA year-end headline: "Fourth Quarter and Fiscal 2026"
        rf"\b{ordinal}[\s-]quarter\s+and\s+fiscal\s+(?:year\s+)?(?:19|20)\d{{2}}\b",
        # "Q2 FY27", "Q2 fiscal 2026", "Q4 FY 2025"
        r"\bQ[1-4]\s*(?:FY\s*'?\d{2,4}|fiscal\s+(?:year\s+)?(?:19|20)\d{2})\b",
    ]
    for scope in (lead, text):
        hits = [m for pat in tier1 for m in [re.search(pat, scope, re.I)] if m]
        if hits:
            first = min(hits, key=lambda m: m.start())
            return re.sub(r"\s+", " ", first.group(0)).strip(" ,.")

    # Tier 2: weaker descriptions, tried in priority order.
    patterns = [
        # "Q2 2026"
        r"\bQ[1-4]\s+(?:19|20)\d{2}\b",
        # JPMorgan shorthand: "2Q26" / "2Q 2026"
        r"\b[1-4]Q\s?(?:\d{2}|(?:19|20)\d{2})\b",
        # "fourth quarter ended June 30, 2025" (Microsoft-style)
        rf"\b{ordinal}[\s-]quarter\s+(?:ended|ending)\s+[A-Z][a-z]+\.?\s+\d{{1,2}},\s+(?:19|20)\d{{2}}",
        # "quarter ended June 30, 2025"
        r"\bquarter\s+(?:ended|ending)\s+[A-Z][a-z]+\.?\s+\d{1,2},\s+(?:19|20)\d{2}",
    ]
    for scope in (lead, text):
        for pat in patterns:
            m = re.search(pat, scope, re.I)
            if m:
                return re.sub(r"\s+", " ", m.group(0)).strip(" ,.")
    return NOT_FOUND


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def fmt_millions(value):
    """Format a $-millions value for the progress line."""
    return NOT_FOUND if value == NOT_FOUND else f"${value:,}M"


def fmt_eps(value):
    """Format EPS for the progress line."""
    return NOT_FOUND if value == NOT_FOUND else f"${value:.2f}"


def write_csv(rows, path=CSV_PATH):
    """Write all rows (overwriting any previous file)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            # Never write None / empty: anything missing becomes NOT_FOUND.
            writer.writerow({c: (NOT_FOUND if row.get(c) in (None, "") else row[c])
                             for c in CSV_COLUMNS})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_filing(company, filing):
    """Download one filing's press release and extract the four fields.

    Returns a CSV row dict, or None if the exhibit could not be retrieved.
    """
    ticker, cik, accession = company["ticker"], company["cik"], filing["accession"]
    try:
        exhibit_url = find_exhibit_url(cik, accession)
        if not exhibit_url:
            print(f"WARNING: {ticker} filing {accession}: press release exhibit not found — skipping")
            return None
        text = fetch_text(exhibit_url)
    except requests.RequestException as exc:
        print(f"WARNING: {ticker} filing {accession}: request failed ({exc}) — skipping")
        return None

    row = {
        "company": company["company"],
        "ticker": ticker,
        "cik": cik,
        "filing_date": filing["filing_date"],
        "period": NOT_FOUND,
        "revenue_reported": NOT_FOUND,
        "eps_diluted": NOT_FOUND,
        "net_income": NOT_FOUND,
    }
    # Each extractor is isolated so one unexpected error can't lose the row.
    for field, func in (("period", extract_period), ("revenue_reported", extract_revenue),
                        ("eps_diluted", extract_eps), ("net_income", extract_net_income)):
        try:
            row[field] = func(text)
        except Exception as exc:  # defensive: keep going, record NOT_FOUND
            print(f"WARNING: {ticker} filing {accession}: error extracting {field} ({exc})")
            row[field] = NOT_FOUND

    print(f"{ticker} | {row['period']} | Revenue: {fmt_millions(row['revenue_reported'])} | "
          f"EPS: {fmt_eps(row['eps_diluted'])} | Net Income: {fmt_millions(row['net_income'])}")
    return row


def main():
    rows = []
    for company in COMPANIES:
        try:
            filings = get_earnings_filings(company["cik"])
        except (requests.RequestException, ValueError) as exc:
            print(f"WARNING: {company['ticker']}: could not load submissions ({exc}) — skipping company")
            continue
        if not filings:
            print(f"WARNING: {company['ticker']}: no 8-K Item 2.02 filings found")
        for filing in filings:
            row = process_filing(company, filing)
            if row is not None:
                rows.append(row)

    write_csv(rows)
    print(f"Saved {len(rows)} rows to {CSV_DISPLAY_PATH}")


if __name__ == "__main__":
    main()
