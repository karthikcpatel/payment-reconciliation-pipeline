import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

KEY_PATH = "/Users/sudheeshgangishetty/Downloads/fintech-reconciliation-85f213388bda.json"
PROJECT_ID = "fintech-reconciliation"

credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)

query = """
SELECT settlement_id, classified_merchant, best_score, confidence_gap, needs_human_review
FROM `fintech-reconciliation.reconciliation.int_merchant_classification`
"""
classified = client.query(query).to_dataframe()

# Ground truth: what merchant does this settlement TRUELY belong to
truth_map = pd.read_csv("data/_private_settlement_truth.csv")  # settlement_id, true_txn_id
gateway = pd.read_csv("data/gateway_transactions.csv")  # txn_id, merchant

truth = truth_map.merge(gateway, left_on="true_txn_id", right_on="txn_id")[["settlement_id", "merchant"]]
truth = truth.rename(columns={"merchant": "true_merchant"})

merged = classified.merge(truth, on="settlement_id", how="left")
merged["correct"] = merged["classified_merchant"] == merged["true_merchant"]

print(f"Overall merchant classification accuracy: {merged['correct'].mean():.2%}")
print(f"\nAccuracy among 'needs_human_review' flagged rows: {merged[merged['needs_human_review']]['correct'].mean():.2%}")
print(f"Accuracy among confident (not flagged) rows: {merged[~merged['needs_human_review']]['correct'].mean():.2%}")
print(f"\nRow counts:")
print(merged["needs_human_review"].value_counts())
