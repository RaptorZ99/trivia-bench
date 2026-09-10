{#
    Le comportement par defaut de dbt prefixe le schema personnalise par celui de la cible
    (`main_gold`), et la macro `generate_schema_name_for_env` ignore le schema personnalise
    hors production. Ce projet est mono-utilisateur et local : on veut simplement `staging`
    et `gold`, tels que declares dans `dbt_project.yml`.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
