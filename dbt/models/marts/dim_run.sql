-- Referentiel des runs, enrichi de libelles lisibles pour le dashboard.
-- Le libelle de la variante vient du manifeste, donc du registre Python : le dupliquer ici
-- exposerait a une divergence silencieuse si les variantes changent.
select
    r.*,
    -- Nom court sans le prefixe d'editeur, quel qu'il soit : les modeles evalues viennent
    -- de trois editeurs differents, et un prefixe code en dur en laisserait passer deux.
    regexp_replace(model_key, '^[^/]+/', '') as model_short,
    case when reasoning_mode = 'on' then 'avec raisonnement' else 'sans raisonnement' end
        as reasoning_label,
    date_diff('second', started_at, finished_at) as duration_s
from {{ ref('stg_runs') }} as r
