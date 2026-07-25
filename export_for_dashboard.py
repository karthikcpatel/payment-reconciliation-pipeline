import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

KEY_PATH = "/Users/sudheeshgangishetty/Downloads/fintech-reconciliation-85f213388bda.json"
PROJECT_ID = "fintech-reconciliation"

credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)

query = """
SELECT *
FROM `fintech-reconciliation.reconciliation.mart_reconciliation`
"""
df = client.query(query).to_dataframe()

df.to_csv("data/mart_reconciliation_export.csv", index=False)
print(f"Exported {len(df)} rows to data/mart_reconciliation_export.csv")
print(f"\nColumns: {list(df.columns)}")
print(f"\nDiscrepancy type breakdown:")
print(df["discrepancy_type"].value_counts())
