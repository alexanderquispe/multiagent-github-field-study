#!/bin/bash
#SBATCH --job-name=wave2-extract
#SBATCH --account=safety_first
#SBATCH --partition=expansion
#SBATCH --cpus-per-task=16
#SBATCH --mem=48G
#SBATCH --time=48:00:00
#SBATCH --output=logs/%x-%j.out
# Second sample: pull request metadata, issues, clones (network; no GPU). Every step skips what is already done,
# so the job can be resubmitted. Usage, from this folder: sbatch run_wave2.sbatch
set -uo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"
unset SSL_CERT_DIR
export SSL_CERT_FILE=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem
D=/resnick/scratch/aquisper/github_multiagent
PY=../.venv/bin/python
$PY fetch_prs.py repos_sample_wave2_run.csv $D --workers 27 >> logs/wave2_prs.log 2>> logs/wave2_prs_stats.log
$PY fetch_issues.py repos_sample_wave2_run.csv $D --workers 27 >> logs/wave2_issues.log 2>> logs/wave2_issues_stats.log
$PY -I clone_repos.py repos_sample_wave2_run.csv $D --max-mb 500 --workers 12 >> logs/wave2_clone.log 2>&1
echo finished
