import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

KEY_PATH = "/Users/sudheeshgangishetty/Downloads/fintech-reconciliation-85f213388bda.json"
PROJECT_ID = "fintech-reconciliation"

credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)

query = """
SELECT txn_id, merchant, gateway_amount, settlement_id, settled_amount, num_candidates
FROM `fintech-reconciliation.reconciliation.mart_reconciliation`
WHERE discrepancy_type = 'matched' AND num_candidates >= 5
"""
matched = client.query(query).to_dataframe()

# Ground truth: which settlement actually belongs to each transaction
truth_map = pd.read_csv("data/_private_settlement_truth.csv")  # settlement_id, true_txn_id
truth_lookup = truth_map.set_index("settlement_id")["true_txn_id"]

matched["true_txn_for_this_settlement"] = matched["settlement_id"].map(truth_lookup)
matched["pick_is_correct"] = matched["txn_id"] == matched["true_txn_for_this_settlement"]

print(f"Total high-candidate matched transactions: {len(matched)}")
print(f"Correct picks: {matched['pick_is_correct'].sum()} ({matched['pick_is_correct'].mean():.1%})")
print(f"Wrong picks: {(~matched['pick_is_correct']).sum()} ({(~matched['pick_is_correct']).mean():.1%})")

# Does accuracy degrade further as candidate count grows?
print("\nAccuracy by candidate count:")
print(matched.groupby("num_candidates")["pick_is_correct"].agg(["mean", "count"]))

# Sample of actual wrong picks for eyeballing
print("\nSample of WRONG picks (for manual review):")
wrong = matched[~matched["pick_is_correct"]].sample(min(10, (~matched["pick_is_correct"]).sum()), random_state=1)
print(wrong[["txn_id", "merchant", "gateway_amount", "settlement_id", "settled_amount", "num_candidates"]].to_string())

print("\n--- Same check, extended to delayed and duplicate ---")
query2 = """
SELECT txn_id, discrepancy_type, settlement_id, num_candidates
FROM `fintech-reconciliation.reconciliation.mart_reconciliation`
WHERE discrepancy_type IN ('delayed', 'duplicate') AND num_candidates >= 5
"""
other = client.query(query2).to_dataframe()
other["true_txn_for_this_settlement"] = other["settlement_id"].map(truth_lookup)
other["pick_is_correct"] = other["txn_id"] == other["true_txn_for_this_settlement"]

print(other.groupby("discrepancy_type")["pick_is_correct"].agg(["mean", "count"]))

print("\n--- Same check, extended to amount_mismatch ---")
query3 = """
SELECT txn_id, discrepancy_type, settlement_id, num_candidates
FROM `fintech-reconciliation.reconciliation.mart_reconciliation`
WHERE discrepancy_type = 'amount_mismatch' AND num_candidates >= 5
"""
mismatch = client.query(query3).to_dataframe()
mismatch["true_txn_for_this_settlement"] = mismatch["settlement_id"].map(truth_lookup)
mismatch["pick_is_correct"] = mismatch["txn_id"] == mismatch["true_txn_for_this_settlement"]

print(mismatch.groupby("discrepancy_type")["pick_is_correct"].agg(["mean", "count"]))
