-- Question metier : quelles questions sont ratees par toutes les variantes (candidates a
-- l'ambiguite ou a une lacune reelle) et lesquelles donnent des reponses instables ?
with per_question as (
    select
        model_short,
        question_id,
        category,
        difficulty,
        type,
        question,
        correct_answer,
        count(*)                        as n_runs,
        count_if(ai_correct)            as n_correct,
        count_if(grade = 'unparseable') as n_unparseable,
        median(response_time)           as median_response_time
    from {{ ref('fct_answer') }}
    group by all
)

select
    *,
    n_correct::double / nullif(n_runs, 0) as correct_rate,
    n_correct = n_runs                    as all_correct,
    n_correct = 0                         as all_wrong,
    n_correct > 0 and n_correct < n_runs  as is_mixed
from per_question
