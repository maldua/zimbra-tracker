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
            ["git", "rev-list", "--parents", "-n", "1", commit_hash], cwd=TRACKING_WORKTREE_DIR
        ).split()
        commit_parents = parents_line[1:]  # skip the commit itself

        # Skip root commits (no parent)
        if not commit_parents:
            continue

        parent_hash = commit_parents[0]

        commit_time = run_cmd(
            ["git", "show", "-s", "--format=%ci", commit_hash], cwd=TRACKING_WORKTREE_DIR
        )
        markdown_output += f"## Snapshot {commit_time}\n\n"

        # Load current and parent snapshots
        current_snapshot = {
            "global_tags": yaml.safe_load(read_tracking_file(commit_hash, "all_tags.yaml") or "[]"),
            "repo_tags": yaml.safe_load(read_tracking_file(commit_hash, "repo_tags.yaml") or "{}"),
            "repo_branches": yaml.safe_load(read_tracking_file(commit_hash, "repo_branches.yaml") or "{}"),
        }

        parent_snapshot = {
            "global_tags": yaml.safe_load(read_tracking_file(parent_hash, "all_tags.yaml") or "[]"),
            "repo_tags": yaml.safe_load(read_tracking_file(parent_hash, "repo_tags.yaml") or "{}"),
            "repo_branches": yaml.safe_load(read_tracking_file(parent_hash, "repo_branches.yaml") or "{}"),
        }

        # --- Global tags changes ---
        new_global_tags = set(current_snapshot["global_tags"]) - set(parent_snapshot["global_tags"])
        removed_global_tags = set(parent_snapshot["global_tags"]) - set(current_snapshot["global_tags"])
        if new_global_tags or removed_global_tags:
            global_tags_changes = {}
            if new_global_tags:
                global_tags_changes.update({tag: [] for tag in new_global_tags})
            if removed_global_tags:
                global_tags_changes.update({f"{tag} (removed)": [] for tag in removed_global_tags})
            markdown_output += summarize_repo_section("Global Tags", global_tags_changes)

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

    # Commit result in markdown repo
    run_cmd(["git", "add", "changes_timeline.md"], cwd=MARKDOWN_WORKTREE_DIR)
    run_cmd(
        ["git", "commit", "-m", f"Update markdown changes ({datetime.now().isoformat()})"],
        cwd=MARKDOWN_WORKTREE_DIR,
    )

    print("✅ Markdown changes generated and committed successfully.")

if __name__ == "__main__":
    main()
