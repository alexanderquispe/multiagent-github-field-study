"""From each bare clone: who deleted whose lines on the default branch, and which commits were reverted.

Usage: python git_line_edges.py REPOS_CSV DATA_DIR [--limit N] [--workers 8] [--window-days 45] [--only OWNER/NAME]
For every commit C on the first-parent history of the default branch (since 2024-12-01) we take the lines C deletes
(git diff -U0 against its first parent) and ask git blame --first-parent, limited to the previous WINDOW days, which
earlier first-parent commit had written each of them. A first-parent commit is a merged pull request in repositories
that merge or squash. Output in DATA_DIR/lines/: OWNER__NAME.commits.csv (one row per commit), .edges.csv
(deleter, origin, lines), .reverts.csv (reverter, reverted), and a marker .done.
Not counted: generated and lock files, binary files, commits that touch more than 100 files or 20,000 lines.
"""
import argparse
import bisect
import collections
import concurrent.futures as cf
import csv
import json
import os
import re
import subprocess

import pandas as pd

SKIP = re.compile(r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|Cargo\.lock|poetry\.lock|uv\.lock|go\.sum|"
                  r"composer\.lock|Gemfile\.lock|bun\.lockb?|npm-shrinkwrap\.json)$|\.min\.(js|css)$|\.map$|\.snap$|"
                  r"(^|/)(dist|build|vendor|node_modules|third_party|__snapshots__)/|\.(svg|ipynb|csv|tsv|lock)$")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
HEAD = re.compile(r"^([0-9a-f]{40}) \d+ \d+(?: \d+)?$")
MAX_FILES, MAX_LINES = 100, 20000


