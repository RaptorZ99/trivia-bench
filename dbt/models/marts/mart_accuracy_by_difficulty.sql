-- Question metier : la difficulte declaree par OpenTDB predit-elle celle percue par le modele ?
with agg as (
    select
        run_id,
        model_short,
        prompt_variant,
        variant_label,
        reasoning_mode,
        difficulty,
        case difficulty when 'easy' then 1 when 'medium' then 2 else 3 end as difficulty_rank,
        count(*)                as n,
        count_if(ai_correct)    as n_correct,
        {{ chance_baseline() }} as chance_baseline,
        median(response_time)   as median_response_time
    from {{ ref('fct_answer') }}
    group by all
)

select
    *,
    n_correct::double / nullif(n, 0)                   as accuracy,
    n_correct::double / nullif(n, 0) - chance_baseline as accuracy_above_chance,
    {{ wilson_lo('n_correct', 'n') }}                  as wilson_lo,
    {{ wilson_hi('n_correct', 'n') }}                  as wilson_hi
from agg
order by run_id, difficulty_rank
