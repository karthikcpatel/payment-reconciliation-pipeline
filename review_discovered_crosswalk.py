import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

KEY_PATH = "/Users/sudheeshgangishetty/Downloads/fintech-reconciliation-85f213388bda.json"
PROJECT_ID = "fintech-reconciliation"

credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)

query = """
SELECT bank_descriptor, discovered_merchant, best_score, confidence_gap, needs_human_review
FROM `fintech-reconciliation.reconciliation.int_discovered_merchant_crosswalk`
"""
discovered = client.query(query).to_dataframe()
discovered = discovered.sort_values(["discovered_merchant", "confidence_gap"])

discovered.to_csv("data/discovered_merchant_crosswalk_for_review.csv", index=False)

print(f"Total distinct descriptors: {len(discovered)}")
print(f"Flagged for human review: {discovered['needs_human_review'].sum()}")
print("\nSaved to data/discovered_merchant_crosswalk_for_review.csv — grouped by discovered merchant, worst-confidence first within each group.")
