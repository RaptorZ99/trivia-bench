-- Question metier : activer le raisonnement change-t-il la reponse, et a quel prix ?
-- Meme modele, meme variante, memes questions : seul le mode de raisonnement varie.
with runs as (
    select run_id, model_key, model_short, prompt_variant, variant_label, reasoning_mode
    from {{ ref('dim_run') }}
),

pairs as (
    select
        off.run_id                  as run_off,
        on_.run_id                  as run_on,
        r_off.model_short,
        r_off.prompt_variant,
        r_off.variant_label,
        off.ai_correct              as correct_off,
        on_.ai_correct              as correct_on,
        off.response_time           as time_off,
        on_.response_time           as time_on,
        on_.reasoning_tokens        as reasoning_tokens
    from {{ ref('fct_answer') }} as off
    inner join {{ ref('fct_answer') }} as on_ using (question_id)
    inner join runs as r_off on off.run_id = r_off.run_id
    inner join runs as r_on on on_.run_id = r_on.run_id
    where r_off.model_key = r_on.model_key
      and r_off.prompt_variant = r_on.prompt_variant
      and r_off.reasoning_mode = 'off'
      and r_on.reasoning_mode = 'on'
)

select
    model_short,
    prompt_variant,
    variant_label,
    run_off,
    run_on,
    count(*)                                        as n,
    count_if(correct_off and correct_on)            as both_correct,
    count_if(correct_off and not correct_on)        as off_only,
    count_if(not correct_off and correct_on)        as on_only,
    count_if(not correct_off and not correct_on)    as both_wrong,
    avg(correct_off::int)                           as accuracy_off,
    avg(correct_on::int)                            as accuracy_on,
    avg(correct_on::int) - avg(correct_off::int)    as accuracy_gain,
    median(time_off)                                as median_time_off,
    median(time_on)                                 as median_time_on,
    median(time_on) / nullif(median(time_off), 0)   as time_factor,
    median(reasoning_tokens)                        as median_reasoning_tokens
from pairs
group by all
