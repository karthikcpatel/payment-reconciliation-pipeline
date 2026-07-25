import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

KEY_PATH = "/Users/sudheeshgangishetty/Downloads/fintech-reconciliation-85f213388bda.json"
PROJECT_ID = "fintech-reconciliation"

credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)

query = """
SELECT txn_id, merchant, gateway_amount, txn_timestamp, settlement_id,
       settled_amount, settlement_date, amount_diff, num_candidates, discrepancy_type
FROM `fintech-reconciliation.reconciliation.mart_reconciliation`
WHERE discrepancy_type = 'amount_mismatch'
"""
mismatch = client.query(query).to_dataframe()
for col in ["gateway_amount", "settled_amount", "amount_diff"]:
    mismatch[col] = mismatch[col].astype(float)

truth_map = pd.read_csv("data/_private_settlement_truth.csv")
settlements_raw = pd.read_csv("data/bank_settlements.csv")
true_settlement = truth_map.merge(settlements_raw, on="settlement_id")[["true_txn_id", "settlement_id", "settled_amount"]]
true_settlement = true_settlement.rename(columns={
    "true_txn_id": "txn_id", "settlement_id": "true_settlement_id", "settled_amount": "true_settled_amount"
})
true_settlement = true_settlement.groupby("txn_id").first().reset_index()

full = mismatch.merge(true_settlement, on="txn_id", how="left")
full["pick_is_correct"] = full["settlement_id"] == full["true_settlement_id"]
full["error_type"] = full.apply(
    lambda r: "correct_pick" if r["pick_is_correct"]
    else ("truly_never_settled" if pd.isna(r["true_settlement_id"]) else "wrong_settlement_picked"),
    axis=1
)
full["true_dollar_error"] = (full["gateway_amount"] - full["true_settled_amount"].fillna(0)).abs()

full.to_csv("data/_private_excel_analysis_ready.csv", index=False)
print(f"Exported {len(full)} rows, ready for Excel pivot analysis")
print(full["error_type"].value_counts())
