-- Invariant du protocole : quand le raisonnement est desactive, le modele ne doit produire
-- aucun token de raisonnement. Sans cela, les temps et les longueurs ne sont plus comparables.
select run_id, question_id, reasoning_tokens
from {{ ref('fct_answer') }}
where reasoning_mode = 'off'
  and reasoning_tokens > 0
