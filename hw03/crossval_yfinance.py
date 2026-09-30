"""
crossval_yfinance.py - HW3 Part 5C cross-validation.

Prompt used: "Write Python using yfinance to get the most recent quarterly
revenue and net income for AAPL."

Pulls Apple's quarterly income statement from Yahoo Finance (a source that is
independent of our 8-K text extraction) and prints the most recent quarter's
Total Revenue and Net Income, in $ millions so they line up with
hw03/earnings_history.csv.

Run from the repo root:  python hw03/crossval_yfinance.py
(requires: pip install yfinance)
"""

import yfinance as yf

TICKER = "AAPL"


def main():
    stmt = yf.Ticker(TICKER).quarterly_income_stmt   # rows = line items, columns = quarter-end dates
    if stmt is None or stmt.empty:
        print(f"No quarterly income statement returned for {TICKER}")
        return

    latest = max(stmt.columns)                        # most recent quarter-end column
    revenue = stmt.loc["Total Revenue", latest]
    net_income = stmt.loc["Net Income", latest]

    print(f"{TICKER} most recent quarter (Yahoo period end {latest.date()}):")
    print(f"  Total Revenue: ${revenue / 1e6:,.0f}M")
    print(f"  Net Income:    ${net_income / 1e6:,.0f}M")


if __name__ == "__main__":
    main()
