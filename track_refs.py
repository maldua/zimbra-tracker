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
- Generates per-repo branch/tag manifests + global all-tags.json
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
from refname_utils import run_throttled_git_cmd
import time

# Paths
TRACKING_WORKTREE_DIR = "../zimbra-tracker-tracking"
REPO_LIST_FILE = "tracked_repos.list"
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
    """Create or reuse the tracking branch worktree."""
    # Save current branch name (if any)
    current_branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if current_branch == "HEAD":
        current_branch = None  # detached HEAD or no branch checked out

    if not os.path.exists(TRACKING_WORKTREE_DIR):
        print("Setting up tracking worktree...")
        # Check if tracking branch exists
        branches = run(["git", "branch", "--list", "tracking"]).splitlines()
        if not branches:
            # Create orphan tracking branch
            run(["git", "checkout", "--orphan", "tracking"])
            run(["git", "rm", "-rf", "."])
            run(["git", "commit", "--allow-empty", "-m", "Initial tracking branch"])
        # Switch back to previous branch if available
        if current_branch:
            run(["git", "checkout", current_branch])
        else:
            # Fallback to default branch if we were detached
            print("Warning: not on a branch before creating tracking; staying detached.")
        # Add worktree
        run(["git", "worktree", "add", TRACKING_WORKTREE_DIR, "tracking"])
    else:
        print("Tracking worktree already exists, updating...")
        # Ensure it's up to date
        run(["git", "checkout", "tracking"], cwd=TRACKING_WORKTREE_DIR)
        run_throttled_git_cmd(["git", "pull"], cwd=TRACKING_WORKTREE_DIR, capture=False)

