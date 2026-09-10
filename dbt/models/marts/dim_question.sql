-- Referentiel des questions evaluees (les exemples few-shot sont conserves mais marques).
select * from {{ ref('stg_questions') }}
