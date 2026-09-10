-- Question metier : comment les bonnes reponses sont-elles reconnues, et quelle part des
-- reponses est inexploitable ? Separe l'echec de connaissance de l'echec de format.
with agg as (
    select
        run_id,
        model_short,
        prompt_variant,
        variant_label,
        reasoning_mode,
        grade,
        count(*) as n
    from {{ ref('fct_answer') }}
    group by all
),

totals as (
    select run_id, sum(n) as n_total
    from agg
    group by run_id
)

select
    agg.*,
    totals.n_total,
    agg.n::double / nullif(totals.n_total, 0) as share,
    grade in ('letter', 'exact', 'fuzzy', 'contains') as counts_as_correct
from agg
inner join totals using (run_id)
order by run_id, n desc
