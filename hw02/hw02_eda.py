"""
Script: hw02_eda.py
Dataset: data/raw/fact_transactions.csv (Wildcat Capital client transactions, 2020-2024)
Author: Tyler Tobin
Date generated: 2026-09-21
Purpose: Exploratory data analysis on the Wildcat Capital transaction fact table --
         inspect structure, assess missing values, compute summary statistics,
         examine distribution shape, group and aggregate by transaction type,
         and look for relationships between variables (MIS3060 HW2).
Generated with Claude Cowork, 2026-09-21, from hw02/specification.md (17-item EDA spec).
"""

import sys
from io import StringIO

import matplotlib
matplotlib.use("Agg")  # no display needed; we only save charts to disk
import matplotlib.pyplot as plt
import pandas as pd

DATA_PATH = "data/raw/fact_transactions.csv"
CHARTS_DIR = "hw02/charts"
PROFILE_PATH = "hw02/hw02_profile.txt"
EXPECTED_SHAPE = (298772, 9)

# Capture everything printed to the terminal so the same content can also be
# written to hw02/hw02_profile.txt (item 16), without printing things twice.
class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)

    def flush(self):
        for s in self.streams:
            s.flush()


def main():
    profile_buffer = StringIO()
    real_stdout = sys.stdout
    sys.stdout = Tee(real_stdout, profile_buffer)

    # ------------------------------------------------------------------
    # Step 1: Load the data (item 1)
    # ------------------------------------------------------------------
    df = pd.read_csv(DATA_PATH)

    # ------------------------------------------------------------------
    # Step 2: Shape (item 2)
    # ------------------------------------------------------------------
    print("=" * 70)
    print("1. DATASET SHAPE")
    print("=" * 70)
    print(f"Shape: {df.shape[0]:,} rows x {df.shape[1]} columns")

    # ------------------------------------------------------------------
    # Step 3: Column names and data types (item 3)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("2. COLUMN NAMES AND DATA TYPES")
    print("=" * 70)
    print(df.dtypes.to_string())

    # ------------------------------------------------------------------
    # Step 4: Missing values per column (item 4)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("3. MISSING VALUES PER COLUMN")
    print("=" * 70)
    print(df.isnull().sum().to_string())

    # ------------------------------------------------------------------
    # Step 5: Descriptive statistics for numeric columns (item 5)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("4. DESCRIPTIVE STATISTICS (NUMERIC COLUMNS)")
    print("=" * 70)
    print(df.describe().to_string())

    # ------------------------------------------------------------------
    # Step 6: txn_type value counts and percentages (item 6)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("5. TXN_TYPE VALUE COUNTS AND PERCENTAGES")
    print("=" * 70)
    counts = df["txn_type"].value_counts()
    pcts = df["txn_type"].value_counts(normalize=True) * 100
    txn_type_summary = pd.DataFrame({"count": counts, "pct": pcts.round(2)})
    print(txn_type_summary.to_string())

    # ------------------------------------------------------------------
    # Step 7: Unique clients, advisors, securities (item 7)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("6. UNIQUE ENTITY COUNTS")
    print("=" * 70)
    print(f"Unique clients:    {df['client_id'].nunique():,}")
    print(f"Unique advisors:   {df['advisor_id'].nunique():,}")
    print(f"Unique securities: {df['security_id'].nunique():,}")

    # ------------------------------------------------------------------
    # Step 8: Earliest / latest txn_date (item 8)
    # txn_date is left as-is (object/string) per the assignment; a temporary
    # parsed copy is used only to compute min/max, it does not change df.
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("7. DATE RANGE (txn_date)")
    print("=" * 70)
    parsed_dates = pd.to_datetime(df["txn_date"])
    print(f"Earliest txn_date: {parsed_dates.min().date()}")
    print(f"Latest txn_date:   {parsed_dates.max().date()}")

    # ------------------------------------------------------------------
    # Step 9: Duplicate txn_id check (item 9)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("8. DUPLICATE txn_id CHECK")
    print("=" * 70)
    dup_count = df["txn_id"].duplicated().sum()
    print(f"Duplicate txn_id values: {dup_count:,}")

    # ------------------------------------------------------------------
    # Step 10: Mean, median, skewness of amount (item 10)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("9. AMOUNT: MEAN, MEDIAN, SKEWNESS")
    print("=" * 70)
    amount_mean = df["amount"].mean()
    amount_median = df["amount"].median()
    amount_skew = df["amount"].skew()
    print(f"Mean amount:     ${amount_mean:,.2f}")
    print(f"Median amount:   ${amount_median:,.2f}")
    print(f"Skewness:        {amount_skew:.2f}")

    # ------------------------------------------------------------------
    # Step 11: Group by txn_type -> count, mean, median amount (item 11)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("10. AMOUNT BY TXN_TYPE (count, mean, median)")
    print("=" * 70)
    grouped = (
        df.groupby("txn_type")["amount"]
        .agg(count="count", mean_amount="mean", median_amount="median")
        .round(2)
        .sort_values("mean_amount", ascending=False)
    )
    print(grouped.to_string())

    # ------------------------------------------------------------------
    # Step 12: Correlation matrix + top 3 correlations (item 12)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("11. CORRELATION MATRIX (shares, price, amount)")
    print("=" * 70)
    corr = df[["shares", "price", "amount"]].corr().round(2)
    print(corr.to_string())

    # Unstack the matrix into unique pairs, drop self-correlations, rank by |r|
    corr_pairs = (
        corr.where(~corr.isna())
        .stack()
        .reset_index()
    )
    corr_pairs.columns = ["var1", "var2", "correlation"]
    corr_pairs = corr_pairs[corr_pairs["var1"] != corr_pairs["var2"]]
    corr_pairs["pair"] = corr_pairs.apply(lambda r: tuple(sorted([r["var1"], r["var2"]])), axis=1)
    corr_pairs = corr_pairs.drop_duplicates(subset="pair")
    corr_pairs["abs_corr"] = corr_pairs["correlation"].abs()
    top3 = corr_pairs.sort_values("abs_corr", ascending=False).head(3)

    print("\nThree strongest correlations (excluding self-correlations):")
    for _, row in top3.iterrows():
        print(f"  {row['var1']} - {row['var2']}: {row['correlation']:.2f}")

    # ------------------------------------------------------------------
    # Step 13: Negative shares by txn_type (item 13)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("12. SHARES COLUMN: MIN / MAX / NEGATIVE COUNT BY TXN_TYPE")
    print("=" * 70)
    shares_by_type = df.groupby("txn_type")["shares"].agg(
        min_shares="min",
        max_shares="max",
        negative_count=lambda s: (s < 0).sum(),
    )
    print(shares_by_type.to_string())

    # ------------------------------------------------------------------
    # Step 14: Shape warning (item 14)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("13. SHAPE VALIDATION")
    print("=" * 70)
    if df.shape != EXPECTED_SHAPE:
        print(
            f"WARNING: expected shape {EXPECTED_SHAPE}, "
            f"but got {df.shape}. Investigate before proceeding."
        )
    else:
        print(f"Shape confirmed: {df.shape} matches expected {EXPECTED_SHAPE}.")

    # ------------------------------------------------------------------
    # Step 15: Charts (item 15)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("14. CHARTS")
    print("=" * 70)

    import os
    os.makedirs(CHARTS_DIR, exist_ok=True)

    # 15a: Histogram of amount with mean/median lines
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.hist(df["amount"], bins=60, color="#4C72B0", edgecolor="white")
    ax.axvline(amount_mean, color="crimson", linestyle="--", linewidth=2,
               label=f"Mean: ${amount_mean:,.2f}")
    ax.axvline(amount_median, color="darkorange", linestyle="--", linewidth=2,
               label=f"Median: ${amount_median:,.2f}")
    ax.set_title("Distribution of Transaction Amount — Wildcat Capital")
    ax.set_xlabel("Amount ($)")
    ax.set_ylabel("Frequency")
    ax.legend()
    fig.tight_layout()
    hist_path = f"{CHARTS_DIR}/hist_amount.png"
    fig.savefig(hist_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {hist_path}")

    # 15b: Horizontal box plot of amount by txn_type
    fig, ax = plt.subplots(figsize=(9, 6))
    order = grouped.index.tolist()
    data_by_type = [df.loc[df["txn_type"] == t, "amount"] for t in order]
    ax.boxplot(data_by_type, vert=False, labels=order)
    ax.set_title("Transaction Amount by Type — Wildcat Capital")
    ax.set_xlabel("Amount ($)")
    fig.tight_layout()
    box_path = f"{CHARTS_DIR}/box_amount_by_type.png"
    fig.savefig(box_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {box_path}")

    # 15c: Scatter of shares vs amount, colored by txn_type
    fig, ax = plt.subplots(figsize=(9, 6))
    txn_types = df["txn_type"].dropna().unique()
    cmap = plt.get_cmap("tab10")
    for i, t in enumerate(sorted(txn_types)):
        subset = df[df["txn_type"] == t]
        ax.scatter(subset["shares"], subset["amount"], s=8, alpha=0.4,
                   color=cmap(i % 10), label=t)
    ax.set_title("Shares vs. Amount by Transaction Type — Wildcat Capital")
    ax.set_xlabel("Shares")
    ax.set_ylabel("Amount ($)")
    ax.legend(markerscale=2, fontsize=8)
    fig.tight_layout()
    scatter_path = f"{CHARTS_DIR}/scatter_shares_amount.png"
    fig.savefig(scatter_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {scatter_path}")

    # ------------------------------------------------------------------
    # Step 16: Save plain-text summary (items 2-13) to hw02_profile.txt
    # ------------------------------------------------------------------
    with open(PROFILE_PATH, "w") as f:
        f.write(profile_buffer.getvalue())

    sys.stdout = real_stdout
    print("\n" + "=" * 70)
    print(f"Profile summary written to: {PROFILE_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    main()
