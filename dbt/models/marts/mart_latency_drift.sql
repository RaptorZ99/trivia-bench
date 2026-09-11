-- Question metier : le debit se degrade-t-il au fil d'un run long (throttling thermique) ?
-- Les appels sont regroupes par tranches de cent dans leur ordre d'execution.
select
    run_id,
    model_short,
    prompt_variant,
    variant_label,
    reasoning_mode,
    -- Division entiere (`//`) et non `/` : en DuckDB `/` est une division flottante, et le
    -- cast en entier arrondit au plus proche au lieu de tronquer. La tranche etiquetee 200
    -- aurait alors contenu les appels 150 a 250, et la premiere tranche n'aurait compte que
    -- cinquante appels au lieu de cent.
    (run_order // 100) * 100            as run_order_bucket,
    count(*)                            as n,
    median(response_time)               as median_response_time,
    median(tokens_per_second)           as median_tokens_per_second,
    median(ttft_s)                      as median_ttft_s,
    avg(ai_correct::int)                as accuracy
from {{ ref('fct_answer') }}
group by all
order by run_id, run_order_bucket
