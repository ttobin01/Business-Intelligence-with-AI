# Prompt B: Count total rows, then subtract rows where txn_type is Sell,
# Deposit, Withdrawal, Dividend, or Advisory Fee.
import pandas as pd
df = pd.read_csv("data/raw/fact_transactions.csv")
total_rows = len(df)
non_buy_types = ["Sell", "Deposit", "Withdrawal", "Dividend", "Advisory Fee"]
non_buy_count = df["txn_type"].isin(non_buy_types).sum()
buy_count = total_rows - non_buy_count
print(f"Total rows: {total_rows}")
print(f"Rows in {non_buy_types}: {non_buy_count}")
print(f"Prompt B result -- Buy count by subtraction: {buy_count}")
