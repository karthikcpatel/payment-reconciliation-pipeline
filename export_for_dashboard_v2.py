import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

KEY_PATH = "/Users/sudheeshgangishetty/Downloads/fintech-reconciliation-85f213388bda.json"
PROJECT_ID = "fintech-reconciliation"

credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)

mart = client.query("SELECT * FROM `fintech-reconciliation.reconciliation.mart_reconciliation`").to_dataframe()
mart.to_csv("data/mart_reconciliation_export.csv", index=False)
print(f"mart_reconciliation: {len(mart)} rows")

queue = client.query("SELECT * FROM `fintech-reconciliation.reconciliation.mart_review_queue`").to_dataframe()
queue.to_csv("data/mart_review_queue_export.csv", index=False)
print(f"mart_review_queue: {len(queue)} rows")
