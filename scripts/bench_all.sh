#!/usr/bin/env bash
# Enchaine les variantes de prompt et relance celles qui n'ont pas abouti.
#
# Un run complet dure plusieurs heures sur une machine de 16 Go partagee avec le modele :
# il peut etre interrompu par la pression memoire. `trivia bench` reprend automatiquement
# un run inacheve de meme configuration, ce script se contente donc de reessayer.
#
# Usage : scripts/bench_all.sh [--model CLE] [--reasoning off|on] [--sample SPEC] [variante...]

set -uo pipefail
cd "$(dirname "$0")/.."

MODEL=""
REASONING="off"
SAMPLE=""
VARIANTS=()
MAX_ATTEMPTS=${MAX_ATTEMPTS:-12}

while [ $# -gt 0 ]; do
  case "$1" in
    --model) MODEL="$2"; shift 2 ;;
    --reasoning) REASONING="$2"; shift 2 ;;
    --sample) SAMPLE="$2"; shift 2 ;;
    *) VARIANTS+=("$1"); shift ;;
  esac
done

if [ ${#VARIANTS[@]} -eq 0 ]; then
  VARIANTS=(v1_letter v3_fewshot v4_json v2_simple_evals)
fi

args=(--reasoning "$REASONING")
[ -n "$MODEL" ] && args+=(--model "$MODEL")
[ -n "$SAMPLE" ] && args+=(--sample "$SAMPLE")

echo "=== Campagne demarree le $(date '+%F %T') ==="
echo "Variantes : ${VARIANTS[*]} | modele : ${MODEL:-defaut} | raisonnement : $REASONING | echantillon : ${SAMPLE:-complet}"

for variant in "${VARIANTS[@]}"; do
  attempt=1
  while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
    echo "--- $variant (tentative $attempt/$MAX_ATTEMPTS) a $(date '+%T') ---"
    uv run trivia bench --variant "$variant" "${args[@]}" 2>&1 | tr '\r' '\n' | grep -viE '^\s*$' | tail -6

    # Le manifeste fait foi : `complete` signifie que toutes les questions ont ete traitees.
    if uv run python - "$variant" "$REASONING" "${SAMPLE:-all}" <<'PY'
import sys
from trivia_bench.bench.runner import find_resumable_run
from trivia_bench.config import get_settings
from trivia_bench.paths import DataPaths

variant, reasoning, sample = sys.argv[1], sys.argv[2], sys.argv[3]
settings = get_settings()
paths = DataPaths(settings.data_dir)
pending = find_resumable_run(
    paths,
    model_key=settings.lmstudio_model_key,
    variant_id=variant,
    reasoning_mode=reasoning,
    sample_spec=sample,
)
sys.exit(1 if pending else 0)
PY
    then
      echo "--- $variant termine a $(date '+%T') ---"
      break
    fi

    echo "--- $variant incomplet, nouvelle tentative dans 20 s ---"
    sleep 20
    attempt=$((attempt + 1))
  done
done

echo "=== Campagne terminee le $(date '+%F %T') ==="
