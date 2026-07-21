import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

KEY_PATH = "/Users/sudheeshgangishetty/Downloads/fintech-reconciliation-85f213388bda.json"
PROJECT_ID = "fintech-reconciliation"

credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)

query = """
SELECT txn_id, num_candidates
FROM `fintech-reconciliation.reconciliation.int_match_selection`
"""
match_detail = client.query(query).to_dataframe()

truth_df = pd.read_csv("data/anomaly_log.csv")
full = truth_df.merge(match_detail, on="txn_id", how="left")

print("num_candidates stats by TRUE anomaly type:")
print(full.groupby("anomaly_type")["num_candidates"].describe())
