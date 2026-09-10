-- Question metier : comment se compare la performance aux choix multiples et au vrai/faux,
-- une fois retire le niveau du hasard (25 % contre 50 %) ?
with agg as (
    select
        run_id,
        model_short,
        prompt_variant,
        variant_label,
        reasoning_mode,
        type,
        count(*)                as n,
        count_if(ai_correct)    as n_correct,
        {{ chance_baseline() }} as chance_baseline
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
