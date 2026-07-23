-- Fails if any settled_amount is negative (should never happen in real settlement data)
select *
from {{ ref('mart_reconciliation') }}
where settled_amount < 0
