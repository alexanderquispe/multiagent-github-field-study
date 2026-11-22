"""Download issues for the sampled repositories with the GitHub GraphQL API.

Usage: python fetch_issues.py REPOS_CSV OUT_DIR [--limit N] [--since 2025-01-01] [--workers 4]
Writes OUT_DIR/issues/OWNER__NAME.jsonl (one issue per line, newest first) and a marker OWNER__NAME.done.
Each issue carries the pull requests that closed it and the pull requests that mention it.
"""
import argparse
import concurrent.futures as cf
import json
import os

import pandas as pd

from fetch_prs import TOKENS, graphql, report_stats

QUERY = """
query($owner:String!, $name:String!, $cursor:String) {
  rateLimit { remaining resetAt cost }
  repository(owner:$owner, name:$name) {
    issues(first:50, after:$cursor, orderBy:{field:CREATED_AT, direction:DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title body state stateReason createdAt closedAt
        author { __typename login }
        labels(first:10) { nodes { name } }
        assignees(first:5) { nodes { login } }
        comments { totalCount }
        closedByPullRequestsReferences(first:10, includeClosedPrs:true) { nodes { number } }
        timelineItems(itemTypes:[CROSS_REFERENCED_EVENT, ASSIGNED_EVENT], first:30) {
          nodes {
            __typename
            ... on CrossReferencedEvent { createdAt willCloseTarget source { __typename ... on PullRequest { number } } }
            ... on AssignedEvent { createdAt actor { __typename login }
                                   assignee { __typename ... on User { login } ... on Bot { login } } }
          }
        }
      }
    }
  }
}
"""


def fetch(full_name, out, since):
    key = full_name.replace("/", "__")
    path, done = f"{out}/issues/{key}.jsonl", f"{out}/issues/{key}.done"
    if os.path.exists(done):
        return full_name, "skipped", 0
    owner, name = full_name.split("/")
    cursor, n, status = None, 0, "ok"
    with open(path + ".tmp", "w") as f:
        while True:
            d = graphql({"owner": owner, "name": name, "cursor": cursor}, QUERY)
            if d is None:
                status = "not_found"
                break
            issues = d["repository"]["issues"]
            stop = False
            for it in issues["nodes"]:
                if it["createdAt"] < since:
                    stop = True
                    break
                f.write(json.dumps(it, separators=(",", ":")) + "\n")
                n += 1
            if stop or not issues["pageInfo"]["hasNextPage"]:
                break
            cursor = issues["pageInfo"]["endCursor"]
    os.replace(path + ".tmp", path)
    open(done, "w").write(status + "\n")
    return full_name, status, n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("repos_csv")
    ap.add_argument("out_dir")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--since", default="2025-01-01")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    os.makedirs(a.out_dir + "/issues", exist_ok=True)
    names = pd.read_csv(a.repos_csv).full_name.tolist()[: a.limit]
    print(f"{len(names)} repositories, {len(TOKENS)} tokens", flush=True)
    report_stats()
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(fetch, nm, a.out_dir, a.since): nm for nm in names}
        for fut in cf.as_completed(futs):
            try:
                print(*fut.result(), flush=True)
            except Exception as e:
                print(futs[fut], "FAILED", type(e).__name__, flush=True)
