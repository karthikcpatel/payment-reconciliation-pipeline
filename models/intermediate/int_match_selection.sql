{{ config(materialized='table') }}

with ranked_candidates as (
    select * from {{ ref('int_candidate_matches') }}
),

per_txn_stats as (
    select
        txn_id,
        count(*) as num_candidates,
        min(case when match_rank = 1 then amount_diff end) as best_amount_diff,
        min(case when match_rank = 2 then amount_diff end) as second_amount_diff,
        count(distinct case when match_rank <= 2 then settled_amount end) as distinct_amounts_top2,
        count(distinct case when match_rank <= 2 then settlement_date end) as distinct_dates_top2
    from ranked_candidates
    group by txn_id
),

chosen_match as (
    select * from ranked_candidates where match_rank = 1
),

combined as (
    select
        c.txn_id,
        c.settlement_id,
        c.settled_amount,
        c.settlement_date,
        c.amount_diff,
        c.days_to_settle,
        s.num_candidates,
        case
            when s.num_candidates >= 2 and s.best_amount_diff = s.second_amount_diff then
                case
                    when s.distinct_amounts_top2 = 1 and s.distinct_dates_top2 = 1 then 'true_duplicate'
                    else 'ambiguous'
                end
            else 'unique_or_clear'
        end as tie_type
    from chosen_match c
    join per_txn_stats s on c.txn_id = s.txn_id
)

select * from combined
