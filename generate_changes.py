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
import subprocess
import json

# --- Constants ---
TRACKING_WORKTREE_DIR = "../zimbra-tracker-tracking"
EVENTS_WORKTREE_DIR = "../zimbra-tracker-events"
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
    if not os.path.exists(".git"):
        raise RuntimeError("This script must be run inside the main zimbra-tracker repository.")

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
        # Directory exists — check if it's a valid git repo
        git_path = os.path.join(MARKDOWN_WORKTREE_DIR, ".git")
        if not os.path.exists(git_path):
            print("⚠️ Markdown directory exists but isn’t a git worktree — recreating...")
            run_cmd(["rm", "-rf", MARKDOWN_WORKTREE_DIR])
            run_cmd(["git", "worktree", "add", MARKDOWN_WORKTREE_DIR, MARKDOWN_BRANCH])
        else:
            print("✅ Markdown worktree already exists, updating...")
            # Ensure it's on the correct branch
            run_cmd(["git", "checkout", MARKDOWN_BRANCH], cwd=MARKDOWN_WORKTREE_DIR)

def ensure_events_branch_exists():
    """Ensure the 'events' branch exists locally; if not, try to fetch from origin."""
    branches = run_cmd(["git", "branch", "--list", EVENTS_BRANCH])
    if not branches:
        print(f"⚠️ Branch '{EVENTS_BRANCH}' not found locally. Trying to fetch from origin...")
        try:
            run_cmd(["git", "fetch", "origin", f"{EVENTS_BRANCH}:{EVENTS_BRANCH}"])
        except RuntimeError:
            raise RuntimeError(
                f"Could not find or fetch '{EVENTS_BRANCH}' branch. Aborting."
            )

def ensure_events_worktree():
    """Ensure the events worktree exists."""
    if not os.path.exists(EVENTS_WORKTREE_DIR):
        print("📦 Setting up events worktree...")
        run_cmd(["git", "worktree", "add", EVENTS_WORKTREE_DIR, EVENTS_BRANCH])
    else:
        git_path = os.path.join(EVENTS_WORKTREE_DIR, ".git")
        if not os.path.exists(git_path):
            print("⚠️ Events directory exists but isn’t a git worktree — recreating...")
            run_cmd(["rm", "-rf", EVENTS_WORKTREE_DIR])
            run_cmd(["git", "worktree", "add", EVENTS_WORKTREE_DIR, EVENTS_BRANCH])
        else:
            print("✅ Events worktree already exists, updating...")
            run_cmd(["git", "checkout", EVENTS_BRANCH], cwd=EVENTS_WORKTREE_DIR)
            run_cmd(["git", "pull"], cwd=EVENTS_WORKTREE_DIR)

def load_events():
    """Load events YAML files from the events worktree."""
    events_dir = os.path.join(EVENTS_WORKTREE_DIR, "events")
    events = []
    if not os.path.isdir(events_dir):
        print(f"⚠️ No events directory found at {events_dir}")
        return events

    for file in Path(events_dir).glob("*.yaml"):
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

