## 1. The paper's 747 pairs, replayed on our cluster

Labels here: {'CLEAN': 556, 'CONFLICT': 162, 'UNAVAIL_fetch': 23, 'UNAVAIL_nobase': 6}
Labels in the authors' file: {'CLEAN': 549, 'CONFLICT': 167, 'UNAVAIL_fetch': 25, 'UNAVAIL_nobase': 6}

| Stratum | Authors | Our replay |
|---|---|---|
| same-agent | 119/601 = 19.8% (16.8 to 23.2) | 116/604 = 19.2% (16.3 to 22.5) |
| cross-agent | 48/115 = 41.7% (33.1 to 50.9) | 46/114 = 40.4% (31.8 to 49.5) |

Pairs evaluable in both runs: 711; same label in 710; same conflicted files in 709.
Pairs that changed availability: 12.

## 2. The paper's sample, split by who opened the two pull requests

Pairs with both pull requests opened by a human account: 343 of 718.

| Agents | Users | Conflict rate |
|---|---|---|
| same-agent | same user | 47/272 = 17.3% (13.3 to 22.2) |
| same-agent | different users | 0/25 = 0.0% (0.0 to 13.3) |
| cross-agent | same user | 11/23 = 47.8% (29.2 to 67.0) |
| cross-agent | different users | 14/23 = 60.9% (40.8 to 77.8) |

## 3. Within-repository sample (repositories with at least one different-user pair)

Labels: {'CLEAN': 792, 'CONFLICT': 333, 'UNAVAIL_fetch': 35, 'UNAVAIL_nobase': 14}; repositories: 108.

| Agents | Users | Pairs pooled | Mean of repository rates | Repositories |
|---|---|---|---|---|
| same-agent | same user | 140/533 = 26.3% (22.7 to 30.2) | 26.9% | 79 |
| same-agent | different users | 137/481 = 28.5% (24.6 to 32.7) | 21.1% | 91 |
| cross-agent | same user | 9/19 = 47.4% (27.3 to 68.3) | 52.3% | 8 |
| cross-agent | different users | 47/92 = 51.1% (41.0 to 61.1) | 49.6% | 32 |

Same-agent pairs, repositories that have both kinds (72): different users 25.3%, same user 27.7%, difference -2.4 points (standard error 4.3; 28 repositories higher, 28 lower, 16 equal).

Pairs by how many of the two pull requests were merged in reality (0, 1, 2), and conflict rate:

| Users | Merged 0 | Merged 1 | Merged 2 |
|---|---|---|---|
| same user | 49/141 = 34.8% (27.4 to 42.9) | 86/258 = 33.3% (27.9 to 39.3) | 14/153 = 9.2% (5.5 to 14.8) |
| different users | 73/200 = 36.5% (30.1 to 43.4) | 96/278 = 34.5% (29.2 to 40.3) | 15/95 = 15.8% (9.8 to 24.4) |
