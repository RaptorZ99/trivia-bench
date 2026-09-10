-- Les questions servant d'exemples dans les prompts few-shot ne doivent jamais etre evaluees :
-- le modele en a vu la reponse dans son propre contexte.
select a.run_id, a.question_id
from {{ ref('fct_answer') }} as a
inner join {{ ref('dim_question') }} as q using (question_id)
where q.is_fewshot_example
