# Do coding agents get in each other's way? A field test on GitHub

Simulations predict that a team does worse when several people each bring their own AI agent
("Worse Together", arXiv 2610.00583). This repository tests that prediction with public GitHub data:
when a second, third or n-th developer starts using a coding agent in a repository, what happens to
the pull requests of the developers who were already there?

Status (November 2026): first sample analysed; a second, larger sample is being downloaded to test two
hypotheses that were fixed in advance ([preregistration](outcomes/preregistration_2026-11-21.md)).

## Data

- Repositories come from the public AIDev dataset (release with cutoff 2026-03-31): at least 10 agent
  pull requests, not a fork. First sample: 240 repositories. Second sample: 1,996.
- For each repository: every pull request and issue since 2025-01-01 (GitHub GraphQL API) and a bare
  clone with the head of every pull request. First sample: 240,024 pull requests, 56,561 issues.
- A pull request counts as written by an agent if the author is the agent's bot account, the branch
  carries the agent's prefix, or the description or commits carry its signature (Claude Code, Codex,
  Copilot, Cursor, Devin, Jules). Against AIDev's own labels: 99.7% recall, and the product never
  disagrees.

## Outcomes, one row per pull request

Merged or not, hours to merge, whether it broke the default branch (green on its own, red right after
the merge), whether it was reverted, and how many of its lines were deleted within 30 days by someone
else's pull request (from `git blame` on every commit of the default branch). Exposure to other
people's agents is always measured at the moment the pull request is opened.

## Results on the first sample

- Raw comparisons look bad: with more agent pull requests of other people open, the merge rate goes
  from 89% to 78% and the median time to merge from 0.6 to 9.2 hours.
- Most of that is which repositories and people are being compared. Within the same person in the same
  repository the differences are small and not significant (merged: -0.6 points, s.e. 1.1).
- Event study at the arrival of the second agent user (stacked difference-in-differences, 136 treated
  and 73 control repositories): no drop in the first user's merge rate (-2.0 points, s.e. 3.4).
- No sign that people without agents are crowded out, and nothing at four agent users.
- Two patterns pointed towards harm among about thirty comparisons (repositories with a backlog; eight
  or more agent users). They are the two preregistered hypotheses for the second sample.

## Layout

| Folder | What it does |
|---|---|
| `extraction/` | Choose the repositories, download pull requests and issues, clone, build the pull request table |
| `outcomes/` | Line-level tracing, outcomes, descriptives, event study, crowd-out, dose-response; results and figures in `outcomes/results/` |
| `replication/` | Replication of an earlier study of concurrent agent pull requests on the same dataset |

Each script starts with a usage line. GitHub tokens are read from a local `.env` file that is not part
of the repository. The `.sbatch` files are written for a Slurm cluster and contain its paths.
