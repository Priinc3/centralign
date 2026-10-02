#!/usr/bin/env bash
# The demo an evaluator runs, start to finish: seeded invoice -> approval -> ERP post -> evidence.
#
#   bash demo/run.sh                 # cold run, scratch DB + scratch runs dir  -> replayed=0
#   bash demo/run.sh --append        # same scratch, nothing wiped              -> replayed=2
#   bash demo/run.sh /tmp/myscratch  # use a different scratch root
#
# Everything it touches lives under $SCRATCH (default /tmp/centralign-demo) and is recreated on a
# cold run: a leftover ERP row or a warm ledger is what made the B1 demo unreadable. Nothing is
# deleted outside that path, and the only network it touches is 127.0.0.1.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRATCH="${CENTRALIGN_SCRATCH:-/tmp/centralign-demo}"

args=()
for arg in "$@"; do
  case "$arg" in
    /*) SCRATCH="$arg" ;;                       # a bare /tmp path sets the scratch root
    *) args+=("$arg") ;;                       # everything else goes to the CLI
  esac
done

case "$SCRATCH" in
  /tmp/*) ;;
  *) printf 'refusing to use %s as scratch: keep it under /tmp (or set CENTRALIGN_SCRATCH)\n' "$SCRATCH" >&2
     exit 2 ;;
esac

cd "$ROOT"
printf 'CentrAlign demo · scratch %s · offline, no API key needed\n' "$SCRATCH"
python3 -m src.cli.main doctor >/dev/null || { echo "doctor says this machine is not ready:" >&2
  python3 -m src.cli.main doctor >&2; exit 1; }
exec python3 -m src.cli.main demo \
  --runs "$SCRATCH/runs" \
  --db "$SCRATCH/sim.db" \
  --queue "$SCRATCH/gate.jsonl" \
  --approve demo-operator \
  ${args[@]+"${args[@]}"}