def read_tracked_repos():
    """Read the repo list file and return list of (repo_id, clone_url, platform)"""
    repos = []
    with open(REPO_LIST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                print(f"Invalid line in {REPO_LIST_FILE}: {line}")
                continue
            repo_id = parts[0]
            clone_url = parts[1]
            platform = parts[2] if len(parts) >= 3 else None
            repos.append((repo_id, clone_url, platform))
    return repos

def ensure_repo_cloned(repo_id, clone_url):
    """Clone the repo in temporary directory if not exists, else fetch updates"""
    os.makedirs(TMP_REPOS_DIR, exist_ok=True)
    path = os.path.join(TMP_REPOS_DIR, repo_id)
    if not os.path.exists(path):
        print(f"Cloning {repo_id}...")
        run_throttled_git_cmd(["git", "clone", "--mirror", clone_url, path], check=True)
    else:
        print(f"Fetching updates for {repo_id}...")
        run_throttled_git_cmd(["git", "fetch", "--all"], cwd=path, check=True)
    return path

def export_ref_commits(repo_path, ref_name, file_path, manifest):
    """
    Export all commits reachable from a given ref (branch or tag),
    write them as one JSON object per line, and update the manifest.
    Each JSON object contains: commit, timestamp, author, committer, message.
    """
    sep = "\x1f"  # Unit Separator (rarely appears in commit messages)
    #   %H  - commit hash (full 40-character SHA1)
    #   %ct - commit timestamp (UNIX epoch time)
    #   %an - author name
    #   %cn - committer name
    #   %s  - commit subject (the commit message's first line)
    git_format = f"%H{sep}%ct{sep}%an{sep}%cn{sep}%s"

    commit_lines = run(
        ["git", "log", "--reverse", f"--pretty=format:{git_format}", ref_name],
        cwd=repo_path
    ).splitlines()

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        for line in commit_lines:
            parts = line.split(sep, 4)
            if len(parts) < 5:
                continue  # skip malformed lines
            commit_hash, timestamp, author, committer, message = parts
            author = author if author else "Unknown"
            committer = committer if committer else "Unknown"

            commit_json = {
                "commit": commit_hash,
                "timestamp": int(timestamp),
                "author": author,
                "committer": committer,
                "message": message
            }
            f.write(json.dumps(commit_json, ensure_ascii=False) + "\n")

    if commit_lines:
        latest_commit = commit_lines[-1].split()[0]  # last commit hash in log
    else:
        latest_commit = None
    manifest[ref_name] = {
        "file": safe_refname_to_filename(ref_name),
        "latest_commit": latest_commit
    }
    print(f"Exported {len(commit_lines)} commits for {ref_name}")

def export_branch_commits(repo_path, repo_id, branch_name, manifest):
    """Export commits for a branch"""
    file_path = branch_file_path(os.path.join(REPOS_DIR, repo_id), branch_name)
    export_ref_commits(repo_path, branch_name, file_path, manifest)

def export_tag_commits(repo_path, repo_id, tag_name, manifest, all_tags):
    """Export commits for a tag and update global tag list"""
    file_path = tag_file_path(os.path.join(REPOS_DIR, repo_id), tag_name)
    export_ref_commits(repo_path, tag_name, file_path, manifest)

    # Update global tag dictionary
    if tag_name not in all_tags:
        all_tags[tag_name] = set()
    all_tags[tag_name].add(repo_id)

def generate_manifest(manifest, repo_id, filename):
    """Write manifest JSON for a repo"""
    path = os.path.join(REPOS_DIR, repo_id, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(f"Generated {filename} for {repo_id}")

def write_all_tags_manifest(all_tags):
    # Save all-tags.txt (just tag names, sorted)
    all_tags_txt_path = os.path.join(TRACKING_WORKTREE_DIR, "all-tags.txt")
    with open(all_tags_txt_path, "w", encoding="utf-8") as f:
        for tag_name in sorted(all_tags.keys()):
            f.write(tag_name + "\n")

    # Save all-tags.json (tag names with associated repos)
    all_tags_json_path = os.path.join(TRACKING_WORKTREE_DIR, "all-tags.json")
    # convert sets to lists for JSON serialization
    json_serializable = {tag: list(repos) for tag, repos in all_tags.items()}
    with open(all_tags_json_path, "w", encoding="utf-8") as f:
        json.dump(json_serializable, f, indent=2, sort_keys=True)

def write_all_repos_manifest(repos):
    """Save list of all tracked repo_ids into all-repos.json"""
    all_projects_path = os.path.join(TRACKING_WORKTREE_DIR, "all-repos.json")
    repo_ids = [repo_id for repo_id, _, _ in repos]
    with open(all_projects_path, "w", encoding="utf-8") as f:
        json.dump(sorted(repo_ids), f, indent=2)
    print(f"Generated all-repos.json with {len(repo_ids)} repos")

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
    all_tags = {}  # { "tag_name": set_of_repo_ids }

    for repo_id, clone_url, platform in repos:
        print(f"\nProcessing repo: {repo_id}")
        repo_path = ensure_repo_cloned(repo_id, clone_url)

        # Separate manifests for branches and tags
        branches_manifest = {}
        tags_manifest = {}

        # Branches
        branches = run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=repo_path).splitlines()
        for branch in branches:
            export_branch_commits(repo_path, repo_id, branch, branches_manifest)

        # Tags
        tags = run(["git", "for-each-ref", "--format=%(refname:short)", "refs/tags"], cwd=repo_path).splitlines()
        for tag in tags:
            export_tag_commits(repo_path, repo_id, tag, tags_manifest, all_tags)

        # Write manifests separately
        generate_manifest(branches_manifest, repo_id, "branches-manifest.json")
        generate_manifest(tags_manifest, repo_id, "tags-manifest.json")

    # Write all tracked repo IDs
    write_all_repos_manifest(repos)

    # Write global tags manifest
    write_all_tags_manifest(all_tags)

    # Commit snapshot to tracking branch
    os.chdir(TRACKING_WORKTREE_DIR)
    if has_changes():
        run(["git", "add", "."], capture=False)
        snapshot_msg = f"Snapshot {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}"
        run(["git", "commit", "-m", snapshot_msg], capture=False)
    else:
        print("No changes to commit")

    # Clean up temporary clones only if requested.
    # Keep TMP_REPOS_DIR around for generate_changes.py to use for snapshot creation.
    KEEP_TMP_REPOS = os.environ.get("ZTR_KEEP_TMP_REPOS", "1")  # default: keep
    if KEEP_TMP_REPOS in ("0", "false", "False"):
        shutil.rmtree(TMP_REPOS_DIR, ignore_errors=True)
    else:
        print(f"Keeping temporary clones in {TMP_REPOS_DIR} for snapshotting.")

if __name__ == "__main__":
    main()
