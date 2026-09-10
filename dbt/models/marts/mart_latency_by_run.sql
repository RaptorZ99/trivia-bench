-- Question metier : combien de temps coute une reponse, selon la variante et le type ?
-- La mediane est privilegiee : quelques reponses longues tirent la moyenne vers le haut.
select
    run_id,
    model_short,
    prompt_variant,
    variant_label,
    reasoning_mode,
    type,
    count(*)                              as n,
    median(response_time)                 as median_response_time,
    quantile_cont(response_time, 0.9)     as p90_response_time,
    quantile_cont(response_time, 0.95)    as p95_response_time,
    avg(response_time)                    as mean_response_time,
    stddev_samp(response_time)            as stddev_response_time,
    min(response_time)                    as min_response_time,
    max(response_time)                    as max_response_time,
    median(ttft_s)                        as median_ttft_s,
    median(tokens_per_second)             as median_tokens_per_second,
    median(time_per_token)                as median_time_per_token,
    median(prompt_tokens)                 as median_prompt_tokens,
    median(completion_tokens)             as median_completion_tokens,
    sum(response_time)                    as total_duration_s
from {{ ref('fct_answer') }}
group by all
