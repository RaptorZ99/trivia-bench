#!/usr/bin/env bash
# Suivi en temps reel d'une campagne de benchmark.
#
# Affiche la progression du run en cours et le decompte de tous les runs du jeu.
# Le debit et l'estimation sont lisses sur toute la duree d'observation, sinon ils
# sautent d'un rafraichissement a l'autre.
#
# Usage : scripts/watch.sh [intervalle_en_secondes]

set -uo pipefail
cd "$(dirname "$0")/.."

TOTAL=${TOTAL:-5257}
PAUSE=${1:-2}
LARGEUR=40

depart_n=""
depart_t=""

while :; do
  actif=$(ls -t data/bronze/llm_responses/*.jsonl 2>/dev/null | head -1)
  if [ -z "$actif" ]; then
    printf "\rAucun run en cours.        "
    sleep "$PAUSE"
    continue
  fi

  n=$(wc -l < "$actif" | tr -d ' ')
  maintenant=$(date +%s)
  [ -z "$depart_n" ] && { depart_n=$n; depart_t=$maintenant; }

  ecoule=$((maintenant - depart_t))
  faits=$((n - depart_n))
  if [ "$ecoule" -gt 0 ] && [ "$faits" -gt 0 ]; then
    debit=$(awk -v f="$faits" -v e="$ecoule" 'BEGIN{printf "%.2f", f/e}')
    reste=$(awk -v r="$((TOTAL - n))" -v f="$faits" -v e="$ecoule" 'BEGIN{printf "%d", r*e/f/60}')
    fin=$(awk -v r="$((TOTAL - n))" -v f="$faits" -v e="$ecoule" 'BEGIN{printf "%d", r*e/f}')
    fin=$(date -v +"${fin}"S '+%H:%M' 2>/dev/null || echo "?")
    info=$(printf "%5s rep/s   reste %4s min   fin ~%s" "$debit" "$reste" "$fin")
  else
    info="        mesure du debit en cours..."
  fi

  pct=$((n * 100 / TOTAL))
  rempli=$((pct * LARGEUR / 100))
  barre=$(printf '%*s' "$rempli" '' | tr ' ' '#')$(printf '%*s' $((LARGEUR - rempli)) '' | tr ' ' '.')
  nom=$(basename "$actif" .jsonl | sed 's/__roff__.*//')

  printf '\033[H\033[J'
  printf '  Campagne en cours — %s\n\n' "$(date '+%H:%M:%S')"
  printf '  %s\n' "$nom"
  printf '  [%s] %3d%%   %5d / %d\n' "${barre//#/█}" "$pct" "$n" "$TOTAL"
  printf '  %s\n\n' "$info"
  printf '  Tous les runs\n'
  for f in data/bronze/llm_responses/*.jsonl; do
    c=$(wc -l < "$f" | tr -d ' ')
    etat=$([ "$c" -ge "$TOTAL" ] && echo "termine" || echo "en cours")
    printf '    %-46s %5d  %s\n' "$(basename "$f" .jsonl | sed 's/__roff__.*//')" "$c" "$etat"
  done
  printf '\n  Ctrl+C pour quitter\n'

  sleep "$PAUSE"
done
