-- Fails if review_priority is ever outside the expected 1-5 range
select *
from {{ ref('mart_review_queue') }}
where review_priority not in (1, 2, 3, 4, 5)
