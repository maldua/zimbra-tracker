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
import sys
import subprocess
import shutil
import json
from datetime import datetime

TRACKING_WORKTREE_DIR = "../zimbra-tracker-tracking"
MARKDOWN_BRANCH = "markdown_changes"
EVENTS_BRANCH = "events"
OUTPUT_FILE = "CHANGES.md"
REPOS_DIR = os.path.join(TRACKING_WORKTREE_DIR, "repos")
TMP_REPOS_DIR = os.path.join(TRACKING_WORKTREE_DIR, "tmp-repos")

def run(cmd, cwd=None, capture=True):
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=capture)
    if result.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
        sys.exit(1)
    return result.stdout.strip() if capture else None

def ensure_markdown_branch():
    """Ensure the markdown_changes branch exists as orphan and checkout"""
    branches = run(["git", "branch", "--list", MARKDOWN_BRANCH])
    if not branches:
        print(f"Creating orphan branch {MARKDOWN_BRANCH}...")
        run(["git", "checkout", "--orphan", MARKDOWN_BRANCH])
        run(["git", "rm", "-rf", "."])
        run(["git", "commit", "--allow-empty", "-m", f"Initial {MARKDOWN_BRANCH} branch"])
        run(["git", "checkout", "-"])
    run(["git", "checkout", MARKDOWN_BRANCH], cwd=TRACKING_WORKTREE_DIR)

def load_events():
    """Load all events from the events branch into memory"""
    current_branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=TRACKING_WORKTREE_DIR)
    # checkout events branch
    run(["git", "checkout", EVENTS_BRANCH], cwd=TRACKING_WORKTREE_DIR)
    events_dir = os.path.join(TRACKING_WORKTREE_DIR, "events")
    events = []
    if os.path.exists(events_dir):
        for fname in sorted(os.listdir(events_dir)):
            if fname.endswith(".yaml") or fname.endswith(".yml"):
                path = os.path.join(events_dir, fname)
                with open(path, "r", encoding="utf-8") as f:
                    event_data = {}
                    current_key = None
                    content_lines = []
                    for line in f:
                        line = line.rstrip()
                        if line.startswith("date:"):
                            event_data["date"] = line.split(":",1)[1].strip()
                        elif line.startswith("title:"):
                            event_data["title"] = line.split(":",1)[1].strip()
                        elif line.startswith("description:"):
                            current_key = "description"
                            content_lines = []
                        elif current_key == "description":
                            content_lines.append(line)
                    if content_lines:
                        event_data["description"] = "\n".join(content_lines).strip()
                    events.append(event_data)
    # go back to original branch
    run(["git", "checkout", current_branch], cwd=TRACKING_WORKTREE_DIR)
    events.sort(key=lambda e: e["date"])
    return events

def get_snapshots():
    """Return a list of snapshot commit hashes in tracking branch (oldest to newest)"""
    snapshots = run(["git", "log", "--reverse", "--pretty=format:%H", "tracking"], cwd=TRACKING_WORKTREE_DIR).splitlines()
    return snapshots

