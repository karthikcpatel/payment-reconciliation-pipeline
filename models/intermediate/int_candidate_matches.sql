{{ config(materialized='table') }}

with gateway as (
    select * from {{ ref('stg_gateway_transactions') }}
),

settlements as (
    select * from {{ ref('stg_bank_settlements') }}
),

crosswalk as (
    select * from {{ ref('int_final_merchant_crosswalk') }}
),

settlements_classified as (
    select
        s.*,
        c.final_merchant as classified_merchant
    from settlements s
    left join crosswalk c
        on s.bank_descriptor = c.bank_descriptor
),

candidates as (
    select
        g.txn_id,
        g.merchant,
        g.gateway_amount,
        g.txn_timestamp,
        s.settlement_id,
        s.settled_amount,
        s.settlement_date,
        date_diff(date(s.settlement_date), date(g.txn_timestamp), day) as days_to_settle,
        abs(g.gateway_amount - s.settled_amount) as amount_diff
    from gateway g
    join settlements_classified s
        on g.merchant = s.classified_merchant
        and abs(g.gateway_amount - s.settled_amount) <= greatest(5.0, g.gateway_amount * 0.05)
        and s.settlement_date between g.txn_timestamp and timestamp_add(g.txn_timestamp, interval 15 day)
),

ranked as (
    select
        *,
        row_number() over (
            partition by txn_id
            order by amount_diff asc, days_to_settle asc
        ) as match_rank
    from candidates
)

select * from ranked
