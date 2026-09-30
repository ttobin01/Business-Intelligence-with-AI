#!/usr/bin/env python3
"""
hw03_executives.py - Executive and director departures/appointments from SEC 8-K filings.

For five large companies, this script:
  1. Pulls each company's filing index from the SEC submissions API.
  2. Keeps original Form 8-K filings (no 8-K/A) from the past 12 months whose
     items include 5.02 (Departure/Election/Appointment of Directors or Officers).
  3. Downloads each filing's main document, isolates the Item 5.02 section, and
     extracts one row per person/event: event_type, person_name, title,
     effective_date (fields that cannot be found are stored as "NOT_FOUND").
  4. Writes hw03/executive_events.csv (overwritten on every run).

Run from the repository root:
    python hw03/hw03_executives.py

Only requests, beautifulsoup4 and the Python standard library are used.
"""

import calendar
import csv
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# The SEC requires a descriptive User-Agent on EVERY request.
HEADERS = {"User-Agent": "MIS3060 Villanova ttobin01@villanova.edu"}
REQUEST_TIMEOUT = 30          # seconds per request
PAUSE_SECONDS = 0.2           # polite pause after every request (SEC limit is 10/sec)
MAX_ATTEMPTS = 3              # retries for rate-limit / temporary server errors

NOT_FOUND = "NOT_FOUND"

# Same five companies and CIKs as the earnings pipeline.
COMPANIES = [
    {"company": "Apple Inc.", "ticker": "AAPL", "cik": "0000320193"},
    {"company": "Microsoft Corporation", "ticker": "MSFT", "cik": "0000789019"},
    {"company": "NVIDIA Corporation", "ticker": "NVDA", "cik": "0001045810"},
    {"company": "JPMorgan Chase & Co.", "ticker": "JPM", "cik": "0000019617"},
    {"company": "Walmart Inc.", "ticker": "WMT", "cik": "0000104169"},
]

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

OUTPUT_DIR = Path("hw03")                       # relative to the repo root (cwd)
OUTPUT_FILE = OUTPUT_DIR / "executive_events.csv"
CSV_COLUMNS = ["company", "ticker", "cik", "filing_date", "event_type",
               "person_name", "title", "effective_date"]

# ---------------------------------------------------------------------------
# Regular expressions used by the extraction functions
# ---------------------------------------------------------------------------

# Departure verbs: resign, retire, step down, depart, leave, not stand for
# re-election, terminate (employment), cease to serve.
DEPARTURE_RE = re.compile(
    r"\b(?:resign(?:s|ed|ing)?"
    r"|retir(?:e|es|ed|ing)"
    r"|step(?:s|ped|ping)?\s+down"
    r"|depart(?:s|ed|ing)?"
    r"|leav(?:e|es|ing)|left\s+the\s+(?:Company|Board)"
    r"|not\s+(?:\w+\s+){0,3}?(?:stand|seek|run)\s+for\s+re-?election"
    r"|terminat(?:e|es|ed|ing)\s+(?:(?:his|her|their|the)\s+)?(?:employment|service)"
    r"|(?:was|were|has\s+been|have\s+been|will\s+be)\s+terminated"
    r"|employment\s+(?:\w+\s+){0,6}?(?:will\s+)?terminat(?:e|es|ed|ing)"
    r"|ceas(?:e|es|ed|ing)\s+to\s+(?:serve|be)"
    # [Iteration 1] role transitions: "will transition from his role as CEO",
    # "a transition of duties from Kate Adams", "continue to serve as ... until
    # <date>", "separate from employment".
    r"|transition(?:s|ed|ing)?\s+(?:of\s+(?:his|her|their|its)?\s*(?:duties|responsibilities)\s+)?from"
    r"|continu(?:e|es|ing)\s+to\s+serve\s+as\s+[^.;]{0,160}?\buntil"
    r"|separat(?:e|es|ed|ing)\s+from\s+(?:employment|the\s+Company))\b",
    re.IGNORECASE,
)

# Appointment verbs: appoint, elect, name, promote, join, succeed, become.
# Look-aheads exclude common non-event uses ("elect to defer", "named executive
# officers", "become vested/effective").
APPOINTMENT_RE = re.compile(
    r"\b(?:appoint(?:s|ed|ing)?"
    r"|(?:re-)?elect(?:s|ed|ing)?(?!\s+(?:not\s+)?to\s+(?!the\b|serve\b|its\b|our\b|a\b|an\b))"
    r"|nam(?:ed|es|ing)(?!\s+executive\s+officers?)"
    r"|promot(?:e|es|ed|ing)"
    r"|join(?:s|ed|ing)?"
    r"|succeed(?:s|ed|ing)?"
    r"|transition(?:s|ed|ing)?\s+to\s+(?:the|a|an|his|her|their)\s+(?:new\s+)?(?:role|position)"  # [Iteration 1-2]
    r"|(?:becom(?:e|es|ing)|became)(?!\s+(?:effective|vested|exercisable|payable|eligible|"
    r"entitled|due|subject|a\s+party)))\b",
    re.IGNORECASE,
)

