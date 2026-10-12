#!/usr/bin/env bash
# Starter de to processer, worker-servicen består af:
#   scheduler.py  lægger forfaldne jobs i køen ud fra løbskalenderen
#   runner.py     henter dem fra køen og udfører dem
#
# De kører som søskende frem for i samme proces, så en fejl i den ene ikke kan
# vælte den anden — og `wait -n` lader containeren dø, så snart ÉN af dem
# stopper. Railway genstarter den så. Alternativet, at lade den overlevende
# køre videre alene, er den værste tilstand: køen fyldes uden at blive tømt
# (eller omvendt), og alt ser ud til at virke.
set -euo pipefail

echo "[worker] starter skemalægger og runner"

python scheduler.py --loop &
SKEMA=$!

python runner.py &
RUNNER=$!

wait -n "$SKEMA" "$RUNNER"
echo "[worker] en af processerne stoppede — lader containeren dø, så Railway genstarter"
exit 1
