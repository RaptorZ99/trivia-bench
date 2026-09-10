{#
    Intervalle de Wilson pour une proportion.

    L'approximation normale (Wald) sort de l'intervalle [0, 1] et devient trompeuse quand
    l'effectif est faible ou la proportion proche de 0 ou 1, ce qui est frequent par categorie.
    L'intervalle de Wilson reste valide dans ces cas, d'ou son usage systematique ici.

        centre = p + z² / (2n)
        marge  = z * sqrt( p(1-p)/n + z² / (4n²) )
        borne  = (centre ± marge) / (1 + z²/n)
#}

{% macro wilson_lo(successes, trials, z=1.96) -%}
    case when {{ trials }} = 0 then null else
    (
        ({{ successes }}::double / {{ trials }}) + ({{ z }} * {{ z }}) / (2.0 * {{ trials }})
        - {{ z }} * sqrt(
            ({{ successes }}::double / {{ trials }})
            * (1 - ({{ successes }}::double / {{ trials }})) / {{ trials }}
            + ({{ z }} * {{ z }}) / (4.0 * {{ trials }} * {{ trials }})
        )
    ) / (1 + ({{ z }} * {{ z }}) / {{ trials }})
    end
{%- endmacro %}

{% macro wilson_hi(successes, trials, z=1.96) -%}
    case when {{ trials }} = 0 then null else
    (
        ({{ successes }}::double / {{ trials }}) + ({{ z }} * {{ z }}) / (2.0 * {{ trials }})
        + {{ z }} * sqrt(
            ({{ successes }}::double / {{ trials }})
            * (1 - ({{ successes }}::double / {{ trials }})) / {{ trials }}
            + ({{ z }} * {{ z }}) / (4.0 * {{ trials }} * {{ trials }})
        )
    ) / (1 + ({{ z }} * {{ z }}) / {{ trials }})
    end
{%- endmacro %}

{#
    Probabilite de reussite au hasard : une chance sur quatre en choix multiples,
    une sur deux en vrai/faux. Sur un groupe mixte, on pondere par le nombre de questions.
#}
{% macro chance_baseline() -%}
    avg(case when type = 'multiple' then 0.25 else 0.5 end)
{%- endmacro %}