# Active, transitive appointment verbs ("the Board appointed Jane Roe").
TRANSITIVE_RE = re.compile(r"^(?:appoint|elect|re-elect|nam|promot)", re.IGNORECASE)

PRONOUN_RE = re.compile(r"\b(?:he|she|his|her|him|they|their|them)\b", re.IGNORECASE)

# Sentences describing a hypothetical/conditional event (vesting, severance)
# rather than an actual departure or appointment.
CONDITIONAL_RE = re.compile(
    r"\b(?:if|in\s+the\s+event|vest(?:s|ing|ed)?|severance|change\s+(?:in|of)\s+control"
    r"|provided\s+that|qualifying\s+termination"
    r"|upon\s+(?:a|an|his|her|their|such|the)?\s*(?:involuntary\s+)?termination)\b",
    re.IGNORECASE,
)

# Biographical boilerplate ("Mr. Roe, 52, has served as ... since 2019").
BIO_RE = re.compile(
    r"\b(?:prior\s+to\s+(?:joining|that|this|his|her)|since\s+(?:19|20)\d{2}"
    r"|from\s+(?:19|20)\d{2}\s+(?:to|until|through)|in\s+(?:19|20)\d{2}"
    r"|family\s+relationships?|arrangements?\s+or\s+understandings?|Item\s+404"
    r"|biograph\w*|,\s*age\s+\d{2}|,\s*\d{2}\s*,)",
    re.IGNORECASE,
)
# Words showing a sentence is about the current event, even if it has bio text.
CURRENT_RE = re.compile(
    r"\b(?:effective|will|informed|notified|notice|intention|intends?|decided|decision|plans?\s+to)\b",
    re.IGNORECASE,
)

# Compensation vocabulary (used to label compensation-only 5.02 filings).
COMPENSATION_RE = re.compile(
    r"\b(?:compensat\w*|equity|awards?|grant\w*|restricted\s+stock|RSUs?|stock\s+units?"
    r"|options?|salary|bonus\w*|incentive|severance|employment\s+agreement|retention|plan)\b",
    re.IGNORECASE,
)

# Dates such as "January 1, 2026", "Sept. 30 2025", "June 1st, 2026".
MONTH_PATTERN = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?"
                 r"|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
DATE_PATTERN = (rf"(?P<mon>{MONTH_PATTERN})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<year>\d{{4}})")
MONTH_NUMBERS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}

# Effective-date phrases: "effective January 1, 2026", "effective as of ...",
# "on or about ...", "as of the close of business on ...".
BRIDGE_WORDS = (r"(?:as|of|the|close|end|start|beginning|opening|business|trading|day"
                r"|on|at|following|after|upon|market|regular|hours|session)")
WEEKDAY = r"(?:(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,?\s+)"
EFFECTIVE_DATE_RE = re.compile(
    rf"\b(?:effective|as\s+of|on\s+or\s+about)(?:\s+{BRIDGE_WORDS}){{0,8}},?\s+{WEEKDAY}?{DATE_PATTERN}",
    re.IGNORECASE,
)

# [Iteration 1] Extra effective-date phrasings seen in the live filings:
#   "will become Apple's general counsel on March 1, 2026"
#   "effective upon the commencement of his employment with the Company on May 4, 2026"
FUTURE_ON_DATE_RE = re.compile(
    rf"\bwill\s+(?:\S+\s+){{0,8}}?on\s+{WEEKDAY}?{DATE_PATTERN}", re.IGNORECASE)
EFFECTIVE_UPON_RE = re.compile(
    rf"\beffective\s+upon\s+(?:\S+\s+){{0,14}}?on\s+{WEEKDAY}?{DATE_PATTERN}", re.IGNORECASE)
# [Iteration 2] "will continue to serve as Controller until the close of business on January 31, 2026"
CONTINUE_UNTIL_RE = re.compile(
    rf"\bcontinu\w*\s+to\s+serve\s+as\s+[^.;]{{0,160}}?\buntil\s+(?:the\s+close\s+of\s+business\s+(?:on\s+)?)?"
    rf"{WEEKDAY}?{DATE_PATTERN}", re.IGNORECASE)
# A defined date term: "effective September 1, 2026 (the “Transition Date”)".
DEFINED_DATE_RE = re.compile(
    rf"{DATE_PATTERN}\s*\(\s*(?:the\s+)?[“\"](?P<term>[A-Z][A-Za-z ]{{1,40}}?Date)[”\"]\s*\)")

