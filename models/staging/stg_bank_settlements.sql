with source as (
    select * from {{ source('raw', 'raw_bank_settlements') }}
),

cleaned as (
    select
        settlement_id,
        txn_id,
        cast(amount as numeric) as settled_amount,
        cast(settlement_date as timestamp) as settlement_date
    from source
)

select * from cleaned
