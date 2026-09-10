-- Question metier : deux variantes different-elles vraiment, ou l'ecart tient-il au hasard ?
-- Les variantes sont evaluees sur les memes questions : la comparaison est appariee et se
-- resume aux paires discordantes, qui alimentent un test de McNemar cote dashboard.
with runs as (
    select run_id, model_key, model_short, prompt_variant, variant_label, reasoning_mode
    from {{ ref('dim_run') }}
),

pairs as (
    select
        a.run_id                as run_a,
        b.run_id                as run_b,
        ra.model_short,
        ra.reasoning_mode,
        ra.prompt_variant       as variant_a,
        rb.prompt_variant       as variant_b,
        ra.variant_label        as variant_a_label,
        rb.variant_label        as variant_b_label,
        a.ai_correct            as correct_a,
        b.ai_correct            as correct_b
    from {{ ref('fct_answer') }} as a
    inner join {{ ref('fct_answer') }} as b using (question_id)
    inner join runs as ra on a.run_id = ra.run_id
    inner join runs as rb on b.run_id = rb.run_id
    where ra.model_key = rb.model_key
      and ra.reasoning_mode = rb.reasoning_mode
      and ra.prompt_variant < rb.prompt_variant
)

select
    model_short,
    reasoning_mode,
    variant_a,
    variant_b,
    variant_a_label,
    variant_b_label,
    run_a,
    run_b,
    count(*)                                            as n,
    count_if(correct_a and correct_b)                   as both_correct,
    count_if(correct_a and not correct_b)               as a_only,
    count_if(not correct_a and correct_b)               as b_only,
    count_if(not correct_a and not correct_b)           as both_wrong,
    avg(correct_a::int)                                 as accuracy_a,
    avg(correct_b::int)                                 as accuracy_b,
    avg(correct_a::int) - avg(correct_b::int)           as accuracy_diff,
    count_if(correct_a != correct_b)                    as n_discordant
from pairs
group by all
