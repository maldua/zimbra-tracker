#!/usr/bin/env python3
"""
track_refs.py
Snapshot generator for Zimbra Tracker using a tracking branch via git worktree.
Copyright (C) 2025 BTACTIC, S.C.C.L.

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software Foundation,
version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.
You should have received a copy of the GNU General Public License along with this program.
If not, see <http://www.gnu.org/licenses/>.

Features:
- Automatically creates or uses a worktree for the 'tracking' branch
- Clones or updates tracked repositories
- Exports commits for all branches and tags into per-repo directories
- Uses filesystem-safe percent-encoded filenames
- Generates refs-manifest.json for branch/tag reverse lookup
- Uses a temporary directory to clone repos to avoid committing full repos
 Exports commits for all branches and tags into per-repo directories in tracking branch
"""

import os
import subprocess
import sys
import json
import shutil
from datetime import datetime
from refname_utils import branch_file_path, tag_file_path, safe_refname_to_filename, filename_to_refname

# Paths
TRACKING_WORKTREE_DIR = "../zimbra-tracker-tracking"
REPO_LIST_FILE = "zimbra_tracked_repos.txt"
REPOS_DIR = os.path.join(TRACKING_WORKTREE_DIR, "repos")
TMP_REPOS_DIR = "tmp_repos"  # temporary clone location (ignored by git)

def run(cmd, cwd=None, capture=True):
    """Run a command and return stdout"""
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=capture)
    if result.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
        sys.exit(1)
    return result.stdout.strip() if capture else None

def ensure_tracking_worktree():
    """Create or reuse the tracking branch worktree"""
    if not os.path.exists(TRACKING_WORKTREE_DIR):
        print("Setting up tracking worktree...")
        # Check if tracking branch exists
        branches = run(["git", "branch", "--list", "tracking"]).splitlines()
        if not branches:
            # Create orphan tracking branch
            run(["git", "checkout", "--orphan", "tracking"])
            run(["git", "rm", "-rf", "."])
            run(["git", "commit", "--allow-empty", "-m", "Initial tracking branch"])
            run(["git", "checkout", "main"])
        # Add worktree
        run(["git", "worktree", "add", TRACKING_WORKTREE_DIR, "tracking"])
    else:
        print("Tracking worktree already exists, updating...")
        # Ensure it's up to date
        run(["git", "checkout", "tracking"], cwd=TRACKING_WORKTREE_DIR)
        run(["git", "pull"], cwd=TRACKING_WORKTREE_DIR, capture=False)

def read_tracked_repos():
    """Read the repo list file and return list of (repo_id, clone_url)"""
    repos = []
    with open(REPO_LIST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                print(f"Invalid line in {REPO_LIST_FILE}: {line}")
                continue
            repos.append((parts[0], parts[1]))
    return repos

def ensure_repo_cloned(repo_id, clone_url):
    """Clone the repo in temporary directory if not exists, else fetch updates"""
    os.makedirs(TMP_REPOS_DIR, exist_ok=True)
    path = os.path.join(TMP_REPOS_DIR, repo_id)
    if not os.path.exists(path):
        print(f"Cloning {repo_id}...")
        subprocess.run(["git", "clone", "--mirror", clone_url, path], check=True)
    else:
        print(f"Fetching updates for {repo_id}...")
        subprocess.run(["git", "fetch", "--all"], cwd=path, check=True)
    return path

def write_commit_list(filepath, commits):
    """Write commits (list of strings) to file"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        for line in commits:
            f.write(line + "\n")

def export_branch_commits(repo_path, repo_id, branch_name, manifest):
    """Export commits for a branch"""
    commit_lines = run(["git", "log", "--reverse", "--pretty=format:%H %s", branch_name], cwd=repo_path).splitlines()
    file_path = branch_file_path(os.path.join(REPOS_DIR, repo_id), branch_name)
    write_commit_list(file_path, commit_lines)
    manifest[branch_name] = safe_refname_to_filename(branch_name)
    print(f"Exported {len(commit_lines)} commits for branch {branch_name}")

def export_tag_commit(repo_path, repo_id, tag_name, manifest):
    """Export commits for a tag"""
    commit_line = run(["git", "log", "-1", "--pretty=format:%H %s", tag_name], cwd=repo_path)
    file_path = tag_file_path(os.path.join(REPOS_DIR, repo_id), tag_name)
    write_commit_list(file_path, [commit_line])
    manifest[tag_name] = safe_refname_to_filename(tag_name)
    print(f"Exported commit for tag {tag_name}")

def generate_manifest(manifest, repo_id):
    """Write refs-manifest.json for a repo"""
    path = os.path.join(REPOS_DIR, repo_id, "refs-manifest.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Generated refs-manifest.json for {repo_id}")

def has_changes():
    """Return True if there are untracked or modified files."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=TRACKING_WORKTREE_DIR,
        stdout=subprocess.PIPE,
        text=True
    )
    return bool(result.stdout.strip())

def main():
    ensure_tracking_worktree()
    os.makedirs(REPOS_DIR, exist_ok=True)
    repos = read_tracked_repos()

    for repo_id, clone_url in repos:
        print(f"\nProcessing repo: {repo_id}")
        repo_path = ensure_repo_cloned(repo_id, clone_url)
        manifest = {}

        # Branches
        branches = run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=repo_path).splitlines()
        for branch in branches:
            export_branch_commits(repo_path, repo_id, branch, manifest)

        # Tags
        tags = run(["git", "for-each-ref", "--format=%(refname:short)", "refs/tags"], cwd=repo_path).splitlines()
        for tag in tags:
            export_tag_commit(repo_path, repo_id, tag, manifest)

        # Write manifest for this repo
        generate_manifest(manifest, repo_id)

    # Commit snapshot to tracking branch
    os.chdir(TRACKING_WORKTREE_DIR)
    if has_changes():
        run(["git", "add", "."], capture=False)
        snapshot_msg = f"Snapshot {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}"
        run(["git", "commit", "-m", snapshot_msg], capture=False)
    else:
        print("No changes to commit")

    # Clean up temporary clones
    shutil.rmtree(TMP_REPOS_DIR, ignore_errors=True)

if __name__ == "__main__":
    main()
