"""Merge replay for pairs of pull requests, after run_replay.py of Xu, Subramanian and Karthik (arXiv 2607.04697).

Usage: python replay_pairs.py PAIRS_CSV OUT_CSV [--workers 8] [--limit N]
For each repository: fetch the head of every pull request named in its pairs (shallow, depth 80; depth 600 if a pair
has no merge base), then for each pair run a three-way `git merge-tree --write-tree` of the two heads. Labels, as in
the original: CLEAN, CONFLICT (with the conflicted files and git's conflict types), UNAVAIL_fetch (a head could not
be fetched), UNAVAIL_nobase (no common ancestor). Nothing is checked out and no repository code is run.
Resumable: pairs already in OUT_CSV are skipped. One fetch per repository, so several pairs per repository are cheap.
"""
import argparse
import csv
import os
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("pairs")
ap.add_argument("out")
ap.add_argument("--workers", type=int, default=8)
ap.add_argument("--limit", type=int, default=0, help="only the first N repositories (smoke test)")
args = ap.parse_args()
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0")
HEADER = ["repo", "prA", "prB", "label", "n_files", "files", "types"]
lock = threading.Lock()


def git(cmd, cwd, timeout):
    try:
        return subprocess.run(["git"] + cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=timeout, env=ENV)
    except Exception:
        return None


def parse_conflict(stdout):
    lines = stdout.split("\n")
    files, types = set(), []
    for ln in lines[1:]:
        if ln == "":
            break
        if "\t" in ln:
            files.add(ln.split("\t", 1)[1])
    for ln in lines:
        if ln.startswith("CONFLICT ("):
            types.append(ln[10:].split(")", 1)[0])
    return files, types


def fetch(d, numbers, depth, timeout):
    """Fetch pull request heads one group at a time; return the set that arrived."""
    refs = [f"refs/pull/{n}/head:refs/pr/{n}" for n in numbers]
    r = git(["-c", "protocol.version=2", "fetch", "-q", "--no-tags", "--depth", str(depth), "origin"] + refs, d, timeout)
    if r is not None and r.returncode == 0:
        return set(numbers)
    got = set()
    for n in numbers:  # a deleted head fails the whole fetch, so retry one by one
        r = git(["-c", "protocol.version=2", "fetch", "-q", "--no-tags", "--depth", str(depth), "origin",
                 f"refs/pull/{n}/head:refs/pr/{n}"], d, 120)
        if r is not None and r.returncode == 0:
            got.add(n)
    return got


def do_repo(repo, pairs):
    d = tempfile.mkdtemp(prefix="replay_", dir=os.environ.get("REPLAY_TMP"))
    rows = []
    try:
        git(["init", "-q"], d, 20)
        git(["remote", "add", "origin", f"https://github.com/{repo}.git"], d, 20)
        numbers = sorted({n for a, b in pairs for n in (a, b)})
        got = fetch(d, numbers, 80, 60 + 20 * len(numbers))
        deep = False
        for a, b in pairs:
            if a not in got or b not in got:
                rows.append([repo, a, b, "UNAVAIL_fetch", 0, "", ""])
                continue
            mb = git(["merge-base", f"refs/pr/{a}", f"refs/pr/{b}"], d, 30)
            if (mb is None or not mb.stdout.strip()) and not deep:
                fetch(d, sorted(got), 600, 120 + 40 * len(got))
                deep = True
                mb = git(["merge-base", f"refs/pr/{a}", f"refs/pr/{b}"], d, 30)
            if mb is None or not mb.stdout.strip():
                rows.append([repo, a, b, "UNAVAIL_nobase", 0, "", ""])
                continue
            mt = git(["merge-tree", "--write-tree", f"refs/pr/{a}", f"refs/pr/{b}"], d, 120)
            if mt is None:
                rows.append([repo, a, b, "UNAVAIL_timeout", 0, "", ""])
            elif mt.returncode == 0:
                rows.append([repo, a, b, "CLEAN", 0, "", ""])
            elif mt.returncode == 1:
                files, types = parse_conflict(mt.stdout)
                rows.append([repo, a, b, "CONFLICT", len(files), "|".join(sorted(files)), "|".join(types)])
            else:
                rows.append([repo, a, b, f"ERR{mt.returncode}", 0, "", ""])
    finally:
        shutil.rmtree(d, ignore_errors=True)
    with lock:
        with open(args.out, "a", newline="") as f:
            csv.writer(f).writerows(rows)
    return len(rows)


p = pd.read_csv(args.pairs)[["repo", "prA", "prB"]].drop_duplicates()
if not os.path.exists(args.out):
    with open(args.out, "w", newline="") as f:
        csv.writer(f).writerow(HEADER)
done = pd.read_csv(args.out)
done = set(zip(done.repo, done.prA, done.prB))
todo = {}
for r, a, b in zip(p.repo, p.prA, p.prB):
    if (r, a, b) not in done:
        todo.setdefault(r, []).append((int(a), int(b)))
repos = sorted(todo)[: args.limit] if args.limit else sorted(todo)
print(f"pairs to do: {sum(len(todo[r]) for r in repos)} in {len(repos)} repositories (already done: {len(done)})", flush=True)
with ThreadPoolExecutor(args.workers) as ex:
    n = 0
    for i, k in enumerate(ex.map(lambda r: do_repo(r, todo[r]), repos)):
        n += k
        if (i + 1) % 25 == 0:
            print(f"  {i + 1} repositories, {n} pairs", flush=True)
print("done:", n, flush=True)
