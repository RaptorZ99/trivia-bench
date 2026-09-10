#!/usr/bin/env bash
# Suivi en temps reel d'une campagne de benchmark.
#
# Affiche la progression du run en cours et le decompte de tous les runs du jeu.
#
# Deux details evitent le scintillement. L'image n'est jamais effacee : le curseur
# remonte du nombre de lignes du cadre precedent et chaque ligne est reecrite par-dessus,
# terminee par un effacement de fin de ligne. Et le cadre entier part en une seule
# ecriture, sans quoi le terminal affiche un etat intermediaire.
#
# Le debit est lisse depuis le lancement : mesure sur un seul rafraichissement, il saute
# d'un facteur deux d'une seconde a l'autre et l'estimation devient inutile.
#
# Usage : scripts/watch.sh [intervalle_en_secondes]

set -uo pipefail
cd "$(dirname "$0")/.."

TOTAL=${TOTAL:-5257}
PAUSE=${1:-2}
LARGEUR=40
EFF=$'\033[K'          # efface jusqu'a la fin de la ligne

lignes_precedentes=0
depart_n=""
depart_t=""

printf '\033[?25l'                                   # curseur masque
restaurer() { printf '\033[?25h\n'; exit 0; }
trap restaurer INT TERM EXIT

while :; do
  actif=$(ls -t data/bronze/llm_responses/*.jsonl 2>/dev/null | head -1)
  cadre=""

  if [ -z "$actif" ]; then
    cadre="  Aucun run en cours.${EFF}"$'\n'
  else
    n=$(wc -l < "$actif" | tr -d ' ')
    maintenant=$(date +%s)
    [ -z "$depart_n" ] && { depart_n=$n; depart_t=$maintenant; }

    ecoule=$((maintenant - depart_t))
    faits=$((n - depart_n))
    if [ "$ecoule" -gt 0 ] && [ "$faits" -gt 0 ]; then
      lu=$(awk -v f="$faits" -v e="$ecoule" -v r="$((TOTAL - n))" \
        'BEGIN{printf "%.2f %d %d", f/e, r*e/f/60, r*e/f}')
      debit=${lu% * *}; reste=$(echo "$lu" | cut -d' ' -f2); secondes=$(echo "$lu" | cut -d' ' -f3)
      fin=$(date -v +"${secondes}"S '+%H:%M' 2>/dev/null || echo '?')
      info=$(printf '%s rep/s   reste %s min   fin ~%s' "$debit" "$reste" "$fin")
    else
      info="mesure du debit en cours…"
    fi

    pct=$((n * 100 / TOTAL))
    rempli=$((pct * LARGEUR / 100))
    barre=$(printf '%*s' "$rempli" '' | tr ' ' '#')$(printf '%*s' $((LARGEUR - rempli)) '' | tr ' ' '.')
    barre=${barre//#/█}; barre=${barre//./░}
    nom=$(basename "$actif" .jsonl | sed 's/__roff__.*//')

    cadre+="  Campagne en cours — $(date '+%H:%M:%S')${EFF}"$'\n'"${EFF}"$'\n'
    cadre+="  ${nom}${EFF}"$'\n'
    cadre+="$(printf '  [%s] %3d%%   %5d / %d' "$barre" "$pct" "$n" "$TOTAL")${EFF}"$'\n'
    cadre+="  ${info}${EFF}"$'\n'"${EFF}"$'\n'
    cadre+="  Tous les runs${EFF}"$'\n'
    for f in data/bronze/llm_responses/*.jsonl; do
      c=$(wc -l < "$f" | tr -d ' ')
      etat=$([ "$c" -ge "$TOTAL" ] && echo 'termine' || echo 'en cours')
      cadre+="$(printf '    %-44s %5d  %s' "$(basename "$f" .jsonl | sed 's/__roff__.*//')" "$c" "$etat")${EFF}"$'\n'
    done
    cadre+="${EFF}"$'\n'"  Ctrl+C pour quitter${EFF}"$'\n'
  fi

  hauteur=$(printf '%s' "$cadre" | grep -c '' )
  # Remonte du cadre precedent puis reecrit par-dessus, en une seule ecriture.
  [ "$lignes_precedentes" -gt 0 ] && printf '\033[%dA' "$lignes_precedentes"
  printf '%s' "$cadre"
  lignes_precedentes=$hauteur

  sleep "$PAUSE"
done