# Words that introduce a title: "as", "to become", "appointed", "from his position as" ...
TITLE_ANCHOR_RE = re.compile(
    r"\b(?:to\s+serve\s+as|to\s+be|to\s+become|become|became"
    r"|(?:to|in)\s+the\s+(?:position|role|office|post)s?\s+of"
    r"|from\s+(?:his|her|their|the)\s+(?:positions?|roles?|posts?|offices?)\s+(?:as|of)"
    r"|promot(?:e|es|ed|ing)\s+[^,.;]+,[^;]*?,\s+to"          # "promoted Jane Roe, <old title>, to <new>"
    r"|(?:appointed|elected|re-elected|named|promoted)(?:\s+to)?(?:\s+the\s+(?:position|role|office)\s+of)?"
    r"|(?:to|from)(?=\s+(?:the|its|our)\s+(?:Company['’]s\s+)?Board\b)"  # "elected to / resigned from the Board"
    r"|as)\s+",
    re.IGNORECASE,
)
COMPANY_WORDS = r"(?:Apple|Microsoft|NVIDIA|Nvidia|JPMorgan|JPMorgan\s+Chase|Walmart)"
# Where a title stops (punctuation, "effective", "and will", "of the Company" ...).
TITLE_STOP = (
    r"(?=\s*[;:()]|\s*,(?!\s+(?:President|Chief|Executive|Senior|Vice|Worldwide|Treasurer|General"
    r"|Walmart|Sam['’]s)\b)|\.(?:\s|$)|\s+(?:effective|as\s+of|on\s+or\s+about|beginning|commencing|upon"
    r"|until|following|after|before|to\s+succeed|succeeding|replacing|who|which|where|while|since"
    rf"|on\s+(?:the|or|{MONTH_PATTERN})"
    r"|in\s+connection|for\s+a\s+term|to\s+pursue|to\s+focus|to\s+spend|in\s+order|at\s+the\s+(?:close|end)"
    r"|and\s+(?:will|has|is|was|to|he|she|they|his|her|Mr\.|Ms\.|Mrs\.|Dr\.|the\s+Board|the\s+Company"
    r"|as|became|become|continue|remain)"
    rf"|(?:of|at|with|within|for)\s+(?:the\s+Company|the\s+Registrant|{COMPANY_WORDS}|us))\b|$)"
)
TITLE_BODY_RE = re.compile(rf"(?P<t>.{{2,120}}?){TITLE_STOP}", re.IGNORECASE)
TITLE_KEYWORD_RE = re.compile(
    r"\b(?:officer|president|director|counsel|chair\w*|secretary|treasurer|controller|board"
    r"|head|lead|chief|member|partner|advis[eo]r|principal|manager|executive|CEO|CFO|COO|CTO"
    r"|CAO|CIO|CHRO|trustee|committee)\b",
    re.IGNORECASE,
)
TITLE_BAD_WORDS_RE = re.compile(
    r"\b(?:will|has|have|had|is|was|were|intention|informed|notified|decided|agreed|announced"
    r"|appointed|elected|named|promoted|resigned|retired|previously|result|described|disclosed"
    r"|who|whose|promotion|continue)\b",
    re.IGNORECASE,
)
DIRECTOR_TITLE_RE = re.compile(
    r"(?:(?:a\s+)?member\s+of\s+)?(?:the\s+)?(?:Company['’]s\s+)?Board(?:\s+of\s+Directors)?"
    r"|(?:an?\s+)?(?:independent\s+|non-employee\s+|new\s+)?director",
    re.IGNORECASE,
)

# Person names: runs of capitalized tokens ("Jane Doe", "J. Scott Kirby", "Mary O'Brien").
NAME_TOKEN = r"(?:[A-Z]\.|[A-Z][A-Za-z'’\-]*[a-z](?:['’]s)?)"
NAME_RUN_RE = re.compile(rf"\b{NAME_TOKEN}(?:\s+{NAME_TOKEN})*")
NAME_TOKEN_RE = re.compile(NAME_TOKEN)
HONORIFIC_RE = re.compile(rf"\b(?:Mr|Ms|Mrs|Dr)\.\s+(?P<name>{NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,3}})")
SUFFIX_RE = re.compile(r"^,?\s+(Jr\.|Sr\.|II|III|IV)(?![A-Za-z])")

