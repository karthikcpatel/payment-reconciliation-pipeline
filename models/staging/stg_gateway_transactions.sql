with source as (
    select * from {{ source('raw', 'raw_gateway_transactions') }}
),

cleaned as (
    select
        txn_id,
        cast(amount as numeric) as gateway_amount,
        cast(timestamp as timestamp) as txn_timestamp,
        merchant,
        status
    from source
)

select * from cleaned
