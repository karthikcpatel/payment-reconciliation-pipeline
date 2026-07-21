with gateway as (
    select * from {{ ref('stg_gateway_transactions') }}
),

settlements as (
    select * from {{ ref('stg_bank_settlements') }}
),

-- flag duplicates: any txn_id with more than 1 settlement row
settlement_counts as (
    select
        txn_id,
        count(*) as settlement_count
    from settlements
    group by txn_id
),

-- for txns with multiple settlements, just take the first one for comparison purposes
settlements_deduped as (
    select
        s.*,
        row_number() over (partition by s.txn_id order by s.settlement_date asc) as rn
    from settlements s
),

joined as (
    select
        g.txn_id,
        g.merchant,
        g.gateway_amount,
        g.txn_timestamp,
        s.settlement_id,
        s.settled_amount,
        s.settlement_date,
        sc.settlement_count,
        date_diff(date(s.settlement_date), date(g.txn_timestamp), day) as days_to_settle
    from gateway g
    left join settlements_deduped s
        on g.txn_id = s.txn_id and s.rn = 1
    left join settlement_counts sc
        on g.txn_id = sc.txn_id
),

classified as (
    select
        *,
        case
            when settlement_id is null then 'missing_settlement'
            when settlement_count > 1 then 'duplicate'
            when abs(gateway_amount - settled_amount) > 0.01 then 'amount_mismatch'
            when days_to_settle > 3 then 'delayed'
            else 'matched'
        end as discrepancy_type,
        round(gateway_amount - coalesce(settled_amount, 0), 2) as amount_diff
    from joined
)

select * from classified