def git(repo, args, timeout=600):
    r = subprocess.run(["git", "-c", "core.quotepath=off"] + args, cwd=repo, capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode("utf-8", "replace")


def diff_files(repo, parent, oid):
    """Per old path: list of (start, count) deleted ranges, and added line count. Skips excluded and binary files."""
    code, text = git(repo, ["diff", "-U0", "--no-color", "-M", "--no-ext-diff", parent, oid])
    files, old, new = [], None, None
    if code:
        return files
    cur = None
    for line in text.split("\n"):
        if line.startswith("diff --git "):
            cur, old, new = None, None, None
        elif line.startswith("--- "):
            old = None if line[4:] == "/dev/null" else line[6:] if line[4:6] == "a/" else "?"
        elif line.startswith("+++ "):
            new = None if line[4:] == "/dev/null" else line[6:] if line[4:6] == "b/" else "?"
            path = old or new
            if path == "?" or old == "?" or SKIP.search(path or ""):
                cur = None
            else:
                cur = {"old": old, "new": new, "del": [], "added": 0}
                files.append(cur)
        elif cur is not None and line.startswith("@@"):
            m = HUNK.match(line)
            if m:
                dn = int(m.group(2) or 1)
                an = int(m.group(4) or 1)
                if dn:
                    cur["del"].append((int(m.group(1)), dn))
                cur["added"] += an
    return files


def blame_counts(repo, parent, bound, path, ranges):
    args = ["blame", "--first-parent", "--porcelain"]
    for s, n in ranges:
        args += ["-L", f"{s},{s + n - 1}"]
    args += [parent] + (["^" + bound] if bound else []) + ["--", path]
    code, text = git(repo, args)
    counts, boundary, last = collections.Counter(), set(), None
    if code:
        return counts
    for line in text.split("\n"):
        if line.startswith("\t"):
            continue
        m = HEAD.match(line)
        if m:
            last = m.group(1)
            counts[last] += 1
        elif line == "boundary" and last:
            boundary.add(last)
    for b in boundary:
        counts.pop(b, None)
    return counts


def process(full_name, data, window):
    key = full_name.replace("/", "__")
    repo, out = f"{data}/git/{key}.git", f"{data}/lines/{key}"
    if os.path.exists(out + ".done"):
        return full_name, "skipped", 0, 0
    if not os.path.exists(f"{data}/git/{key}.done"):
        return full_name, "no clone", 0, 0
    branch = (json.load(open(f"{data}/repos/{key}.json")).get("defaultBranchRef") or {}).get("name")
    if not branch:
        return full_name, "no default branch", 0, 0
    code, text = git(repo, ["log", "--first-parent", "--since=2024-12-01", "--format=%H%x00%P%x00%ct%x00%ae%x00%s",
                            f"refs/heads/{branch}"])
    if code:
        return full_name, "log failed", 0, 0
    commits = [ln.split("\x00") for ln in text.split("\n") if ln]
    commits.reverse()  # oldest first
    times = [int(c[2]) for c in commits]
    n_edges = 0
    with open(out + ".commits.csv.tmp", "w", newline="") as fc, open(out + ".edges.csv.tmp", "w", newline="") as fe:
        wc, we = csv.writer(fc), csv.writer(fe)
        wc.writerow(["oid", "parent", "time", "email", "subject", "n_files", "added", "deleted", "blamed"])
        we.writerow(["deleter", "origin", "lines", "files", "whole_file_lines"])
        for i, (oid, parents, ct, email, subject) in enumerate(commits):
            parent = parents.split(" ")[0] if parents else ""
            if not parent:
                wc.writerow([oid, "", ct, email, subject[:200], 0, 0, 0, 0])
                continue
            files = diff_files(repo, parent, oid)
            added = sum(f["added"] for f in files)
            deleted = sum(n for f in files for _, n in f["del"])
            ok = len(files) <= MAX_FILES and added + deleted <= MAX_LINES
            if ok and deleted:
                j = bisect.bisect_left(times, int(ct) - window * 86400, 0, i) - 1
                bound = commits[j][0] if j >= 0 else None
                tot, nfiles, whole = collections.Counter(), collections.Counter(), collections.Counter()
                for f in files:
                    if not f["del"] or not f["old"]:
                        continue
                    c = blame_counts(repo, parent, bound, f["old"], f["del"])
                    for o, n in c.items():
                        tot[o] += n
                        nfiles[o] += 1
                        if f["new"] is None:
                            whole[o] += n
                for o, n in tot.items():
                    we.writerow([oid, o, n, nfiles[o], whole[o]])
                    n_edges += 1
            wc.writerow([oid, parent, ct, email, subject[:200], len(files), added, deleted, int(ok)])
    # reverts anywhere on the default branch
    code, text = git(repo, ["log", "--since=2024-12-01", "--grep=This reverts commit", "--format=%x01%H%x00%ct%x00%B",
                            f"refs/heads/{branch}"])
    with open(out + ".reverts.csv.tmp", "w", newline="") as fr:
        wr = csv.writer(fr)
        wr.writerow(["reverter", "time", "reverted"])
        for block in text.split("\x01")[1:]:
            oid, ct, body = block.split("\x00", 2)
            for m in re.finditer(r"This reverts commit ([0-9a-f]{7,40})", body):
                wr.writerow([oid, ct, m.group(1)])
    for ext in ("commits", "edges", "reverts"):
        os.replace(f"{out}.{ext}.csv.tmp", f"{out}.{ext}.csv")
    open(out + ".done", "w").write("ok\n")
    return full_name, "ok", len(commits), n_edges


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("repos_csv")
    ap.add_argument("data_dir")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--window-days", type=int, default=45)
    ap.add_argument("--only")
    a = ap.parse_args()
    os.makedirs(a.data_dir + "/lines", exist_ok=True)
    names = [a.only] if a.only else pd.read_csv(a.repos_csv).full_name.tolist()[: a.limit]
    with cf.ProcessPoolExecutor(a.workers) as ex:
        futs = {ex.submit(process, nm, a.data_dir, a.window_days): nm for nm in names}
        for fut in cf.as_completed(futs):
            try:
                print(*fut.result(), flush=True)
            except Exception as e:
                print(futs[fut], "FAILED", type(e).__name__, str(e)[:150], flush=True)
