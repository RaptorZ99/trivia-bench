-- L'exactitude observee doit toujours tomber dans son propre intervalle de confiance.
-- Un echec signalerait une erreur dans la macro statistique ou dans les comptages.
select run_id, accuracy, wilson_lo, wilson_hi
from {{ ref('mart_run_summary') }}
where accuracy is not null
  and (accuracy < wilson_lo - 1e-9 or accuracy > wilson_hi + 1e-9)
