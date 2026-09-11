-- Garantie centrale d'ADR-15 : tous les modeles sont servis par le meme moteur d'inference.
-- Comparer des latences produites par `llama.cpp` et par `mlx-llm` mesurerait le moteur autant
-- que le modele, et deux versions du meme moteur ne se comparent pas davantage : la version
-- fait partie de son identite, d'ou l'exigence d'un numero.
--
-- Le moteur est lu dans `lms runtime ls`, qui coche **un moteur par format** : une lecture qui
-- retiendrait la mauvaise ligne enregistrerait `mlx-llm` sur un run servi en GGUF, sans que
-- rien d'autre ne le signale.
--
-- `model_format` est verifie quand il est renseigne : la colonne a ete ajoutee apres le premier
-- run, dont le format reste atteste par le nom du moteur (`llama.cpp` ne sert que du GGUF).
with controle as (
    select
        count(*)                                                     as n_runs,
        count(distinct runtime_engine)                               as n_moteurs,
        count_if(runtime_engine is null)                             as n_sans_moteur,
        count_if(runtime_engine not like '%@%')                      as n_sans_version,
        count(distinct model_format)                                 as n_formats,
        count_if(model_format is not null and model_format <> 'gguf') as n_hors_gguf
    from {{ ref('dim_run') }}
)

select *
from controle
where n_moteurs <> 1
   or n_sans_moteur > 0
   or n_sans_version > 0
   or n_formats > 1
   or n_hors_gguf > 0
