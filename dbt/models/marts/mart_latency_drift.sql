-- Question metier : le debit se degrade-t-il au fil d'un run long (throttling thermique) ?
-- Les appels sont regroupes par tranches de cent dans leur ordre d'execution.
select
    run_id,
    model_short,
    prompt_variant,
    variant_label,
    reasoning_mode,
    (run_order / 100)::integer * 100    as run_order_bucket,
    count(*)                            as n,
    median(response_time)               as median_response_time,
    median(tokens_per_second)           as median_tokens_per_second,
    median(ttft_s)                      as median_ttft_s,
    avg(ai_correct::int)                as accuracy
from {{ ref('fct_answer') }}
group by all
order by run_id, run_order_bucket
