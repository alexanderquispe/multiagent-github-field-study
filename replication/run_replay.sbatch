#!/bin/bash
#SBATCH --job-name=pr-replay
#SBATCH --account=safety_first
#SBATCH --partition=expansion
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=logs/%x-%j.out
# Merge replay of pull request pairs (network only; no GPU). Usage, from this folder: sbatch run_replay.sbatch
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"
unset SSL_CERT_DIR
export SSL_CERT_FILE=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem
export REPLAY_TMP=/resnick/scratch/aquisper/aidev/replay_tmp
mkdir -p "$REPLAY_TMP"
PY=../.venv/bin/python
$PY replay_pairs.py pairs_paper_sample.csv results/replay_paper_sample.csv --workers 12
$PY replay_pairs.py pairs_user_sample.csv results/replay_user_sample.csv --workers 12
