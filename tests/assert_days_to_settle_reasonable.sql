-- Fails if any settlement is dated before the transaction, or absurdly far in the future
-- (0 to 20 days covers the generator's max 15-day delay plus a small buffer)
select *
from {{ ref('mart_reconciliation') }}
where days_to_settle is not null
  and (days_to_settle < 0 or days_to_settle > 20)
