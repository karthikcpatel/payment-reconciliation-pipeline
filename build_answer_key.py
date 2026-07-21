import pandas as pd

gateway = pd.read_csv("data/gateway_transactions.csv")
settlements = pd.read_csv("data/bank_settlements.csv")
anomaly_log = pd.read_csv("data/anomaly_log.csv")  # txn_id, merchant, anomaly_type
truth_map = pd.read_csv("data/_private_settlement_truth.csv")  # settlement_id, true_txn_id

# Attach the TRUE txn_id to every real settlement row
settlements_with_truth = settlements.merge(truth_map, on="settlement_id", how="left")

# Start from gateway transactions (every transaction, including ones with no settlement)
# and bring in every settlement that truly belongs to it (duplicates will produce 2 rows)
answer_key = gateway.merge(
    settlements_with_truth,
    left_on="txn_id",
    right_on="true_txn_id",
    how="left"
)

# Bring in the anomaly_type label
answer_key = answer_key.merge(
    anomaly_log[["txn_id", "anomaly_type"]],
    on="txn_id",
    how="left"
)

answer_key["was_settled"] = answer_key["settlement_id"].notna()

# Clean column order and naming for readability
answer_key = answer_key.rename(columns={
    "amount": "gateway_amount",
    "timestamp": "gateway_timestamp",
    "merchant": "true_merchant"
})

answer_key = answer_key[[
    "txn_id", "true_merchant", "gateway_amount", "gateway_timestamp",
    "anomaly_type", "was_settled",
    "settlement_id", "settled_amount", "settlement_date", "bank_descriptor"
]]

answer_key = answer_key.sort_values("txn_id")
answer_key.to_csv("data/_private_full_answer_key.csv", index=False)

print(f"Answer key rows: {len(answer_key)} (includes duplicate settlements as extra rows)")
print(f"\nBreakdown by anomaly_type:")
print(answer_key.drop_duplicates("txn_id")["anomaly_type"].value_counts())
print(f"\nSample rows:")
print(answer_key.head(10).to_string())
