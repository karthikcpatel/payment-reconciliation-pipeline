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

# Confusion matrix: true anomaly type vs what the pipeline actually classified it as
confusion = pd.crosstab(merged["anomaly_type"], merged["discrepancy_type"])
print("Confusion matrix (rows = true label, columns = predicted label):\n")
print(confusion)

# Overall accuracy for reference
match_map = {
    "clean": "matched",
    "missing": "missing_settlement",
    "amount_mismatch": "amount_mismatch",
    "duplicate": "duplicate",
    "delayed": "delayed",
}
merged["expected"] = merged["anomaly_type"].map(match_map)
merged["correct"] = merged["expected"] == merged["discrepancy_type"]
accuracy = merged["correct"].mean()
print(f"\nOverall exact-match accuracy: {accuracy:.2%}")

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)
print("\nFull confusion matrix:\n")
print(confusion)

# Pull merchant_distance from the intermediate model to inspect distribution

full = truth_df.merge(match_detail, on="txn_id", how="left")


# Test: what if we treat any match with merchant_distance above a threshold as low-confidence?
print("\nThreshold sensitivity test:")
for threshold in [6, 7, 8, 9, 10, 11, 12]:
    full["would_flag"] = full["merchant_distance"] > threshold
    flagged_missing = full[(full["anomaly_type"] == "missing") & (full["would_flag"])].shape[0]
    flagged_clean = full[(full["anomaly_type"] == "clean") & (full["would_flag"])].shape[0]
    total_missing = full[full["anomaly_type"] == "missing"].shape[0]
    total_clean = full[full["anomaly_type"] == "clean"].shape[0]
    print(f"threshold={threshold}: catches {flagged_missing}/{total_missing} true 'missing' impostor-matches, "
          f"but also flags {flagged_clean}/{total_clean} genuinely clean transactions ({flagged_clean/total_clean:.1%})")

print("\n--- Threshold optimized for catching MISSING specifically ---")
missing_true = full[full["anomaly_type"] == "missing"]
clean_true = full[full["anomaly_type"] == "clean"]

for threshold in [10, 11, 12, 13, 14, 15, 16]:
    missing_caught = (missing_true["merchant_distance"] > threshold).sum()
    clean_falsely_flagged = (clean_true["merchant_distance"] > threshold).sum()
    print(f"threshold={threshold}: "
          f"missing recall = {missing_caught}/320 ({missing_caught/320:.1%}), "
          f"clean false-flag rate = {clean_falsely_flagged}/6800 ({clean_falsely_flagged/6800:.1%})")
