#!/usr/bin/env python3
"""
generate_changes.py
Generate markdown summaries of repo changes and events based on the tracking branch.
Copyright (C) 2025 BTACTIC, S.C.C.L.

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software Foundation,
version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.
You should have received a copy of the GNU General Public License along with this program.
If not, see <http://www.gnu.org/licenses/>.
"""

import os
import yaml
from datetime import datetime
from subprocess import run, PIPE
from pathlib import Path

# --- Constants ---
TRACKING_WORKTREE_DIR = "../zimbra-tracker-tracking"
MARKDOWN_WORKTREE_DIR = "../zimbra-tracker-markdown-changes"
EVENTS_BRANCH = "events"
MARKDOWN_BRANCH = "markdown_changes"
EVENTS_DIR = os.path.join(TRACKING_WORKTREE_DIR, EVENTS_BRANCH)

# --- Helpers ---
def run_cmd(cmd, cwd=None):
    """Run shell command and return stdout as string."""
    result = run(cmd, cwd=cwd, stdout=PIPE, stderr=PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()

def ensure_markdown_worktree():
    """Ensure the markdown worktree and branch exist."""
    if not os.path.exists(MARKDOWN_WORKTREE_DIR):
        print("📦 Setting up markdown_changes worktree...")
        # Save current branch name
        current_branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if current_branch == "HEAD":
            current_branch = None  # detached or empty repo

        # Check if branch exists
        branches = run_cmd(["git", "branch", "--list", MARKDOWN_BRANCH])
        if not branches:
            # Create orphan branch
            run_cmd(["git", "checkout", "--orphan", MARKDOWN_BRANCH])
            run_cmd(["git", "rm", "-rf", "."])
            run_cmd(["git", "commit", "--allow-empty", "-m", "Initial markdown_changes branch"])
        # Switch back to previous branch if available
        if current_branch:
            run_cmd(["git", "checkout", current_branch])
        else:
            print("⚠️ Not on a branch before creating markdown_changes; staying detached.")
        # Add worktree
        run_cmd(["git", "worktree", "add", MARKDOWN_WORKTREE_DIR, MARKDOWN_BRANCH])
    else:
        print("✅ Markdown worktree already exists, updating...")
        # Ensure it's on the correct branch
        run_cmd(["git", "checkout", MARKDOWN_BRANCH], cwd=MARKDOWN_WORKTREE_DIR)

def ensure_repo_and_branch(repo_dir, branch_name):
    """Ensure the repo dir exists and checkout/create orphan branch (markdown repo only)."""
    os.makedirs(repo_dir, exist_ok=True)
    if not os.path.exists(os.path.join(repo_dir, ".git")):
        raise RuntimeError(f"{repo_dir} is not a git repository.")

    current_branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir)

    # Check if branch exists
    branches = run_cmd(["git", "branch", "--list", branch_name], cwd=repo_dir)
    if not branches:
        run_cmd(["git", "checkout", "--orphan", branch_name], cwd=repo_dir)
        run_cmd(["git", "rm", "-rf", "."], cwd=repo_dir)
    else:
        run_cmd(["git", "checkout", branch_name], cwd=repo_dir)

    return current_branch  # So we can restore it later

def restore_branch(repo_dir, branch_name):
    """Restore previously active branch."""
    run_cmd(["git", "checkout", branch_name], cwd=repo_dir)

def load_events():
    """Load events YAML files from events branch directory."""
    events = []
    if not os.path.isdir(EVENTS_DIR):
        print(f"⚠️ No events directory found at {EVENTS_DIR}")
        return events

    for file in Path(EVENTS_DIR).glob("*.yaml"):
        with open(file, "r") as f:
            data = yaml.safe_load(f)
            if data:
                events.append(data)
    # Sort by date descending (newest first)
    events.sort(key=lambda e: e["date"], reverse=True)
    return events

def read_tracking_commits():
    """Read commit snapshots from tracking repo (no branch switching)."""
    tracking_commits = run_cmd(
        ["git", "log", "--reverse", "--pretty=format:%H"], cwd=TRACKING_WORKTREE_DIR
    ).splitlines()
    return tracking_commits

def read_tracking_file(snapshot_hash, rel_path):
    """Read file from a specific commit snapshot."""
    try:
        return run_cmd(["git", "show", f"{snapshot_hash}:{rel_path}"], cwd=TRACKING_WORKTREE_DIR)
    except RuntimeError:
        return ""

def summarize_repo_section(title, items, limit=5):
    """Generate markdown section for a list of repo items (tags/branches)."""
    md = f"### {title}\n\n"
    for name, commits in items.items():
        md += f"#### {name}\n"
        for commit in commits[:limit]:
            md += f"- {commit}\n"
        md += "\n"
    return md

# --- Main logic ---
def main():
    print("🔍 Generating Markdown changes timeline...")

    # Ensure markdown worktree and branch exist first
    ensure_markdown_worktree()

    # Only the markdown repo branch should be checked out
    prev_branch = ensure_repo_and_branch(MARKDOWN_WORKTREE_DIR, MARKDOWN_BRANCH)

    # Load events from the tracking repo (static folder)
    events = load_events()

    # Read tracking repo commits directly
    tracking_commits = read_tracking_commits()

    markdown_output = "# Zimbra Tracker – Changes Timeline\n\n"

    # Add events
    markdown_output += "## Events\n\n"
    for ev in events:
        markdown_output += f"### {ev['title']} ({ev['date']})\n\n{ev['description']}\n\n"

    # Traverse tracking commits newest to oldest
    for commit_hash in reversed(tracking_commits):
        commit_time = run_cmd(["git", "show", "-s", "--format=%ci", commit_hash], cwd=TRACKING_WORKTREE_DIR)
        markdown_output += f"## Snapshot {commit_time}\n\n"

        # Global tags
        global_tags_yaml = read_tracking_file(commit_hash, "all_tags.yaml")
        if global_tags_yaml:
            tags = yaml.safe_load(global_tags_yaml)
            markdown_output += summarize_repo_section("Global Tags", {t: [] for t in tags})

        # Repo-specific tags
        repo_tags_yaml = read_tracking_file(commit_hash, "repo_tags.yaml")
        if repo_tags_yaml:
            repo_tags = yaml.safe_load(repo_tags_yaml)
            markdown_output += summarize_repo_section("Repo Tags", repo_tags)

        # Repo-specific branches
        repo_branches_yaml = read_tracking_file(commit_hash, "repo_branches.yaml")
        if repo_branches_yaml:
            repo_branches = yaml.safe_load(repo_branches_yaml)
            markdown_output += summarize_repo_section("Repo Branches", repo_branches)

    # Write markdown file
    output_file = os.path.join(MARKDOWN_WORKTREE_DIR, "changes_timeline.md")
    with open(output_file, "w") as f:
        f.write(markdown_output)

    # Commit result in markdown repo
    run_cmd(["git", "add", "changes_timeline.md"], cwd=MARKDOWN_WORKTREE_DIR)
    run_cmd(["git", "commit", "-m", f"Update markdown changes ({datetime.now().isoformat()})"], cwd=MARKDOWN_WORKTREE_DIR)

    # Restore previous branch
    restore_branch(MARKDOWN_WORKTREE_DIR, prev_branch)

    print("✅ Markdown changes generated and committed successfully.")

if __name__ == "__main__":
    main()
