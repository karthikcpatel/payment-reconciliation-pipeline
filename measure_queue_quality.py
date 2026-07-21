import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

KEY_PATH = "/Users/sudheeshgangishetty/Downloads/fintech-reconciliation-85f213388bda.json"
PROJECT_ID = "fintech-reconciliation"

credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)

query = """
SELECT txn_id, discrepancy_type
FROM `fintech-reconciliation.reconciliation.mart_reconciliation`
"""
results_df = client.query(query).to_dataframe()
truth_df = pd.read_csv("data/anomaly_log.csv")
merged = results_df.merge(truth_df, on="txn_id", how="left")

queue = merged[merged["discrepancy_type"] == "needs_manual_review"]
print(f"Total transactions sent to manual review: {len(queue)}")
print(f"\nWhat's actually inside the review queue (true label breakdown):")
print(queue["anomaly_type"].value_counts())
print(f"\nAs % of queue:")
print((queue["anomaly_type"].value_counts(normalize=True) * 100).round(1))

# recall check: of all TRUE missing, how many made it to the queue vs elsewhere
missing_true = merged[merged["anomaly_type"] == "missing"]
print(f"\nOf {len(missing_true)} true missing transactions, where did they end up:")
print(missing_true["discrepancy_type"].value_counts())