# Capitalized words that are never part of a person's name.
NON_NAME_WORDS = set("""
Mr Ms Mrs Dr Jr Sr The This That These Those On In As At By For From To Of With Following
Effective Pursuant Also After Before During Upon Under Until While When Where Which Who Whom
Additionally Accordingly Further Furthermore Subsequently Thereafter Currently Previously
Separately Concurrently Consequently Today Such Each Any All Both New Former Interim Acting
He She His Her They Their It Its Our We Us I
Company Companies Corporation Corp Inc Co Ltd LLC LLP Holdings Group Registrant
Apple Microsoft Nvidia NVIDIA JPMorgan Chase Walmart Sam Sam's Club Bank Banking
Board Boards Directors Director Committee Committees Compensation Management Development
Nominating Governance Corporate Audit Risk Human Resources Capital People Talent
Chief Executive Financial Operating Officer Officers Accounting Technology Legal Principal
Senior Vice President Presidents General Counsel Secretary Treasurer Controller Chairman
Chair Chairwoman Chairperson Lead Independent Head Global Worldwide International Americas
Operations Retail Marketing Services Software Hardware Engineering Cloud Business Division
Segment Consumer Commercial Investment Asset Wealth Community Enterprise Strategy Strategic
Advisor Adviser Special Member Members Partner Partners Product Products Sales Research
Item Items Form Section Securities Exchange Act Commission Agreement Agreements Plan Plans
Stock Equity Incentive Award Awards Annual Meeting Shareholders Stockholders Report Exhibit
Current Restricted Units Unit Performance Share Shares Proxy Statement Departure Election
Appointment Appointments Arrangements Compensatory Certain Fiscal Year Quarter Press Release
Letter Offer Employment Retirement Resignation Transition Regulation Rule United States
America Delaware California Washington New York Arkansas Santa Clara Redmond Cupertino
Bentonville Street Avenue Way Park Drive Road Signature Signatures Date Dated Name Title
January February March April May June July August September October November December
Jan Feb Mar Apr Jun Jul Aug Sep Sept Oct Nov Dec
Monday Tuesday Wednesday Thursday Friday Saturday Sunday
""".split())


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def sec_get(url):
    """GET a URL from the SEC with the required User-Agent, a timeout and a pause.

    Retries a couple of times on rate-limit (429) or temporary server errors.
    Raises requests.RequestException if the request ultimately fails.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            time.sleep(PAUSE_SECONDS)
            if attempt == MAX_ATTEMPTS:
                raise
            time.sleep(attempt)          # brief back-off before retrying
            continue
        time.sleep(PAUSE_SECONDS)        # polite pause after every request
        if response.status_code in (429, 500, 502, 503, 504) and attempt < MAX_ATTEMPTS:
            time.sleep(attempt * 2)      # back off, then retry
            continue
        response.raise_for_status()
        return response
    raise requests.RequestException(f"Failed to fetch {url}")


# ---------------------------------------------------------------------------
# Step 2: find Item 5.02 8-K filings from the past 12 months
# ---------------------------------------------------------------------------

def twelve_months_ago(today):
    """Return the date exactly 12 months before `today` (Feb 29 -> Feb 28)."""
    year = today.year - 1
    last_day = calendar.monthrange(year, today.month)[1]
    return date(year, today.month, min(today.day, last_day))


def find_502_filings(cik, cutoff):
    """Return a list of Item 5.02 Form 8-K filings (dicts) filed on/after `cutoff`."""
    data = sec_get(SUBMISSIONS_URL.format(cik=cik)).json()
    recent = data.get("filings", {}).get("recent", {})

    # filings.recent is a set of parallel lists - walk them together by index.
    forms = recent.get("form", [])
    items_list = recent.get("items", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    documents = recent.get("primaryDocument", [])

    filings = []
    for i in range(len(forms)):
        form = forms[i]
        items = items_list[i] if i < len(items_list) else ""
        filing_date = dates[i] if i < len(dates) else ""
        if form != "8-K":                         # exact match: skips 8-K/A
            continue
        if "5.02" not in (items or ""):
            continue
        try:
            if date.fromisoformat(filing_date) < cutoff:
                continue
        except ValueError:
            continue
        filings.append({
            "filing_date": filing_date,
            "accession": accessions[i] if i < len(accessions) else "",
            "document": documents[i] if i < len(documents) else "",
        })
    return filings


# ---------------------------------------------------------------------------
# Step 3: download a filing and isolate the Item 5.02 section
# ---------------------------------------------------------------------------

def filing_document_url(cik, accession, document):
    """Build the Archives URL of a filing's primary document."""
    return ARCHIVE_URL.format(cik=int(cik), accession=accession.replace("-", ""),
                              document=document)


def html_to_text(html_bytes):
    """Strip HTML to plain text and collapse all whitespace to single spaces."""
    soup = BeautifulSoup(html_bytes, "html.parser")
    # Remove non-visible content (scripts, styles, hidden inline-XBRL header).
    for tag in soup.find_all(["script", "style", "head", "ix:header"]):
        tag.decompose()
    text = soup.get_text(" ")
    text = text.replace("\xa0", " ").replace("\u200b", " ")  # zero-width spaces
    return re.sub(r"\s+", " ", text).strip()


def extract_item_502(text):
    """Return the Item 5.02 section text (without its heading), or "" if not found.

    The section runs from the "Item 5.02" heading to the next "Item X.XX"
    heading or the signature block, whichever comes first.
    """
    starts = list(re.finditer(r"\bItem\s*5\.02\b", text, re.IGNORECASE))
    if not starts:
        return ""
    # Prefer an occurrence that looks like a heading (followed by "Departure ...").
    start = starts[0]
    for m in starts:
        if re.match(r"\.?\s*[:\-–—]?\s*Departure", text[m.end():m.end() + 20], re.IGNORECASE):
            start = m
            break

    rest = text[start.end():]
    end_positions = [len(rest)]
    # Next item heading ("Item 9.01"), but not cross-references like "Item 5.02(c)" / "Item 401 of".
    next_item = re.search(r"\bItem\s*\d{1,2}\.\d{2}\b(?!\s*\()(?!\s+of\b)", rest, re.IGNORECASE)
    if next_item:
        end_positions.append(next_item.start())
    for pattern in (r"\bSIGNATURES?\b",
                    r"\bPursuant to the requirements of the Securities Exchange Act"):
        m = re.search(pattern, rest)
        if m:
            end_positions.append(m.start())
    section = rest[:min(end_positions)]

    # Drop the standard heading so words like "Departure"/"Election" are not read as events.
    section = re.sub(
        r"^\s*\.?\s*[:\-–—]?\s*Departure of Directors[^.]{0,250}?"
        r"(?:Compensatory Arrangements of Certain Officers|Certain Officers)\.?",
        "", section, count=1, flags=re.IGNORECASE)
    return section.strip()