def load_manifest(repo_id, snapshot_hash):
    """Load manifest JSON from a snapshot"""
    manifest_file = os.path.join(REPOS_DIR, repo_id, "refs-manifest.json")
    if os.path.exists(manifest_file):
        with open(manifest_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def get_last_commits(repo_id, ref_name, is_tag=False, n=5):
    """Return last n commits for a branch or tag"""
    if is_tag:
        path = os.path.join(REPOS_DIR, repo_id, "tags", ref_name)
    else:
        path = os.path.join(REPOS_DIR, repo_id, "branches", ref_name)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    return lines[-n:][::-1]  # newest to oldest

def generate_markdown():
    events = load_events()
    snapshots = get_snapshots()
    markdown_lines = []

    previous_global_tags = set()
    previous_branch_commits = {}
    previous_tag_commits = {}

    for snap_hash in reversed(snapshots):  # newest to oldest
        snap_time = run(["git", "show", "-s", "--format=%cI", snap_hash], cwd=TRACKING_WORKTREE_DIR)
        header = f"## {snap_time} Snapshot"
        snapshot_lines = [header, ""]
        # Events
        snapshot_lines.append("### Events\n")
        for event in events:
            snapshot_lines.append(f"(Event) {event['date']} {event['title']}\n")
            snapshot_lines.append(event.get("description","") + "\n")
        # Global Tags
        snapshot_lines.append("### Global Tags\n")
        current_global_tags = set()
        for repo_id in os.listdir(REPOS_DIR):
            tag_file = os.path.join(REPOS_DIR, repo_id, "tags-manifest.json")
            if os.path.exists(tag_file):
                with open(tag_file, "r", encoding="utf-8") as f:
                    tags = json.load(f)
                    current_global_tags.update(tags.keys())
        new_tags = current_global_tags - previous_global_tags
        removed_tags = previous_global_tags - current_global_tags
        for t in sorted(new_tags):
            snapshot_lines.append(f"- New {t} tag")
        for t in sorted(removed_tags):
            snapshot_lines.append(f"- {t} tag was removed")
        previous_global_tags = current_global_tags
        snapshot_lines.append("")
        # Repo changes: Tags
        snapshot_lines.append("### Repo changes (Tags)\n")
        for repo_id in os.listdir(REPOS_DIR):
            tag_file = os.path.join(REPOS_DIR, repo_id, "tags-manifest.json")
            if os.path.exists(tag_file):
                with open(tag_file, "r", encoding="utf-8") as f:
                    tags = json.load(f)
                    for t in tags.keys():
                        if previous_tag_commits.get((repo_id, t)) != True:  # not yet seen
                            snapshot_lines.append(f"[{repo_id}](https://github.com/{repo_id}) - New [{t} tag](https://github.com/{repo_id}/tree/{t})\n(Showing only top 5 commits)\n")
                            commits = get_last_commits(repo_id, t, is_tag=True, n=5)
                            for c in commits:
                                snapshot_lines.append(f"- {c}")
                            previous_tag_commits[(repo_id,t)] = True
        # Repo changes: Branches
        snapshot_lines.append("### Repo changes (Branches)\n")
        for repo_id in os.listdir(REPOS_DIR):
            branch_file = os.path.join(REPOS_DIR, repo_id, "branches-manifest.json")
            if os.path.exists(branch_file):
                with open(branch_file, "r", encoding="utf-8") as f:
                    branches = json.load(f)
                    for b in branches.keys():
                        if previous_branch_commits.get((repo_id,b)) != True:
                            snapshot_lines.append(f"[{repo_id}](https://github.com/{repo_id}) - New commits on [{b} branch](https://github.com/{repo_id}/tree/{b})\n(Showing only top 5 commits)\n")
                            commits = get_last_commits(repo_id, b, is_tag=False, n=5)
                            for c in commits:
                                snapshot_lines.append(f"- {c}")
                            previous_branch_commits[(repo_id,b)] = True
        snapshot_lines.append("\n")
        markdown_lines = snapshot_lines + markdown_lines  # newest snapshots first

    return "\n".join(markdown_lines)

def main():
    ensure_markdown_branch()
    md_content = generate_markdown()
    output_path = os.path.join(TRACKING_WORKTREE_DIR, OUTPUT_FILE)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Generated markdown in {OUTPUT_FILE}")
    # Commit changes
    os.chdir(TRACKING_WORKTREE_DIR)
    run(["git", "add", OUTPUT_FILE], capture=False)
    snapshot_msg = f"Generate changes {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}"
    run(["git", "commit", "-m", snapshot_msg], capture=False)
    print(f"Committed to branch {MARKDOWN_BRANCH}")

if __name__ == "__main__":
    main()
