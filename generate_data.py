import pandas as pd
import numpy as np
from faker import Faker
from datetime import timedelta
import random

random.seed(42)
np.random.seed(42)
fake = Faker()

N_TRANSACTIONS = 8000
START_DATE = pd.Timestamp("2026-05-01")
END_DATE = pd.Timestamp("2026-06-30")

MERCHANTS = [fake.company() for _ in range(25)]

P_MISSING = 0.04
P_AMOUNT_MISMATCH = 0.04
P_DUPLICATE = 0.03
P_DELAYED = 0.04

PROCESSOR_PREFIXES = ["SQ *", "SP ", "PAYPAL *", "TST*", ""]

def mangle_merchant(merchant):
    """Simulate messy real-world bank statement descriptors."""
    name = merchant.upper().replace(",", "").replace(".", "")
    name_compact = name.replace(" ", "")

    style = random.choice(["truncate", "compact_truncate", "store_code", "prefix_only", "abbrev"])
    prefix = random.choice(PROCESSOR_PREFIXES)

    if style == "truncate":
        base = name[:random.randint(10, 18)]
    elif style == "compact_truncate":
        base = name_compact[:random.randint(8, 14)]
    elif style == "store_code":
        base = name[:random.randint(8, 14)] + f" #{random.randint(1000,9999)}"
    elif style == "abbrev":
        words = name.split()
        base = "".join(w[:3] for w in words)[:14]
    else:
        base = name[:random.randint(10, 20)]

    descriptor = f"{prefix}{base}".strip()
    # occasionally append a city/location code, like real statements do
    if random.random() < 0.4:
        descriptor += " " + random.choice(["SYD", "MEL", "AU", "NSW"])
    return descriptor

def random_timestamp():
    delta_days = (END_DATE - START_DATE).days
    random_days = random.uniform(0, delta_days)
    return START_DATE + timedelta(days=random_days)

# ---- 1. Gateway transactions ----
gateway_rows = []
for i in range(1, N_TRANSACTIONS + 1):
    txn_id = f"TXN{i:06d}"
    amount = round(random.uniform(5, 500), 2)
    timestamp = random_timestamp()
    merchant = random.choice(MERCHANTS)
    gateway_rows.append({
        "txn_id": txn_id,
        "amount": amount,
        "timestamp": timestamp,
        "merchant": merchant,
        "status": "completed"
    })

gateway_df = pd.DataFrame(gateway_rows)

# ---- 2. Assign anomaly types (kept private — answer key only) ----
anomaly_choices = (
    ["missing"] * int(N_TRANSACTIONS * P_MISSING) +
    ["amount_mismatch"] * int(N_TRANSACTIONS * P_AMOUNT_MISMATCH) +
    ["duplicate"] * int(N_TRANSACTIONS * P_DUPLICATE) +
    ["delayed"] * int(N_TRANSACTIONS * P_DELAYED)
)
anomaly_choices += ["clean"] * (N_TRANSACTIONS - len(anomaly_choices))
random.shuffle(anomaly_choices)
gateway_df["anomaly_type"] = anomaly_choices

# ---- 3. Generate settlements — NO txn_id, mangled merchant descriptor ----
settlement_rows = []
settlement_counter = 1

for _, row in gateway_df.iterrows():
    amount = row["amount"]
    txn_timestamp = row["timestamp"]
    merchant = row["merchant"]
    anomaly = row["anomaly_type"]
    descriptor = mangle_merchant(merchant)

    if anomaly == "missing":
        continue

    elif anomaly == "amount_mismatch":
        if random.random() < 0.7:
            diff = round(amount * random.uniform(0.01, 0.03), 2)
        else:
            diff = round(random.uniform(5, 50), 2)
        settled_amount = round(amount - diff, 2)
        settle_date = txn_timestamp + timedelta(days=random.randint(1, 3))
        settlement_rows.append({
            "settlement_id": f"STL{settlement_counter:06d}",
            "settled_amount": settled_amount,
            "settlement_date": settle_date,
            "bank_descriptor": descriptor
        })
        settlement_counter += 1

    elif anomaly == "duplicate":
        settle_date = txn_timestamp + timedelta(days=random.randint(1, 3))
        for _ in range(2):
            settlement_rows.append({
                "settlement_id": f"STL{settlement_counter:06d}",
                "settled_amount": amount,
                "settlement_date": settle_date,
                "bank_descriptor": descriptor
            })
            settlement_counter += 1

    elif anomaly == "delayed":
        settle_date = txn_timestamp + timedelta(days=random.randint(4, 15))
        settlement_rows.append({
            "settlement_id": f"STL{settlement_counter:06d}",
            "settled_amount": amount,
            "settlement_date": settle_date,
            "bank_descriptor": descriptor
        })
        settlement_counter += 1

    else:  # clean
        settle_date = txn_timestamp + timedelta(days=random.randint(1, 3))
        settlement_rows.append({
            "settlement_id": f"STL{settlement_counter:06d}",
            "settled_amount": amount,
            "settlement_date": settle_date,
            "bank_descriptor": descriptor
        })
        settlement_counter += 1

settlement_df = pd.DataFrame(settlement_rows)
# shuffle settlement rows so they're not suspiciously in gateway order
settlement_df = settlement_df.sample(frac=1, random_state=42).reset_index(drop=True)

# ---- 4. Save outputs ----
gateway_output = gateway_df.drop(columns=["anomaly_type"])
gateway_output.to_csv("data/gateway_transactions.csv", index=False)
settlement_df.to_csv("data/bank_settlements.csv", index=False)
gateway_df[["txn_id", "merchant", "anomaly_type"]].to_csv("data/anomaly_log.csv", index=False)

print(f"Generated {len(gateway_output)} gateway transactions")
print(f"Generated {len(settlement_df)} settlement records (no txn_id — matching required)")
print("\nSample bank descriptors vs original merchant names:")
sample = gateway_df.sample(5, random_state=1)[["merchant"]]
print(sample)
