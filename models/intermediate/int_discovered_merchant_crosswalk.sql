{{ config(materialized='table') }}

with distinct_descriptors as (
    select distinct bank_descriptor from {{ ref('stg_bank_settlements') }}
),

distinct_merchants as (
    select distinct merchant from {{ ref('stg_gateway_transactions') }}
),

scored as (
    select
        d.bank_descriptor,
        m.merchant as candidate_merchant,
        edit_distance(
            upper(regexp_replace(m.merchant, r'[^a-zA-Z0-9]', '')),
            upper(regexp_replace(d.bank_descriptor, r'[^a-zA-Z0-9]', ''))
        ) / greatest(
            length(regexp_replace(m.merchant, r'[^a-zA-Z0-9]', '')),
            length(regexp_replace(d.bank_descriptor, r'[^a-zA-Z0-9]', '')),
            1
        ) as normalized_distance
    from distinct_descriptors d
    cross join distinct_merchants m
),

ranked as (
    select
        *,
        row_number() over (partition by bank_descriptor order by normalized_distance asc) as rank
    from scored
),

best_two as (
    select
        bank_descriptor,
        max(case when rank = 1 then candidate_merchant end) as discovered_merchant,
        max(case when rank = 1 then normalized_distance end) as best_score,
        max(case when rank = 2 then normalized_distance end) as second_score
    from ranked
    where rank <= 2
    group by bank_descriptor
)

select
    bank_descriptor,
    discovered_merchant,
    best_score,
    second_score,
    round(second_score - best_score, 4) as confidence_gap,
    (second_score - best_score) < 0.05 as needs_human_review
from best_two