def has_changes(repo_dir):
    """Return True if there are untracked or modified files in the given repo/worktree."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return bool(result.stdout.strip())

# --- Main logic ---
def main():
    print("🔍 Generating Markdown changes timeline...")

    ensure_events_branch_exists()
    ensure_events_worktree()

    # Ensure markdown worktree and branch exist first
    ensure_markdown_worktree()

    # Load events from the tracking repo (static folder)
    events = load_events()

    # Read tracking repo commits directly (oldest → newest)
    tracking_commits = read_tracking_commits()

    markdown_output = "# Zimbra Tracker – Changes Timeline\n\n"

    # Add events
    markdown_output += "## Events\n\n"
    for ev in events:
        markdown_output += f"### {ev['title']} ({ev['date']})\n\n{ev['description']}\n\n"

    # Traverse commits **newest to oldest** to produce snapshots
    for commit_hash in reversed(tracking_commits):

        # Get parent commits
        parents_line = run_cmd(
            ["git", "rev-list", "--parents", "-n", "1", commit_hash],
            cwd=TRACKING_WORKTREE_DIR
        ).split()
        commit_parents = parents_line[1:]  # skip the commit itself

        # Handle the "very first commit" (no parents at all)
        if not commit_parents:
            commit_time = run_cmd(
                ["git", "show", "-s", "--format=%ci", commit_hash],
                cwd=TRACKING_WORKTREE_DIR
            ).strip()
            markdown_output += f"## Very first commit ({commit_time})\n\nIgnored on purpose.\n\n"
            continue

        # Handle the case where parent’s parent does not exist (branch root)
        parent_hash = commit_parents[0]
        parent_parents_line = run_cmd(
            ["git", "rev-list", "--parents", "-n", "1", parent_hash],
            cwd=TRACKING_WORKTREE_DIR
        ).split()
        parent_parents = parent_parents_line[1:] if len(parent_parents_line) > 1 else []

        if not parent_parents:
            commit_time = run_cmd(
                ["git", "show", "-s", "--format=%ci", commit_hash],
                cwd=TRACKING_WORKTREE_DIR
            ).strip()
            markdown_output += f"## (First) Snapshot {commit_time}\n\nIgnored on purpose.\n\n"
            continue

        # Load current and parent snapshots
        current_snapshot = {
            "global_tags": yaml.safe_load(read_tracking_file(commit_hash, "all-tags.yaml") or "[]"),
            "repo_tags": yaml.safe_load(read_tracking_file(commit_hash, "repo_tags.yaml") or "{}"),
            "repo_branches": yaml.safe_load(read_tracking_file(commit_hash, "repo_branches.yaml") or "{}"),
        }

        parent_snapshot = {
            "global_tags": yaml.safe_load(read_tracking_file(parent_hash, "all-tags.yaml") or "[]"),
            "repo_tags": yaml.safe_load(read_tracking_file(parent_hash, "repo_tags.yaml") or "{}"),
            "repo_branches": yaml.safe_load(read_tracking_file(parent_hash, "repo_branches.yaml") or "{}"),
        }

        # --- Repository detection (based on all-repos.json) ---
        current_repos_raw = read_tracking_file(commit_hash, "all-repos.json")
        parent_repos_raw = read_tracking_file(parent_hash, "all-repos.json")

        try:
            current_repos = json.loads(current_repos_raw) if current_repos_raw else []
        except json.JSONDecodeError:
            current_repos = []
        try:
            parent_repos = json.loads(parent_repos_raw) if parent_repos_raw else []
        except json.JSONDecodeError:
            parent_repos = []

        new_repos = sorted(set(current_repos) - set(parent_repos))
        removed_repos = sorted(set(parent_repos) - set(current_repos))

        if new_repos or removed_repos:
            markdown_output += "### 🧭 Repository Changes\n\n"

            if new_repos:
                markdown_output += "#### 🆕 New Repositories Detected\n\n"
                for repo_id in new_repos:
                    markdown_output += (
                        f"- **{repo_id}** — Branches and Tags changes will only be shown in future snapshots.\n"
                    )
                markdown_output += "\n"

            if removed_repos:
                markdown_output += "#### 🗑️ Repositories Removed\n\n"
                for repo_id in removed_repos:
                    markdown_output += f"- **{repo_id}**\n"
                markdown_output += "\n"

        # --- Global tags changes (based on all-tags.txt) ---
        current_tags_raw = read_tracking_file(commit_hash, "all-tags.txt")
        parent_tags_raw = read_tracking_file(parent_hash, "all-tags.txt")

        current_tags = [t.strip() for t in current_tags_raw.splitlines() if t.strip()] if current_tags_raw else []
        parent_tags = [t.strip() for t in parent_tags_raw.splitlines() if t.strip()] if parent_tags_raw else []

        new_global_tags = sorted(set(current_tags) - set(parent_tags))
        removed_global_tags = sorted(set(parent_tags) - set(current_tags))

        if new_global_tags or removed_global_tags:
            markdown_output += "### 🏷️ Global Tags Changes\n\n"

            if new_global_tags:
                markdown_output += "#### 🆕 New Global Tags\n\n"
                for tag in new_global_tags:
                    markdown_output += f"- **{tag}**\n"
                markdown_output += "\n"

            if removed_global_tags:
                markdown_output += "#### 🗑️ Removed Global Tags\n\n"
                for tag in removed_global_tags:
                    markdown_output += f"- **{tag}**\n"
                markdown_output += "\n"

        # --- Repo tags changes ---
        repo_tags_changes = {}
        for repo, tags in current_snapshot["repo_tags"].items():
            parent_tags = parent_snapshot["repo_tags"].get(repo, [])
            added = set(tags) - set(parent_tags)
            if added:
                repo_tags_changes[repo] = list(added)
        if repo_tags_changes:
            markdown_output += summarize_repo_section("Repo Tags", repo_tags_changes)

        # --- Repo branches changes ---
        repo_branches_changes = {}
        for repo, branches in current_snapshot["repo_branches"].items():
            parent_branches = parent_snapshot["repo_branches"].get(repo, {})
            for branch_name, commits in branches.items():
                parent_commits = parent_branches.get(branch_name, [])
                # Only show new commits
                new_commits = [c for c in commits if c not in parent_commits]
                if new_commits:
                    if repo not in repo_branches_changes:
                        repo_branches_changes[repo] = {}
                    repo_branches_changes[repo][branch_name] = new_commits
        if repo_branches_changes:
            markdown_output += summarize_repo_section("Repo Branches", repo_branches_changes)

    # Write markdown file
    os.makedirs(MARKDOWN_WORKTREE_DIR, exist_ok=True)
    output_file = os.path.join(MARKDOWN_WORKTREE_DIR, "changes_timeline.md")
    with open(output_file, "w") as f:
        f.write(markdown_output)

    if has_changes(MARKDOWN_WORKTREE_DIR):
        run_cmd(["git", "add", "changes_timeline.md"], cwd=MARKDOWN_WORKTREE_DIR)
        run_cmd(
            ["git", "commit", "-m", f"Update markdown changes ({datetime.now().isoformat()})"],
            cwd=MARKDOWN_WORKTREE_DIR,
        )
        print("✅ Markdown changes generated and committed successfully.")
    else:
        print("ℹ️ No changes to commit in markdown worktree.")

if __name__ == "__main__":
    main()
