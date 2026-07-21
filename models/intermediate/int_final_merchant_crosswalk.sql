{{ config(materialized='table') }}

with discovered as (
    select * from {{ ref('int_discovered_merchant_crosswalk') }}
),

corrections as (
    select * from {{ ref('manual_merchant_corrections') }}
),

combined as (
    select
        d.bank_descriptor,
        case
            when d.bank_descriptor = 'TST*SMI' then null  -- genuinely ambiguous, left unresolved by design
            else coalesce(c.corrected_merchant, d.discovered_merchant)
        end as final_merchant
    from discovered d
    left join corrections c on d.bank_descriptor = c.bank_descriptor
)

select * from combined
