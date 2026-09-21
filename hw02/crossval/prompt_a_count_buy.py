# Prompt A: Count rows in fact_transactions.csv where txn_type equals exactly 'Buy'.
import pandas as pd
df = pd.read_csv("data/raw/fact_transactions.csv")
buy_count = (df["txn_type"] == "Buy").sum()
print(f"Prompt A result -- rows where txn_type == 'Buy': {buy_count}")