# ---------------------------------------------------------------------------
# Step 4 helpers: sentences, names, titles and dates
# ---------------------------------------------------------------------------

ABBREVIATIONS = ["Mr", "Ms", "Mrs", "Dr", "Jr", "Sr", "Inc", "Corp", "Co", "Ltd", "No",
                 "St", "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Sept",
                 "Oct", "Nov", "Dec", "vs", "etc", "U.S", "U.K"]


def split_sentences(text):
    """Split text into sentences without breaking on "Mr.", "Inc.", initials, etc."""
    protected = text
    for abbr in ABBREVIATIONS:
        protected = re.sub(rf"\b{re.escape(abbr)}\.", abbr.replace(".", "<DOT>") + "<DOT>", protected)
    protected = re.sub(r"\b([A-Z])\.", r"\1<DOT>", protected)          # initials: "J. Scott"
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"“(])", protected)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


def _clean_token(token):
    """Remove a possessive "'s" and trailing period from a name token."""
    return re.sub(r"['’]s$", "", token).rstrip(".")


def _name_groups(run_text, offset):
    """Split a run of capitalized tokens into candidate full names (2-4 tokens)."""
    groups, current = [], []
    for tm in NAME_TOKEN_RE.finditer(run_text):
        token = tm.group(0)
        if _clean_token(token) in NON_NAME_WORDS:
            if current:
                groups.append(current)
            current = []
        else:
            current.append((offset + tm.start(), offset + tm.end(), token))
    if current:
        groups.append(current)

    names = []
    for group in groups:
        # Skip single words, and names that end in (or are only) initials.
        if len(group) < 2 or len(group) > 4 or group[-1][2].endswith("."):
            continue
        names.append(group)
    return names


def find_full_names(sentence):
    """Return [(start, end, "First Last")] for full names found in a sentence."""
    results = []
    for run in NAME_RUN_RE.finditer(sentence):
        for group in _name_groups(run.group(0), run.start()):
            start, end = group[0][0], group[-1][1]
            name = " ".join(_clean_token(t) if i == len(group) - 1 else t
                            for i, (_, _, t) in enumerate(group))
            suffix = SUFFIX_RE.match(sentence[end:])
            if suffix and not group[-1][2].endswith(("'s", "’s")):
                name += " " + suffix.group(1)
                end += suffix.end()
            results.append((start, end, name))
    return results


def build_surname_map(sentences):
    """Map each surname to the full name it belongs to (so "Mr. Doe" -> "Jane Doe")."""
    surname_map = {}
    for sentence in sentences:
        for _, _, name in find_full_names(sentence):
            parts = [p for p in name.split() if p not in ("Jr.", "Sr.", "II", "III", "IV")]
            surname_map.setdefault(parts[-1], name)
    return surname_map


def find_people(sentence, surname_map):
    """Return person mentions in a sentence as a sorted list of (start, end, full_name)."""
    mentions = []
    # "Mr./Ms./Mrs./Dr. Name" - honorific is dropped from the stored name.
    for m in HONORIFIC_RE.finditer(sentence):
        tokens = [t for t in m.group("name").split()]
        kept = []
        for t in tokens:
            if _clean_token(t) in NON_NAME_WORDS:
                break
            kept.append(t)
        if not kept:
            continue
        end = m.start("name") + len(" ".join(kept))
        cleaned = [_clean_token(t) if i == len(kept) - 1 else t for i, t in enumerate(kept)]
        if len(cleaned) == 1:
            name = surname_map.get(cleaned[0], cleaned[0])
        else:
            name = " ".join(cleaned)
            # [Iteration 1] "Ms. Nora Johnson" is the same person as "Suzanne Nora
            # Johnson" - use the full name so one person doesn't become two rows.
            full = surname_map.get(cleaned[-1])
            if full and full != name and full.endswith(" " + name):
                name = full
        mentions.append((m.start(), end, name))
    # Plain full names ("Jane Doe") that do not overlap an honorific mention.
    for start, end, name in find_full_names(sentence):
        if not any(s <= start < e or start <= s < end for s, e, _ in mentions):
            mentions.append((start, end, name))
    return sorted(mentions)


def parse_month_date(match):
    """Convert a DATE_PATTERN match into "YYYY-MM-DD" (or None if invalid)."""
    month = MONTH_NUMBERS.get(match.group("mon")[:3].lower())
    try:
        return datetime(int(match.group("year")), month, int(match.group("day"))).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def find_effective_date(text):
    """Return the first effective date in text as YYYY-MM-DD, or None."""
    for regex in (EFFECTIVE_DATE_RE, EFFECTIVE_UPON_RE, CONTINUE_UNTIL_RE, FUTURE_ON_DATE_RE):
        for m in regex.finditer(text):
            parsed = parse_month_date(m)
            if parsed:
                return parsed
    return None


