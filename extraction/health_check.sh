#!/bin/bash
# Checks the second-sample download every 10 minutes and appends one line to logs/wave2_health.log.
# Usage: bash health_check.sh JOB_ID. Stops (so that whoever launched it is told) when the job leaves the queue,
# when nothing was written in two checks in a row, or when more than 5 repositories failed since the last check.
job=$1; D=/resnick/scratch/aquisper/github_multiagent; cd "$(dirname "$0")"
keys=$(tail -n +2 repos_sample_wave2_run.csv | cut -d, -f7 | sed 's#/#__#')
total=$(echo $keys | wc -w); last_bytes=0; last_fail=0; still=0
while true; do
  state=$(squeue -j $job -h -o %T 2>/dev/null)
  prs=$(for k in $keys; do [ -e $D/repos/$k.json ] && echo 1; done | wc -l)
  iss=$(for k in $keys; do [ -e $D/issues/$k.done ] && echo 1; done | wc -l)
  cl=$(for k in $keys; do [ -e $D/git/$k.done ] && echo 1; done | wc -l)
  fail=$(cat logs/wave2_prs.log logs/wave2_issues.log logs/wave2_clone.log 2>/dev/null | grep -c FAILED)
  bytes=$(( $(du -sb $D/prs $D/issues 2>/dev/null | awk "{s+=\$1} END{print s}") + cl * 1000000 ))
  line="$(date '+%m-%d %H:%M') job=${state:-GONE} of $total repos: prs=$prs issues=$iss clones=$cl failed=$fail GB=$(awk -v b=$bytes 'BEGIN{printf "%.1f", b/2^30}')"
  [ "$bytes" = "$last_bytes" ] && still=$((still+1)) || still=0
  if [ -z "$state" ]; then echo "$line END" >> logs/wave2_health.log; echo "$line END"; exit 0; fi
  if [ "$state" = RUNNING ] && [ $still -ge 2 ]; then echo "$line ALERT no progress" | tee -a logs/wave2_health.log; exit 1; fi
  if [ $((fail-last_fail)) -gt 5 ]; then echo "$line ALERT failures" | tee -a logs/wave2_health.log; exit 1; fi
  echo "$line ok" >> logs/wave2_health.log; last_bytes=$bytes; last_fail=$fail; sleep 600
done
