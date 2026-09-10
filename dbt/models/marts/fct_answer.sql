-- Grain le plus fin du benchmark : une ligne par (run, question), enrichie des attributs
-- de la question et du run pour eviter des jointures repetees cote dashboard.
select
    a.run_id,
    a.question_id,
    a.model_key,
    r.model_short,
    a.prompt_variant,
    r.variant_label,
    a.reasoning_mode,
    a.transport,
    a.prompt_version,
    a.prompt_sha256,

    q.category,
    q.category_group,
    q.difficulty,
    q.type,
    q.n_options,
    q.correct_letter,
    q.correct_answer,
    q.question,
    q.question_chars,
    q.question_words,

    a.ai_answer,
    a.ai_reasoning,
    a.predicted_letter,
    a.predicted_text,
    a.ai_correct,
    a.grade,
    a.grade_score,
    a.grade not in ('unparseable', 'error')      as is_parsed,
    -- Le format demande depend du type : une lettre en choix multiples, le mot lui-meme
    -- en vrai/faux. Distinguer les deux evite de compter une reponse conforme comme un ecart.
    (
        (q.type = 'multiple' and a.grade = 'letter')
        or (q.type = 'boolean' and a.grade in ('exact', 'letter'))
    )                                            as is_expected_format,
    case when q.type = 'multiple' then 0.25 else 0.5 end as chance_baseline,

    a.response_time,
    a.ttft_s,
    a.tokens_per_second,
    a.response_time / nullif(a.completion_tokens, 0) as time_per_token,
    a.prompt_tokens,
    a.completion_tokens,
    a.reasoning_tokens,
    length(a.ai_answer)                          as answer_chars,
    a.finish_reason,
    a.run_order,
    a.attempt,
    a.called_at,
    a.error
from {{ ref('stg_answers') }} as a
inner join {{ ref('stg_questions') }} as q using (question_id)
inner join {{ ref('dim_run') }} as r using (run_id)
