-- Fails if a transaction somehow appears more than once in the review queue
select txn_id, count(*) as occurrences
from {{ ref('mart_review_queue') }}
group by txn_id
having count(*) > 1
