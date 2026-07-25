import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

KEY_PATH = "/Users/sudheeshgangishetty/Downloads/fintech-reconciliation-85f213388bda.json"
PROJECT_ID = "fintech-reconciliation"

credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)

query = """
SELECT txn_id, gateway_amount, settled_amount, amount_diff, discrepancy_type
FROM `fintech-reconciliation.reconciliation.mart_reconciliation`
"""
mart = client.query(query).to_dataframe()
for col in ["gateway_amount", "settled_amount", "amount_diff"]:
    mart[col] = mart[col].astype(float)

# Approach A: current net gap (trusts settled_amount even when wrongly matched)
approach_a = (mart["gateway_amount"] - mart["settled_amount"].fillna(0)).sum()

# Approach B: your proposal - full gateway_amount for anything not "matched"
approach_b = mart.loc[mart["discrepancy_type"] != "matched", "gateway_amount"].sum()

# Approach C: category-aware hybrid
def hybrid_exposure(row):
    if row["discrepancy_type"] in ["missing_settlement", "needs_manual_review"]:
        return row["gateway_amount"]
    elif row["discrepancy_type"] == "amount_mismatch":
        return row["amount_diff"]
    else:  # matched, delayed, duplicate
        return 0.0

approach_c = mart.apply(hybrid_exposure, axis=1).sum()

# Ground truth: real dollar gap using TRUE settlement data
truth_map = pd.read_csv("data/_private_settlement_truth.csv")
settlements = pd.read_csv("data/bank_settlements.csv")
gateway = pd.read_csv("data/gateway_transactions.csv")

true_settlement = truth_map.merge(settlements, on="settlement_id")[["true_txn_id", "settled_amount"]]
true_settlement = true_settlement.rename(columns={"true_txn_id": "txn_id", "settled_amount": "true_settled_amount"})
true_settlement = true_settlement.groupby("txn_id").first().reset_index()

full = gateway.merge(true_settlement, on="txn_id", how="left")
full["true_settled_amount"] = full["true_settled_amount"].fillna(0)
true_gap = (full["amount"] - full["true_settled_amount"]).sum()

print(f"Approach A (current net gap):        ${approach_a:>12,.2f}")
print(f"Approach B (your proposal - gross):  ${approach_b:>12,.2f}")
print(f"Approach C (category-aware hybrid):  ${approach_c:>12,.2f}")
print(f"TRUE dollar gap (ground truth):      ${true_gap:>12,.2f}")
