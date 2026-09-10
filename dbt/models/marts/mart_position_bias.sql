-- Question metier : le modele privilegie-t-il une position d'option, independamment du contenu ?
-- L'ordre des options etant melange de facon deterministe, un ecart marque entre la
-- distribution des lettres predites et celle des bonnes reponses signale un biais de position.
with mc as (
    select *
    from {{ ref('fct_answer') }}
    where type = 'multiple'
),

by_correct as (
    select
        run_id,
        model_short,
        prompt_variant,
        variant_label,
        reasoning_mode,
        correct_letter          as letter,
        count(*)                as n_is_correct_letter,
        count_if(ai_correct)    as n_correct
    from mc
    group by all
),

by_predicted as (
    select
        run_id,
        coalesce(predicted_letter, '?') as letter,
        count(*)                        as n_predicted
    from mc
    group by all
),

totals as (
    select run_id, count(*) as n_total
    from mc
    group by run_id
)

select
    c.run_id,
    c.model_short,
    c.prompt_variant,
    c.variant_label,
    c.reasoning_mode,
    c.letter,
    c.n_is_correct_letter,
    c.n_correct,
    c.n_correct::double / nullif(c.n_is_correct_letter, 0) as accuracy_when_correct_letter,
    coalesce(p.n_predicted, 0)                            as n_predicted,
    coalesce(p.n_predicted, 0)::double / nullif(t.n_total, 0) as share_predicted,
    c.n_is_correct_letter::double / nullif(t.n_total, 0)  as share_is_correct_letter
from by_correct as c
left join by_predicted as p on c.run_id = p.run_id and c.letter = p.letter
inner join totals as t on c.run_id = t.run_id
order by c.run_id, c.letter
