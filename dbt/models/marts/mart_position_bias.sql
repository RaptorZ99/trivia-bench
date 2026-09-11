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
    -- Seules les lettres reellement predites entrent ici. Une reponse dont aucune lettre n'a
    -- pu etre extraite n'a pas de position a comparer : la compter sous une etiquette « ? »
    -- serait sans effet, la jointure ci-dessous etant pilotee par les lettres correctes.
    select
        run_id,
        predicted_letter as letter,
        count(*)         as n_predicted
    from mc
    where predicted_letter is not null
    group by all
),

totals as (
    -- `n_no_letter` est expose pour que le complement a cent des parts predites soit lisible
    -- plutot que silencieux : sans lui, la somme des `share_predicted` tombe sous 1 sans
    -- que la table dise pourquoi.
    select
        run_id,
        count(*)                                as n_total,
        count_if(predicted_letter is null)      as n_no_letter
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
    c.n_is_correct_letter::double / nullif(t.n_total, 0)  as share_is_correct_letter,
    t.n_no_letter,
    t.n_no_letter::double / nullif(t.n_total, 0)          as share_no_letter
from by_correct as c
left join by_predicted as p on c.run_id = p.run_id and c.letter = p.letter
inner join totals as t on c.run_id = t.run_id
order by c.run_id, c.letter
