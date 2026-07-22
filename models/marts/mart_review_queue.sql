with reconciliation as (
    select * from {{ ref('mart_reconciliation') }}
),

prioritized as (
    select
        txn_id,
        merchant,
        gateway_amount,
        txn_timestamp,
        settlement_id,
        settled_amount,
        discrepancy_type,
        match_confidence,
        num_candidates,
        amount_diff,
        days_to_settle,

        case
            when discrepancy_type = 'missing_settlement' then 1
            when discrepancy_type = 'duplicate' then 2
            when discrepancy_type = 'needs_manual_review' then 3
            when discrepancy_type = 'matched' and num_candidates >= 5 then 4
            when discrepancy_type = 'amount_mismatch' and amount_diff >= 5 then 5
            else null
        end as review_priority,

        case
            when discrepancy_type = 'missing_settlement' then 'No settlement found — full amount unaccounted for'
            when discrepancy_type = 'duplicate' then 'Possible duplicate payout — verify only one settlement is legitimate'
            when discrepancy_type = 'needs_manual_review' then 'Ambiguous tie — two equally plausible settlements, no confident pick'
            when discrepancy_type = 'matched' and num_candidates >= 5 then 'Matched from 5+ candidates — spot-check the pick is correct'
            when discrepancy_type = 'amount_mismatch' and amount_diff >= 5 then 'Settled amount differs from gateway amount by $5 or more'
            else null
        end as review_reason,

        case
            when discrepancy_type in ('missing_settlement', 'needs_manual_review') then gateway_amount
            when discrepancy_type = 'duplicate' then coalesce(settled_amount, 0)
            when discrepancy_type = 'amount_mismatch' then amount_diff
            else 0
        end as estimated_exposure

    from reconciliation
    where discrepancy_type in ('missing_settlement', 'duplicate', 'needs_manual_review')
       or (discrepancy_type = 'matched' and num_candidates >= 5)
       or (discrepancy_type = 'amount_mismatch' and amount_diff >= 5)
),

filtered as (
    select *
    from prioritized
    where review_priority is not null
)

select *
from filtered
qualify row_number() over (partition by review_priority order by gateway_amount desc) <= 30
order by review_priority asc, gateway_amount desc
