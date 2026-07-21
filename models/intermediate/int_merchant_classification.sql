{{ config(materialized='table') }}

with distinct_merchants as (
    select distinct merchant from {{ ref('stg_gateway_transactions') }}
),

settlements as (
    select settlement_id, bank_descriptor from {{ ref('stg_bank_settlements') }}
),

scored as (
    select
        s.settlement_id,
        s.bank_descriptor,
        m.merchant as candidate_merchant,
        edit_distance(
            upper(regexp_replace(m.merchant, r'[^a-zA-Z0-9]', '')),
            upper(regexp_replace(s.bank_descriptor, r'[^a-zA-Z0-9]', ''))
        ) / greatest(
            length(regexp_replace(m.merchant, r'[^a-zA-Z0-9]', '')),
            length(regexp_replace(s.bank_descriptor, r'[^a-zA-Z0-9]', '')),
            1
        ) as normalized_distance
    from settlements s
    cross join distinct_merchants m
),

ranked as (
    select
        *,
        row_number() over (partition by settlement_id order by normalized_distance asc) as rank
    from scored
),

best_two as (
    select
        settlement_id,
        max(case when rank = 1 then candidate_merchant end) as classified_merchant,
        max(case when rank = 1 then normalized_distance end) as best_score,
        max(case when rank = 2 then normalized_distance end) as second_score
    from ranked
    where rank <= 2
    group by settlement_id
)

select
    settlement_id,
    classified_merchant,
    best_score,
    second_score,
    round(second_score - best_score, 4) as confidence_gap,
    (second_score - best_score) < 0.05 as needs_human_review
from best_two
