# Hypotheses fixed before downloading the second sample

Written on 2026-11-21, before any data of the second sample was downloaded or looked at.

## Why this file exists

In the first sample (240 repositories) we tried three definitions of scarcity on ten outcomes. One combination came out
significant, and one more pattern pointed the same way without being significant. With about 30 comparisons, one or two
are expected by chance. The second sample tests only those two, with every choice fixed here.

## Sample

2,000 repositories listed in `extraction/repos_sample_wave2.csv`, drawn from the same public dataset (AIDev, release
with cutoff 2026-03-31) with the same eligibility as the first sample, any number of agent users. None of the 240
repositories of the first sample is included. All 954 eligible repositories with five or more agent users are taken;
the other 1,046 are a random draw (seed 43). Data: pull requests and issues from 2025-01-01 to the download date.

## Hypothesis 1 (main): backlog

When a second person starts using an agent in a repository, the share of the first agent user's agent pull requests
that get merged falls more in repositories that already had a backlog than in repositories that did not.

- Event, controls, window, fixed effects and standard errors: exactly `outcomes/event_study.py` with its defaults
  (`--min-prs 1 --kth 2 --pre 3 --post 5 --split backlog`).
- Backlog: pull requests open at the start of the event month, divided by pull requests merged per month over the three
  previous months. A repository has a backlog if this is above **0.11** (the median of the first sample; the cut is
  not re-estimated).
- Outcome: `inc_merged`.
- Test: difference (backlog minus no backlog) of the two post-arrival estimates, one-sided, 5% level.
  First sample: -14.1 points (standard error 6.3).
- Confirmed if the difference is negative and significant. Not confirmed otherwise.

## Hypothesis 2 (secondary): many users

For the same person in the same repository, agent pull requests are merged less often when eight or more people are
using agents in the repository (previous 30 days, counting the author) than when that person is the only one.

- Exactly `outcomes/dose_users.py`, outcome "Mergeado (%)", category "8 o más".
- Test: coefficient negative, one-sided, 5% level. First sample: -5.2 points (standard error 3.6).

## Everything else

Any other outcome, split or definition run on the second sample is exploratory and will be reported as such.
The two samples may be pooled afterwards for descriptive figures, never for these two tests.

## Amendment, 2026-11-21 (during the download, before any outcome of the second sample was computed)

Four repositories are excluded from the second sample because they are package registries: the repository is the
collection of package definitions of a package manager, and almost all of its pull requests are version updates, not
software development. They are NixOS/nixpkgs, microsoft/winget-pkgs, Homebrew/homebrew-core and Homebrew/homebrew-cask
(listed in `extraction/repos_wave2_excluded.csv`). The rule was applied by repository name and purpose, without looking
at any pull request data. The sample used is `extraction/repos_sample_wave2_run.csv` (1,996 repositories).
Nothing else in this file changes.
