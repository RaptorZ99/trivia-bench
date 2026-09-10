-- Question metier : sur quels themes le modele reussit-il ou echoue-t-il ?
with agg as (
    select
        run_id,
        model_short,
        prompt_variant,
        variant_label,
        reasoning_mode,
        category,
        category_group,
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
    {{ wilson_hi('n_correct', 'n') }}                  as wilson_hi,
    -- En dessous de 30 reponses, l'intervalle est trop large pour conclure : on le signale
    -- plutot que de masquer la categorie.
    n < 30                                             as n_flag_low,
    rank() over (partition by run_id order by n_correct::double / nullif(n, 0) desc)
        as rank_in_run
from agg
