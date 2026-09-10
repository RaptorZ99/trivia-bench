#!/usr/bin/env bash
# Enchaine les campagnes de plusieurs modeles, un a la fois.
#
# Pour chaque modele : attend qu'aucune campagne ne tourne, decharge le modele courant,
# charge le nouveau dans la configuration de reference, verifie, puis lance les variantes.
#
# Un controle en echec arrete la chaine. C'est voulu : un modele charge dans une autre
# configuration, ou dont le gabarit de chat laisse fuiter des marqueurs, produirait des
# heures de donnees non comparables. Mieux vaut ne rien produire et trouver la chaine
# arretee au matin.
#
# Usage : scripts/chain.sh <cle_modele> [<cle_modele>...]

set -uo pipefail
cd "$(dirname "$0")/.."

LMS="${LMS:-$HOME/.lmstudio/bin/lms}"
CONTEXTE="${CONTEXTE:-4096}"

if [ $# -eq 0 ]; then
  echo "Usage : scripts/chain.sh <cle_modele> [<cle_modele>...]" >&2
  exit 2
fi

echo "=== Chaine demarree le $(date '+%F %T') · modeles : $* ==="

for modele in "$@"; do
  echo
  echo "########## $modele ##########"

  # Une campagne peut deja tourner : on attend qu'elle finisse plutot que de lui
  # arracher son modele sous les pieds.
  attente=0
  while pgrep -f 'bench_all\.sh' > /dev/null 2>&1; do
    [ "$attente" -eq 0 ] && echo "$(date '+%T') · campagne en cours, attente..."
    attente=1
    sleep 60
  done
  [ "$attente" -eq 1 ] && echo "$(date '+%T') · machine libre"

  echo "$(date '+%T') · chargement"
  "$LMS" unload --all > /dev/null 2>&1
  if ! "$LMS" load "$modele" --context-length "$CONTEXTE" --gpu max --parallel 1 \
       --identifier trivia-bench -y 2>&1 | tr '\r' '\n' | tail -2; then
    echo "ECHEC : chargement de $modele impossible — chaine arretee" >&2
    exit 1
  fi

  echo "$(date '+%T') · verifications"
  if ! uv run trivia check --model "$modele" 2>&1 | tail -30; then
    echo "ECHEC : les verifications de $modele ne passent pas — chaine arretee" >&2
    exit 1
  fi

  echo "$(date '+%T') · lancement des variantes"
  ./scripts/bench_all.sh --model "$modele"
  echo "$(date '+%T') · $modele termine"
done

echo
echo "=== Chaine terminee le $(date '+%F %T') ==="
