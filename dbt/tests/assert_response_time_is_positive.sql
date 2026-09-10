-- Un temps de reponse nul ou negatif revelerait une mesure cassee.
select run_id, question_id, response_time
from {{ ref('fct_answer') }}
where error is null
  and (response_time is null or response_time <= 0)
