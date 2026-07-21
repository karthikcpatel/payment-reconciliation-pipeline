import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

KEY_PATH = "/Users/sudheeshgangishetty/Downloads/fintech-reconciliation-85f213388bda.json"
PROJECT_ID = "fintech-reconciliation"

credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)

query = """
SELECT txn_id, settlement_id, merchant_distance, amount_diff, gateway_amount
FROM `fintech-reconciliation.reconciliation.int_candidate_matches`
"""
candidates = client.query(query).to_dataframe()
candidates["merchant_distance"] = candidates["merchant_distance"].astype(float)
candidates["amount_diff"] = candidates["amount_diff"].astype(float)
candidates["gateway_amount"] = candidates["gateway_amount"].astype(float)
truth = pd.read_csv("data/_private_settlement_truth.csv")

truth_map = truth.set_index("settlement_id")["true_txn_id"]
candidates["true_txn_for_settlement"] = candidates["settlement_id"].map(truth_map)
candidates["is_true_match"] = candidates["txn_id"] == candidates["true_txn_for_settlement"]

candidates["pct_amount_diff"] = (candidates["amount_diff"] / candidates["gateway_amount"]) * 100

grp = candidates.groupby("txn_id")
for col in ["merchant_distance", "pct_amount_diff"]:
    cmin = grp[col].transform("min")
    cmax = grp[col].transform("max")
    candidates[f"{col}_norm"] = (candidates[col] - cmin) / (cmax - cmin + 1e-9)

results = []
for w_merchant in [1.0, 0.7, 0.5, 0.3, 0.0]:
    w_amount = 1 - w_merchant
    candidates["composite"] = (
        w_merchant * candidates["merchant_distance_norm"] +
        w_amount * candidates["pct_amount_diff_norm"]
    )
    picks = candidates.loc[candidates.groupby("txn_id")["composite"].idxmin()]
    hit_rate = picks["is_true_match"].mean()
    results.append({"w_merchant": w_merchant, "w_amount": w_amount, "top1_hit_rate": hit_rate})

print(pd.DataFrame(results))

# Finer sweep near the amount-heavy end
print("\nFiner sweep:")
results2 = []
for w_merchant in [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3]:
    w_amount = 1 - w_merchant
    candidates["composite"] = (
        w_merchant * candidates["merchant_distance_norm"] +
        w_amount * candidates["pct_amount_diff_norm"]
    )
    picks = candidates.loc[candidates.groupby("txn_id")["composite"].idxmin()]
    hit_rate = picks["is_true_match"].mean()
    results2.append({"w_merchant": w_merchant, "w_amount": w_amount, "top1_hit_rate": hit_rate})

print(pd.DataFrame(results2))

# Lexicographic approach: rank by amount_diff first, merchant_distance as tiebreaker only
print("\nLexicographic ranking (amount primary, merchant tiebreaker):")
candidates_sorted = candidates.sort_values(["txn_id", "amount_diff", "merchant_distance"])
picks_lex = candidates_sorted.groupby("txn_id").first().reset_index()
hit_rate_lex = picks_lex["is_true_match"].mean()
print(f"Lexicographic hit rate: {hit_rate_lex:.4f}")
