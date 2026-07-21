with gateway as (
    select * from {{ ref('stg_gateway_transactions') }}
),

match_info as (
    select * from {{ ref('int_match_selection') }}
),

joined as (
    select
        g.txn_id,
        g.merchant,
        g.gateway_amount,
        g.txn_timestamp,
        m.settlement_id,
        m.settled_amount,
        m.settlement_date,
        m.amount_diff,
        m.days_to_settle,
        m.num_candidates,
        m.tie_type
    from gateway g
    left join match_info m on g.txn_id = m.txn_id
),

classified as (
    select
        *,
        case
            when num_candidates is null or num_candidates = 0 then 'missing_settlement'
            when tie_type = 'ambiguous' then 'needs_manual_review'
            when tie_type = 'true_duplicate' then 'duplicate'
            when amount_diff > 0.01 then 'amount_mismatch'
            when days_to_settle > 3 then 'delayed'
            else 'matched'
        end as discrepancy_type,
        round(gateway_amount - coalesce(settled_amount, 0), 2) as amount_diff_signed
    from joined
)

select * from classified
