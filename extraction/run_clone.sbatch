#!/bin/bash
#SBATCH --job-name=clone-repos
#SBATCH --account=safety_first
#SBATCH --partition=expansion
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=06:00:00
#SBATCH --output=logs/%x-%j.out
# Bare clones of the sampled repositories (network only; no GPU). Usage, from this folder: sbatch run_clone.sbatch
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"
../.venv/bin/python -I clone_repos.py repos_sample.csv /resnick/scratch/aquisper/github_multiagent --max-mb 500 --workers 8
