import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

KEY_PATH = "/Users/sudheeshgangishetty/Downloads/fintech-reconciliation-85f213388bda.json"
PROJECT_ID = "fintech-reconciliation"

credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)

query = """
SELECT txn_id, gateway_amount, settled_amount, discrepancy_type
FROM `fintech-reconciliation.reconciliation.mart_reconciliation`
"""
mart = client.query(query).to_dataframe()
for col in ["gateway_amount", "settled_amount"]:
    mart[col] = mart[col].astype(float)

truth_map = pd.read_csv("data/_private_settlement_truth.csv")
gateway = pd.read_csv("data/gateway_transactions.csv")
settlements = pd.read_csv("data/bank_settlements.csv")

# true settlement (if any) per transaction
true_settlement = truth_map.merge(settlements, on="settlement_id")[["true_txn_id", "settled_amount"]]
true_settlement = true_settlement.rename(columns={"true_txn_id": "txn_id", "settled_amount": "true_settled_amount"})
true_settlement = true_settlement.groupby("txn_id").first().reset_index()  # dedupe true duplicates

full = mart.merge(true_settlement, on="txn_id", how="left")
full["true_settled_amount"] = full["true_settled_amount"].fillna(0)  # truly never settled

observed_gap = (full["gateway_amount"] - full["settled_amount"].fillna(0)).sum()
true_gap = (full["gateway_amount"] - full["true_settled_amount"]).sum()

print(f"Pipeline-reported dollar gap: ${observed_gap:,.2f}")
print(f"Actual true dollar gap:       ${true_gap:,.2f}")
print(f"Understatement:               ${true_gap - observed_gap:,.2f} ({(true_gap - observed_gap)/true_gap:.1%} of true gap is hidden)")