def resolve_defined_dates(section):
    """Replace later uses of a defined date ("the Transition Date") with the date itself.

    [Iteration 1] Apple and Walmart define a date once - "effective September 1,
    2026 (the “Transition Date”)" - and then say "effective on the Transition
    Date". Substituting the real date lets the normal date patterns find it.
    """
    for m in DEFINED_DATE_RE.finditer(section):
        date_text = f"{m.group('mon')} {m.group('day')}, {m.group('year')}"
        term = re.escape(m.group("term"))
        section = re.sub(rf"\b(?:the\s+)?{term}\b(?![”\"])", date_text, section)
    return section


def clean_title(raw, person_names):
    """Tidy a candidate title and return it, or None if it does not look like a title."""
    title = raw.strip(" ,;:.")
    prefix = re.compile(
        rf"^(?:the\s+Company['’]s|the\s+Registrant['’]s|{COMPANY_WORDS}(?:\s+Inc\.?)?['’]s"
        r"|its|our|his|her|their|the|a|an|new)\s+", re.IGNORECASE)
    while prefix.match(title):
        title = prefix.sub("", title, count=1)
    title = title.strip(" ,;:.")
    # [Iteration 1] "member of the Board of Directors of Microsoft Corporation" -> drop the company.
    title = re.sub(rf"\s+(?:of|at)\s+(?:the\s+Company|{COMPANY_WORDS}(?:\s+(?:Inc|Corporation|Corp|Co)\.?)?)$",
                   "", title, flags=re.IGNORECASE).strip(" ,;:.")
    if not title or not title[0].isalpha():
        return None
    words = title.split()
    if len(words) > 14 or not TITLE_KEYWORD_RE.search(title) or TITLE_BAD_WORDS_RE.search(title):
        return None
    if re.search(r"\b(?:Mr|Ms|Mrs|Dr)\.", title):
        return None
    for name in person_names:
        if name and name.split()[-1] in words:
            return None
    if DIRECTOR_TITLE_RE.fullmatch(title):
        return "member of the Board of Directors"
    return title


def find_title(window, mention, sentence, person_names):
    """Find the role being left or taken, searching around one person's event.

    Order: (1) a title introduced by "as"/"appointed"/"to become"... in the
    event window; (2) an appositive after the name ("Jane Doe, Senior Vice
    President,"); (3) a title just before the name ("the Company's CFO, Jane Doe").
    """
    for anchor in TITLE_ANCHOR_RE.finditer(window):
        body = TITLE_BODY_RE.match(window[anchor.end():])
        if body:
            title = clean_title(body.group("t"), person_names)
            if title:
                return title
    if mention is not None:
        start, end, _ = mention
        appositive = re.match(
            r"\s*,\s*(?:\d{1,3}\s*,\s*)?(?:(?:who\s+)?(?:is\s+|was\s+|has\s+been\s+|currently\s+"
            r"|serves\s+as\s+|served\s+as\s+)+)?(?P<t>[^,;()]{2,100}?)(?=\s*[,;()]|\.\s|\.$|$)",
            sentence[end:])
        if appositive:
            title = clean_title(appositive.group("t"), person_names)
            if title:
                return title
        before = re.search(
            r"(?:the\s+Company['’]s|its|our|the)\s+(?P<t>[A-Z][A-Za-z&'’\-]*"
            r"(?:\s+(?:[A-Z][A-Za-z&'’\-]*|and|of|&|for|the))*)\s*,?\s*$",
            sentence[:start])
        if before:
            title = clean_title(before.group("t"), person_names)
            if title:
                return title
    return None


def skip_sentence(sentence):
    """True for conditional (vesting/severance) or biographical sentences."""
    if CONDITIONAL_RE.search(sentence):
        return True
    return bool(BIO_RE.search(sentence)) and not CURRENT_RE.search(sentence)


def find_event_verbs(sentence):
    """Return [(start, end, event_type, verb_text)] for event verbs in a sentence."""
    verbs = []
    for pattern, kind in ((DEPARTURE_RE, "departure"), (APPOINTMENT_RE, "appointment")):
        for m in pattern.finditer(sentence):
            before = sentence[max(0, m.start() - 15):m.start()]
            # "Prior to joining ...", "since joining ..." describe history, not the event.
            if re.search(r"(?:prior\s+to|before|since|after|upon)\s+$", before, re.IGNORECASE):
                continue
            # Past-tense verbs inside a ", who ..." clause are biography ("who joined in 2015").
            clause = re.search(r",\s*who\s+[^,;]*$", sentence[:m.start()], re.IGNORECASE)
            verb = m.group(0)
            if clause and re.search(r"(?:ed|became|left)\b", verb.split()[0] if " " in verb else verb,
                                    re.IGNORECASE):
                continue
            verbs.append((m.start(), m.end(), kind, verb))
    # [Iteration 1] "will transition from his role as CEO to Executive Chair": the
    # "to <Title>" part is the new role, so record an appointment there too.
    for m in re.finditer(r"\btransition(?:s|ed|ing)?\s+from\s+[^.;]{0,150}?\s(to)\s+(?=[A-Z])",
                         sentence, re.IGNORECASE):
        verbs.append((m.start(1), m.end(1), "appointment", m.group(1)))
    # Drop overlapping matches (keep the earliest / longest).
    verbs.sort(key=lambda v: (v[0], -(v[1] - v[0])))
    cleaned = []
    for v in verbs:
        if cleaned and v[0] < cleaned[-1][1]:
            continue
        cleaned.append(v)
    return cleaned


