-- Chaque reponse tombe dans exactement une categorie de notation : la somme des modes de
-- reconnaissance, des reponses fausses, inexploitables et en erreur doit couvrir le total.
with per_run as (
    select
        run_id,
        count(*)                                                        as n,
        count_if(grade in ('letter', 'exact', 'fuzzy', 'contains'))     as n_recognised,
        count_if(grade = 'wrong')                                       as n_wrong,
        count_if(grade = 'unparseable')                                 as n_unparseable,
        count_if(grade = 'error')                                       as n_error,
        count_if(ai_correct)                                            as n_correct
    from {{ ref('fct_answer') }}
    group by run_id
)

select *
from per_run
where n != n_recognised + n_wrong + n_unparseable + n_error
   or n_correct != n_recognised
