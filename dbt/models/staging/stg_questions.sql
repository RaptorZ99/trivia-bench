-- Questions nettoyees : typage explicite, aucune logique metier.
select
    question_id,
    category_id::smallint          as category_id,
    category,
    category_group,
    type::varchar                  as type,
    difficulty::varchar            as difficulty,
    question,
    correct_answer,
    incorrect_answers,
    options,
    correct_index::tinyint         as correct_index,
    correct_letter,
    n_options::tinyint             as n_options,
    question_chars::integer        as question_chars,
    question_words::integer        as question_words,
    is_fewshot_example,
    scraped_at
from {{ source('silver', 'questions') }}