def _with_coordinated(sentence, first, mentions):
    """Extend one mention to a list: "Alice Brown and Robert Green" -> both mentions."""
    group = [first]
    for mention in mentions:
        if mention[0] > group[-1][1] and re.fullmatch(r"\s*(?:,\s*(?:and\s+)?|and\s+)",
                                                       sentence[group[-1][1]:mention[0]]):
            group.append(mention)
        elif mention[0] > group[-1][1]:
            break
    return group


def assign_people(sentence, verb, mentions):
    """Pick the mention(s) (start, end, name) an event verb is about ([] if none)."""
    vstart, vend, _, vtext = verb
    # Active voice: "the Board appointed Jane Roe (and John Poe)" -> people right after the verb.
    if TRANSITIVE_RE.match(vtext):
        for mention in mentions:
            if mention[0] >= vend and sentence[vend:mention[0]].strip() == "":
                return _with_coordinated(sentence, mention, mentions)
    # [Iteration 1] "a transition of duties from Kate Adams" -> the person after "from".
    if re.search(r"from$", vtext, re.IGNORECASE):
        for mention in mentions:
            if mention[0] >= vend and sentence[vend:mention[0]].strip() == "":
                return [mention]
    # Passive with agent: "... will be succeeded by Jane Roe".
    for mention in mentions:
        if mention[0] >= vend and re.fullmatch(r"\s+by\s+", sentence[vend:mention[0]]):
            return [mention]
    # Otherwise the nearest person named before the verb (the subject) ...
    preceding = [m for m in mentions if m[1] <= vstart]
    if preceding:
        return [preceding[-1]]
    # ... or, failing that, the first person named after it.
    following = [m for m in mentions if m[0] >= vend]
    return [following[0]] if following else []


def event_window(sentence, start, mention, mentions, group_names=()):
    """Text from the event (verb or name) up to the next different person's mention.

    People in `group_names` (co-appointees listed together) do not end the window,
    so "elected Alice Brown and Robert Green to the Board" gives both the title.
    """
    anchor_end = max(start, mention[1]) if mention else start
    window_start = min(start, mention[0]) if mention else start
    same = set(group_names) | ({mention[2]} if mention else set())
    end = len(sentence)
    for m in mentions:
        if m[0] >= anchor_end and m[2] not in same:
            end = m[0]
            break
    return sentence[window_start:end]


def extract_events(section):
    """Return a list of event dicts (event_type, person_name, title, effective_date)."""
    sentences = split_sentences(resolve_defined_dates(section))
    surname_map = build_surname_map(sentences)
    successor_of = {}       # [Iteration 1] predecessor name -> successor name

    events = {}             # (person_name, event_type) -> event dict, in discovery order
    related = {}            # person_name -> [(sentence, mention)] for fallback look-ups
    unattributed = []       # events with no identifiable person
    last_person = None

    for sentence in sentences:
        mentions = find_people(sentence, surname_map)
        all_names = [m[2] for m in mentions]
        skip = skip_sentence(sentence)

        if not skip:
            for m in mentions:
                related.setdefault(m[2], []).append((sentence, m))
            if not mentions and last_person and PRONOUN_RE.search(sentence):
                related.setdefault(last_person, []).append((sentence, None))

        if not skip:
            # Group this sentence's event verbs by the person they are about.
            per_person = {}          # name -> {"types": set, "start": pos, "mention": m}
            for verb in find_event_verbs(sentence):
                targets = assign_people(sentence, verb, mentions)
                group = [m[2] for m in targets]
                if not targets:
                    if last_person and PRONOUN_RE.search(sentence):
                        targets = [None]         # "She will retire ..." -> previous person
                    else:
                        unattributed.append((sentence, verb))
                        continue
                for mention in targets:
                    name = mention[2] if mention else last_person
                    entry = per_person.setdefault(name, {"types": set(), "start": verb[0],
                                                         "mention": mention, "group": group})
                    entry["types"].add(verb[2])
                # [Iteration 1] "Mr. Borders succeeds Chris Kondo": the person being
                # succeeded is departing that role - record a departure for them too.
                if re.match(r"succeed", verb[3], re.IGNORECASE):
                    after = [m for m in mentions
                             if m[0] >= verb[1] and sentence[verb[1]:m[0]].strip() == ""]
                    if after and targets and targets[0] is not None:
                        pred = after[0]
                        successor_of[pred[2]] = targets[0][2]
                        entry = per_person.setdefault(pred[2], {"types": set(), "start": pred[0],
                                                                "mention": pred, "group": [pred[2]]})
                        entry["types"].add("departure")

            for name, entry in per_person.items():
                # Same person leaving one role and taking another in one sentence -> "both".
                event_type = "both" if len(entry["types"]) == 2 else next(iter(entry["types"]))
                window = event_window(sentence, entry["start"], entry["mention"], mentions,
                                      entry["group"])
                title = find_title(window, entry["mention"], sentence, all_names)
                eff = find_effective_date(window)
                if not eff and len(set(all_names)) <= 1:
                    # Only one person in the sentence, so any effective date is theirs.
                    eff = find_effective_date(sentence)
                key = (name, event_type)
                if key not in events:
                    events[key] = {"event_type": event_type, "person_name": name,
                                   "title": title, "effective_date": eff}
                else:                            # same person/event again: fill gaps only
                    events[key]["title"] = events[key]["title"] or title
                    events[key]["effective_date"] = events[key]["effective_date"] or eff

        if mentions:
            last_person = mentions[0][2]         # sentence subject, for pronoun look-ups

    # Fill missing title/date from other sentences about the same person.
    for event in events.values():
        for sentence, mention in related.get(event["person_name"], []):
            mentions = find_people(sentence, surname_map)
            names = [m[2] for m in mentions]
            start = mention[0] if mention else 0
            window = event_window(sentence, start, mention, mentions)
            if not event["title"]:
                event["title"] = find_title(window, mention, sentence, names)
            if not event["effective_date"]:
                event["effective_date"] = find_effective_date(window)

    # [Iteration 1] A predecessor with no title/date of their own takes the
    # successor's (the successor steps into the same role on the same day).
    for (name, kind), event in events.items():
        successor = successor_of.get(name)
        if successor:
            succ = events.get((successor, "appointment")) or events.get((successor, "both"))
            if succ:
                event["title"] = event["title"] or succ["title"]
                event["effective_date"] = event["effective_date"] or succ["effective_date"]

    # A person reported as "both" should not also get separate departure/appointment rows.
    both_people = {name for name, kind in events if kind == "both"}
    rows = [e for (name, kind), e in events.items() if kind == "both" or name not in both_people]

    # Fallback: event verbs with no identifiable person -> one NOT_FOUND-name row per type.
    if not rows and unattributed:
        seen = set()
        for sentence, verb in unattributed:
            if verb[2] in seen:
                continue
            seen.add(verb[2])
            window = sentence[verb[0]:]
            rows.append({"event_type": verb[2], "person_name": None,
                         "title": find_title(window, None, sentence, []),
                         "effective_date": find_effective_date(window)})

    # Any field not found is stored as the literal string NOT_FOUND.
    for row in rows:
        for field in ("event_type", "person_name", "title", "effective_date"):
            if not row.get(field):
                row[field] = NOT_FOUND
    return rows


