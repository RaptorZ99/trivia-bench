-- Grain de la couche silver : une seule reponse par couple (run, question).
-- Une reprise re-interroge les questions restees en erreur, et le journal brut est ecrit en
-- ajout : sans deduplication a la notation, la meme question porterait deux lignes et tous
-- les comptages du rapport seraient fausses.
select
    run_id,
    question_id,
    count(*) as n_answers
from {{ ref('fct_answer') }}
group by run_id, question_id
having count(*) > 1
