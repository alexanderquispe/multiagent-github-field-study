#!/bin/bash
#SBATCH --job-name=line-edges
#SBATCH --account=safety_first
#SBATCH --partition=expansion
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=logs/%x-%j.out
# Who deleted whose lines, per repository (local git only). Usage, from this folder: sbatch run_line_edges.sbatch
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"
../.venv/bin/python -I git_line_edges.py ../extraction/repos_sample.csv /resnick/scratch/aquisper/github_multiagent --workers 32
