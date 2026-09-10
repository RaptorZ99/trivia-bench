-- Referentiel des runs, enrichi d'un libelle lisible pour le dashboard.
select
    r.*,
    replace(model_key, 'google/', '') as model_short,
    case prompt_variant
        when 'v1_open' then 'V1 · Question ouverte'
        when 'v2_letter' then 'V2 · Lettre seule'
        when 'v3_simple_evals' then 'V3 · Contrat de sortie'
        when 'v4_fewshot' then 'V4 · Few-shot'
        when 'v5_json' then 'V5 · JSON contraint'
        else prompt_variant
    end as variant_label,
    case when reasoning_mode = 'on' then 'avec raisonnement' else 'sans raisonnement' end
        as reasoning_label,
    date_diff('second', started_at, finished_at) as duration_s
from {{ ref('stg_runs') }} as r