# ---------------------------------------------------------------------------
# Per-filing / per-company processing
# ---------------------------------------------------------------------------

def process_filing(company, filing):
    """Download one filing, extract its events, print them, and return CSV rows."""
    ticker, filing_date = company["ticker"], filing["filing_date"]
    url = filing_document_url(company["cik"], filing["accession"], filing["document"])
    try:
        text = html_to_text(sec_get(url).content)
        section = extract_item_502(text)
        if not section:
            print(f"WARNING: {ticker} | {filing_date} | Item 5.02 section not found in {url}")
            return []
        events = extract_events(section)
    except Exception as exc:    # one bad filing must not stop the run
        print(f"WARNING: {ticker} | {filing_date} | could not download/parse {url}: {exc}")
        return []

    if not events:
        if COMPENSATION_RE.search(section):
            print(f"{ticker} | {filing_date} | no departure/appointment found "
                  f"(compensation-only 5.02) — no event row")
        else:
            print(f"{ticker} | {filing_date} | no departure/appointment found — no event row")
        return []

    rows = []
    for event in events:
        print(f"{ticker} | {filing_date} | {event['event_type']} | "
              f"{event['person_name']} | {event['title']}")
        rows.append({
            "company": company["company"],
            "ticker": ticker,
            "cik": company["cik"],
            "filing_date": filing_date,
            "event_type": event["event_type"],
            "person_name": event["person_name"],
            "title": event["title"],
            "effective_date": event["effective_date"],
        })
    return rows


def process_company(company, cutoff):
    """Find and process every Item 5.02 8-K for one company; return its CSV rows."""
    ticker = company["ticker"]
    try:
        filings = find_502_filings(company["cik"], cutoff)
    except Exception as exc:
        print(f"WARNING: {ticker}: could not load SEC submissions: {exc}")
        return []

    if not filings:
        # Zero events is a legitimate finding, not an error.
        print(f"{ticker}: No executive events in past 12 months")
        return []

    rows = []
    for filing in filings:
        rows.extend(process_filing(company, filing))
    return rows


def save_csv(rows, path):
    """Write rows to CSV (overwriting); writes just the header if there are no rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    """Build the executive events table for all five companies."""
    # Avoid crashes on consoles that cannot print some characters (e.g. accented names).
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

    cutoff = twelve_months_ago(date.today())
    print(f"Looking for Item 5.02 8-K filings filed on or after {cutoff.isoformat()}\n")

    all_rows = []
    for company in COMPANIES:
        all_rows.extend(process_company(company, cutoff))

    save_csv(all_rows, OUTPUT_FILE)
    print(f"\nSaved {len(all_rows)} events to {OUTPUT_FILE.as_posix()}")


if __name__ == "__main__":
    main()
