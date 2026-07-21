with source as (
    select * from {{ source('raw', 'raw_bank_settlements') }}
),

cleaned as (
    select
        settlement_id,
        cast(settled_amount as numeric) as settled_amount,
        cast(settlement_date as timestamp) as settlement_date,
        bank_descriptor
    from source
)

select * from cleaned
