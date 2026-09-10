-- Question metier : une reponse plus longue est-elle associee a une erreur (hesitation,
-- justification, hors-format) ?
select
    run_id,
    model_short,
    prompt_variant,
    variant_label,
    reasoning_mode,
    ai_correct,
    grade,
    count(*)                        as n,
    median(completion_tokens)       as median_completion_tokens,
    avg(completion_tokens)          as mean_completion_tokens,
    median(answer_chars)            as median_answer_chars,
    avg(answer_chars)               as mean_answer_chars,
    median(response_time)           as median_response_time
from {{ ref('fct_answer') }}
group by all
