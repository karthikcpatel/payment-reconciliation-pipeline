from google.cloud import bigquery
from google.oauth2 import service_account

KEY_PATH = "/Users/sudheeshgangishetty/Downloads/fintech-reconciliation-85f213388bda.json"
PROJECT_ID = "fintech-reconciliation"
DATASET_ID = "reconciliation"

credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)

# Create dataset if it doesn't exist
dataset_ref = bigquery.Dataset(f"{PROJECT_ID}.{DATASET_ID}")
dataset_ref.location = "US"
client.create_dataset(dataset_ref, exists_ok=True)
print(f"Dataset {DATASET_ID} ready.")

def load_csv(file_path, table_name):
    table_id = f"{PROJECT_ID}.{DATASET_ID}.{table_name}"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        autodetect=True,
        write_disposition="WRITE_TRUNCATE",  # overwrite if rerun
    )
    with open(file_path, "rb") as f:
        job = client.load_table_from_file(f, table_id, job_config=job_config)
    job.result()  # wait for completion
    table = client.get_table(table_id)
    print(f"Loaded {table.num_rows} rows into {table_id}")

load_csv("data/gateway_transactions.csv", "raw_gateway_transactions")
load_csv("data/bank_settlements.csv", "raw_bank_settlements")
