"""Bare-clone the sampled repositories and fetch the head of every pull request (refs/pr/N).

Usage: python clone_repos.py REPOS_CSV OUT_DIR [--limit N] [--max-mb 500] [--workers 4]
Needs OUT_DIR/repos/OWNER__NAME.json from fetch_prs.py (for the size). Clones go to OUT_DIR/git/OWNER__NAME.git.
Public anonymous clone, no token. A repository with a file OUT_DIR/git/OWNER__NAME.done is skipped.
"""
import argparse
import concurrent.futures as cf
import json
import os
import subprocess

import pandas as pd

ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", SSL_CERT_FILE="/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem")
ENV.pop("SSL_CERT_DIR", None)


def git(args, cwd=None, timeout=3600):
    return subprocess.run(["git"] + args, cwd=cwd, env=ENV, capture_output=True, text=True, timeout=timeout)


def clone(full_name, out, max_mb):
    key = full_name.replace("/", "__")
    meta_path, dest, done = f"{out}/repos/{key}.json", f"{out}/git/{key}.git", f"{out}/git/{key}.done"
    if os.path.exists(done):
        return full_name, "skipped"
    if not os.path.exists(meta_path):
        return full_name, "no metadata"
    meta = json.load(open(meta_path))
    if meta.get("status") != "ok":
        return full_name, "not found"
    if meta["diskUsage"] / 1024 > max_mb:
        return full_name, f"too large ({meta['diskUsage'] / 1024:.0f} MB)"
    url = f"https://github.com/{full_name}.git"
    if not os.path.exists(dest):
        r = git(["clone", "--bare", "--quiet", url, dest])
        if r.returncode:
            return full_name, "clone failed: " + r.stderr.strip()[-200:]
    r = git(["fetch", "--quiet", "--no-tags", url, "+refs/pull/*/head:refs/pr/*"], cwd=dest)
    if r.returncode:
        return full_name, "fetch failed: " + r.stderr.strip()[-200:]
    open(done, "w").write("ok\n")
    return full_name, "ok"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("repos_csv")
    ap.add_argument("out_dir")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--max-mb", type=float, default=500)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    os.makedirs(a.out_dir + "/git", exist_ok=True)
    names = pd.read_csv(a.repos_csv).full_name.tolist()[: a.limit]
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for res in ex.map(lambda nm: clone(nm, a.out_dir, a.max_mb), names):
            print(*res, flush=True)
