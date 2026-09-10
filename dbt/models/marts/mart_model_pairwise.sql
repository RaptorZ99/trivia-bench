-- Question metier : deux modeles different-ils reellement, a formulation identique ?
-- Les deux modeles n'ont pas forcement ete evalues sur le meme nombre de questions (un modele
-- secondaire peut n'avoir vu qu'un echantillon stratifie) : la jointure sur `question_id`
-- restreint la comparaison a leur intersection, seule base equitable.
with runs as (
    select run_id, model_key, model_short, prompt_variant, variant_label, reasoning_mode
    from {{ ref('dim_run') }}
),

pairs as (
    select
        a.run_id            as run_a,
        b.run_id            as run_b,
        ra.model_short      as model_a,
        rb.model_short      as model_b,
        ra.prompt_variant,
        ra.variant_label,
        ra.reasoning_mode,
        a.ai_correct        as correct_a,
        b.ai_correct        as correct_b,
        a.response_time     as time_a,
        b.response_time     as time_b
    from {{ ref('fct_answer') }} as a
    inner join {{ ref('fct_answer') }} as b using (question_id)
    inner join runs as ra on a.run_id = ra.run_id
    inner join runs as rb on b.run_id = rb.run_id
    where ra.prompt_variant = rb.prompt_variant
      and ra.reasoning_mode = rb.reasoning_mode
      and ra.model_key < rb.model_key
)

select
    model_a,
    model_b,
    prompt_variant,
    variant_label,
    reasoning_mode,
    run_a,
    run_b,
    count(*)                                    as n,
    count_if(correct_a and correct_b)           as both_correct,
    count_if(correct_a and not correct_b)       as a_only,
    count_if(not correct_a and correct_b)       as b_only,
    count_if(not correct_a and not correct_b)   as both_wrong,
    avg(correct_a::int)                         as accuracy_a,
    avg(correct_b::int)                         as accuracy_b,
    avg(correct_a::int) - avg(correct_b::int)   as accuracy_diff,
    median(time_a)                              as median_time_a,
    median(time_b)                              as median_time_b
from pairs
group by all
