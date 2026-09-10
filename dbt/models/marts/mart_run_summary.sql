-- Question metier : quelle est la performance globale de chaque couple (modele, variante) ?
with agg as (
    select
        run_id,
        model_key,
        model_short,
        prompt_variant,
        variant_label,
        reasoning_mode,
        count(*)                                   as n,
        count_if(ai_correct)                       as n_correct,
        count_if(grade = 'unparseable')            as n_unparseable,
        count_if(grade = 'error')                  as n_error,
        count_if(is_parsed)                        as n_parsed,
        count_if(is_expected_format)               as n_expected_format,
        count_if(is_truncated)                     as n_truncated,
        count_if(ai_correct and is_parsed)         as n_correct_parsed,
        {{ chance_baseline() }}                    as chance_baseline,
        median(response_time)                      as median_response_time,
        quantile_cont(response_time, 0.9)          as p90_response_time,
        quantile_cont(response_time, 0.95)         as p95_response_time,
        avg(response_time)                         as mean_response_time,
        median(tokens_per_second)                  as median_tokens_per_second,
        median(ttft_s)                             as median_ttft_s,
        median(time_per_token)                     as median_time_per_token,
        avg(prompt_tokens)                         as mean_prompt_tokens,
        avg(completion_tokens)                     as mean_completion_tokens,
        sum(response_time)                         as total_duration_s
    from {{ ref('fct_answer') }}
    group by all
)

select
    *,
    n_correct::double / nullif(n, 0)                    as accuracy,
    n_correct_parsed::double / nullif(n_parsed, 0)      as accuracy_parsed_only,
    n_unparseable::double / nullif(n, 0)                as unparseable_rate,
    n_expected_format::double / nullif(n, 0)            as format_compliance_rate,
    n_truncated::double / nullif(n, 0)                  as truncation_rate,
    n_correct::double / nullif(n, 0) - chance_baseline  as accuracy_above_chance,
    {{ wilson_lo('n_correct', 'n') }}                   as wilson_lo,
    {{ wilson_hi('n_correct', 'n') }}                   as wilson_hi
from agg
order by accuracy desc
