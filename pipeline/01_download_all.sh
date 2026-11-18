#!/usr/bin/env bash
# Phase 1: download every dataset for 2010-present, then convert to Parquet and check counts.
#
#   bash pipeline/01_download_all.sh            # everything, one after another (~6 h without a token)
#   bash pipeline/01_download_all.sh large      # HPD violations + complaints only (~4 h)
#   bash pipeline/01_download_all.sh medium     # everything else (~2 h)
#
# Each dataset continues even if an earlier one fails; failures are listed at the end.
# Set SOCRATA_APP_TOKEN (or put it in .env) to raise rate limits.
set -u
cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/bin/python}"
SINCE=2010-01-01

LARGE="hpd_violations:$SINCE hpd_complaints:$SINCE"
MEDIUM="hpd_vacates: dob_violations:$SINCE dob_ecb:$SINCE dob_complaints: dob_now_permits:$SINCE \
hpd_registrations: hpd_contacts: fdny_incidents:$SINCE nyc311_housing:$SINCE nyc311_housing_2010_2019:$SINCE"
# hpd_vacates: all years (records start 2012). dob_complaints: date is MM/DD/YYYY text, filtered later.
# registrations/contacts: current snapshot, no date filter. pluto: current version (run separately).

case "${1:-all}" in
  large) JOBS="$LARGE" ;; medium) JOBS="$MEDIUM" ;; all) JOBS="$MEDIUM $LARGE" ;;
  *) echo "usage: $0 [all|large|medium]"; exit 2 ;;
esac

failed=(); done_=()
for job in $JOBS; do
  name="${job%%:*}"; since="${job#*:}"
  echo "=== $(date -u +%FT%TZ) start $name ${since:+since $since}"
  if "$PY" pipeline/01_download.py --dataset "$name" ${since:+--since "$since"}; then
    done_+=("$name")
  else
    failed+=("$name"); echo "=== FAILED $name"
  fi
done
echo "=== $(date -u +%FT%TZ) downloads finished; converting to Parquet and checking counts"
[ ${#done_[@]} -gt 0 ] && "$PY" pipeline/01b_to_parquet.py "${done_[@]}" || failed+=("count-check")
echo "=== $(date -u +%FT%TZ) done. failed: ${failed[*]:-none}"
[ ${#failed[@]} -eq 0 ]
