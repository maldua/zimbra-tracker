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
from datetime import timezone
from subprocess import run, PIPE
from pathlib import Path
import subprocess
import json
import re
from urllib.parse import urlparse
import shutil

# --- Constants ---
TRACKING_WORKTREE_DIR = "../zimbra-tracker-tracking"
EVENTS_WORKTREE_DIR = "../zimbra-tracker-events"
MARKDOWN_WORKTREE_DIR = "../zimbra-tracker-markdown-changes"
EVENTS_BRANCH = "events"
MARKDOWN_BRANCH = "markdown_changes"
EVENTS_DIR = os.path.join(TRACKING_WORKTREE_DIR, EVENTS_BRANCH)

TMP_REPOS_DIR = "tmp_repos"  # must match track_refs.py
TMP_WORK_DIR = "tmp_work_repos"  # ephemeral working clones for creating snapshots
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")  # optional, for API fallback
EXTERNAL_SNAPSHOT_GITHUB_TOKEN = os.environ.get("EXTERNAL_SNAPSHOT_GITHUB_TOKEN")

try:
    import config
    SNAPSHOT_ORG = config.SNAPSHOT_ORG
    snapshot_mode = config.SNAPSHOT_MODE
except ImportError:
    # fallback defaults
    SNAPSHOT_ORG = ""
    snapshot_mode = False

# --- Helpers ---
def run_cmd(cmd, cwd=None):
    """Run shell command and return stdout as string."""
    result = run(cmd, cwd=cwd, stdout=PIPE, stderr=PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()

def detect_git_platform(url):
    """Return 'github' or 'gitlab' or 'unknown' based on repo URL."""
    url_lower = url.lower()
    if "github.com" in url_lower:
        return "github"
    elif "gitlab.com" in url_lower:
        return "gitlab"
    else:
        return "unknown"

def load_repo_config(filepath="zimbra_tracked_repos.txt"):
    """Load repository URL and platform info."""
    repos = {}
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = re.split(r"\s+", line)
            if len(parts) < 2:
                continue

            repo_id, repo_url = parts[0], parts[1]
            platform = parts[2] if len(parts) > 2 else detect_git_platform(repo_url)

            # Extract clean base for link generation
            normalized_url = normalize_repo_url(repo_url, platform)
            repos[repo_id] = {"url": repo_url, "platform": platform, "base": normalized_url}

    return repos

def normalize_repo_url(repo_url, platform):
    """Normalize SSH or HTTPS git URLs to a web base URL."""
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]

    if repo_url.startswith("git@"):
        # Convert SSH form like git@github.com:user/repo to https://github.com/user/repo
        match = re.match(r"git@([^:]+):(.+)", repo_url)
        if match:
            host, path = match.groups()
            return f"https://{host}/{path}"
    elif repo_url.startswith("http"):
        parsed = urlparse(repo_url)
        return f"https://{parsed.netloc}{parsed.path}"

    # fallback
    return repo_url

def make_repo_links(base_url, platform, repo_id, ref_name, commit_hash=None, type="tag"):
    """
    Return dictionary with tag/tree/commit links depending on platform.

    Parameters:
        base_url (str): Base URL of the repo (e.g., https://github.com/org/repo)
        platform (str): 'github', 'gitlab', or other
        repo_id (str): Repository identifier (optional, kept for compatibility)
        ref_name (str): Tag or branch name
        commit_hash (str, optional): Specific commit hash for commit link
        type (str): 'tag' or 'branch' (default 'tag')

    Returns:
        dict: Dictionary with 'tag', 'tree', 'commits', 'commit' links
    """
    if platform == "github":
        if type == "branch":
            return {
                "ref": f"{base_url}/tree/{ref_name}",        # Use 'tree' as the main ref link
                "tree": f"{base_url}/tree/{ref_name}",
                "commits": f"{base_url}/commits/{ref_name}",
                "commit": f"{base_url}/commit/{commit_hash}" if commit_hash else None
            }
        else:  # default is 'tag'
            return {
                "ref": f"{base_url}/releases/tag/{ref_name}",
                "tree": f"{base_url}/tree/{ref_name}",
                "commits": f"{base_url}/commits/{ref_name}",
                "commit": f"{base_url}/commit/{commit_hash}" if commit_hash else None
            }

    elif platform == "gitlab":
        if type == "branch":
            return {
                "ref": f"{base_url}/-/tree/{ref_name}",
                "tree": f"{base_url}/-/tree/{ref_name}",
                "commits": f"{base_url}/-/commits/{ref_name}",
                "commit": f"{base_url}/-/commit/{commit_hash}" if commit_hash else None
            }
        else:
            return {
                "ref": f"{base_url}/-/tags/{ref_name}",
                "tree": f"{base_url}/-/tree/{ref_name}",
                "commits": f"{base_url}/-/commits/{ref_name}",
                "commit": f"{base_url}/-/commit/{commit_hash}" if commit_hash else None
            }

    else:
        # Unknown platform, fallback to GitHub-style URLs
        return {
            "ref": f"{base_url}/releases/tag/{ref_name}",
            "tree": f"{base_url}/tree/{ref_name}",
            "commits": f"{base_url}/commits/{ref_name}",
            "commit": f"{base_url}/commit/{commit_hash}" if commit_hash else None
        }

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

def format_commit(repo_config, commit, repo_id, prefix=""):
    """
    Format a single commit into markdown.

    Args:
        repo_config: Repositories configuration
        commit (dict): Commit dictionary containing commit, timestamp, author, committer, message
        repo_id (str): Repository name for GitHub URLs
        prefix (str): Optional prefix like 'NEW' or 'REMOVED'

    Returns:
        str: Markdown string representing the commit
    """
    chash = commit.get("commit", "unknown")[:12]
    msg = commit.get("message", "_(no message)_")
    author = commit.get("author", "Unknown")
    committer = commit.get("committer", "Unknown")
    ts = commit.get("timestamp", 0)
    dt = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S UTC")

    cfg = repo_config.get(repo_id, {})
    base = cfg.get("base", f"https://github.com/Zimbra/{repo_id}")
    platform = cfg.get("platform", "github")
    links = make_repo_links(base, platform, repo_id, "", chash)
    github_url = links["commit"]

    prefix_str = f"**{prefix}**" if prefix else "_"
    return (
        f"    - {dt} | {prefix_str} | **[{chash}]({github_url})** [{msg}]({github_url}) "
        f"| authored by *{author}* | committed by *{committer}*\n"
    )

def format_recent_commits(repo_config, commit_hash, markdown_output, repo_id, ref_name, ref_file_path, prefix=""):
    """
    Append the last 5 commits of a tag or branch to markdown_output using format_commit.
    """
    file_content = read_tracking_file(commit_hash, ref_file_path)
    if not file_content:
        return markdown_output

    commits_json = []
    for line in file_content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            commits_json.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    last_commits = commits_json[-5:][::-1]  # newest first

    for commit in last_commits:
        markdown_output += format_commit(repo_config, commit, repo_id, prefix=prefix)

    markdown_output += "\n"
    return markdown_output

def get_tracking_commit_timestamp():
    """
    Get the timestamp of the latest commit in the tracking branch.
    Returns a string like '2025-10-14T18-21-07Z'.
    """
    commit_time = run_cmd(
        ["git", "show", "-s", "--format=%ci", "tracking"],
        cwd=TRACKING_WORKTREE_DIR,
    )
    from datetime import datetime, timezone
    dt = datetime.strptime(commit_time.strip(), "%Y-%m-%d %H:%M:%S %z")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

def snapshot_name_for(ref_name):
    ts = get_tracking_commit_timestamp()
    return f"{ref_name}-snapshot-{ts}"

def prepare_working_clone(repo_id):
    mirror_path = os.path.join(TMP_REPOS_DIR, repo_id)
    if not os.path.exists(mirror_path):
        raise RuntimeError(f"Mirror for {repo_id} not found at {mirror_path}; run track_refs.py first.")
    work_dir = os.path.join(TMP_WORK_DIR, repo_id)
    # remove old work dir
    if os.path.exists(work_dir):
        subprocess.run(["rm", "-rf", work_dir], check=True)
    os.makedirs(TMP_WORK_DIR, exist_ok=True)
    # clone from mirror (mirror is bare); make a normal clone from it
    subprocess.run(["git", "clone", "--no-local", mirror_path, work_dir], check=True)
    return work_dir

def ensure_snapshot_remote_repo(repo_id):
    """
    Ensure that https://github.com/{SNAPSHOT_ORG}/{repo_id}.git exists.
    Tries gh CLI first (preferred). Requires authenticated gh CLI or GITHUB_TOKEN.
    """
    remote_repo = f"https://github.com/{SNAPSHOT_ORG}/{repo_id}.git"
    # Try gh CLI
    try:
        subprocess.run(["gh", "repo", "view", f"{SNAPSHOT_ORG}/{repo_id}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return remote_repo
    except subprocess.CalledProcessError:
        # repo doesn't exist; try to create with gh
        try:
            print(f"Creating repo {SNAPSHOT_ORG}/{repo_id} via `gh`...")
            subprocess.run(["gh", "repo", "create", f"{SNAPSHOT_ORG}/{repo_id}", "--private", "--confirm"], check=True)
            return remote_repo
        except subprocess.CalledProcessError:
            # fallback to API if GITHUB_TOKEN present
            if GITHUB_TOKEN:
                import json
                print(f"Creating repo {SNAPSHOT_ORG}/{repo_id} via GitHub API...")
                repo_data = {
                    "name": repo_id,
                    "private": True,
                    "auto_init": False
                }
                headers = ["-H", f"Authorization: token {GITHUB_TOKEN}", "-H", "Accept: application/vnd.github+json"]
                curl_cmd = ["curl", "-s", "-X", "POST"] + headers + ["https://api.github.com/orgs/" + SNAPSHOT_ORG + "/repos", "-d", json.dumps(repo_data)]
                subprocess.run(curl_cmd, check=True)
                return remote_repo
            else:
                raise RuntimeError(f"Cannot create repo {SNAPSHOT_ORG}/{repo_id}: no gh CLI or GITHUB_TOKEN available.")

# --- Main logic ---
def main():

    if snapshot_mode:
        if not EXTERNAL_SNAPSHOT_GITHUB_TOKEN:
            raise RuntimeError(
                "EXTERNAL_SNAPSHOT_GITHUB_TOKEN is not defined. "
                "Please export it in your environment before running generate_changes.py"
            )

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

    repo_config = load_repo_config("zimbra_tracked_repos.txt")

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

        # Handle regular snapshot
        parent_hash = commit_parents[0]
        commit_time = run_cmd(
            ["git", "show", "-s", "--format=%ci", commit_hash], cwd=TRACKING_WORKTREE_DIR
        )
        markdown_output += f"## Snapshot {commit_time}\n\n"

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
                        f"- **{repo_id}**\n"
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

        # --- Repository tag changes ---
        all_repos = sorted(set(current_repos))  # Sort repos alphabetically
        for repo_id in all_repos:
            current_tags_raw = read_tracking_file(
                commit_hash, f"repos/{repo_id}/tags-manifest.json"
            )
            parent_tags_raw = read_tracking_file(
                parent_hash, f"repos/{repo_id}/tags-manifest.json"
            )

            try:
                current_tags = json.loads(current_tags_raw) if current_tags_raw else {}
            except json.JSONDecodeError:
                current_tags = {}

            try:
                parent_tags = json.loads(parent_tags_raw) if parent_tags_raw else {}
            except json.JSONDecodeError:
                parent_tags = {}

            # --- Detect tag differences ---
            new_tags = []
            changed_tags = []
            removed_tags = []

            # Detect new and changed tags
            for tag_name, tag_data in current_tags.items():
                if tag_name not in parent_tags:
                    new_tags.append(tag_name)
                else:
                    parent_commit = parent_tags[tag_name].get("latest_commit")
                    current_commit = tag_data.get("latest_commit")
                    if parent_commit != current_commit:
                        changed_tags.append(tag_name)

            # Detect removed tags
            for tag_name in parent_tags.keys():
                if tag_name not in current_tags:
                    removed_tags.append(tag_name)

            # --- Output if there are differences ---
            if new_tags or changed_tags or removed_tags:
                markdown_output += f"### 🏷️ Tag Changes in **{repo_id}**\n\n"

                # 🆕 New Tags with latest commits
                if new_tags:
                    markdown_output += "#### 🆕 New Tags\n\n"
                    for tag in new_tags:

                        cfg = repo_config.get(repo_id, {})
                        base = cfg.get("base", f"https://github.com/Zimbra/{repo_id}")
                        platform = cfg.get("platform", "github")
                        links = make_repo_links(base, platform, repo_id, tag)

                        markdown_output += f"- **[{tag}]({links['ref']})** | [Tag]({links['ref']}) | [Tree]({links['tree']}) | [Commits]({links['commits']})"

                        if snapshot_mode:
                            snapshot_base = f"https://github.com/{SNAPSHOT_ORG}/{repo_id}"
                            snapshot_links = make_repo_links(snapshot_base, platform, repo_id, tag)
                            markdown_output += f" | [Snapshot Tag]({snapshot_links['ref']}) | [Tree]({snapshot_links['tree']}) | [Commits]({snapshot_links['commits']})"

                        markdown_output += " | Recent commits 👇\n"

                        tag_file = current_tags[tag].get("file")
                        if tag_file:
                            tag_file_path = f"repos/{repo_id}/tags/{tag_file}"
                            markdown_output = format_recent_commits(repo_config, commit_hash, markdown_output, repo_id, tag, tag_file_path, "")
                    markdown_output += "\n"

                    markdown_output += "\n"

                # 🔄 Updated Tags
                if changed_tags:
                    markdown_output += "#### 🔄 Updated Tags\n\n"
                    for tag in changed_tags:

                        cfg = repo_config.get(repo_id, {})
                        base = cfg.get("base", f"https://github.com/Zimbra/{repo_id}")
                        platform = cfg.get("platform", "github")
                        links = make_repo_links(base, platform, repo_id, tag)

                        parent_commit_hash = parent_tags[tag].get("latest_commit")
                        current_commit_hash = current_tags[tag].get("latest_commit")

                        markdown_output += f"- **[{tag}]({links['ref']})** | [Tag]({links['ref']}) | [Tree]({links['tree']}) | [Commits]({links['commits']})"

                        if snapshot_mode:
                            snapshot_base = f"https://github.com/{SNAPSHOT_ORG}/{repo_id}"
                            snapshot_links = make_repo_links(snapshot_base, platform, repo_id, tag)
                            markdown_output += f" | [Snapshot Tag]({snapshot_links['ref']}) | [Tree]({snapshot_links['tree']}) | [Commits]({snapshot_links['commits']})"

                        markdown_output += f" | [Previous target]({parent_commit_hash}) | Recent commits 👇\n"

                        # (existing commit diff logic remains unchanged below)
                        parent_tag_file = parent_tags[tag].get("file")
                        parent_commits = []
                        if parent_tag_file:
                            parent_file_path = f"repos/{repo_id}/tags/{parent_tag_file}"
                            parent_content = read_tracking_file(parent_hash, parent_file_path)
                            if parent_content:
                                for line in parent_content.splitlines():
                                    line = line.strip()
                                    if not line:
                                        continue
                                    try:
                                        parent_commits.append(json.loads(line))
                                    except json.JSONDecodeError:
                                        continue
                                parent_commits = parent_commits[-5:][::-1]  # newest first
                        parent_hashes = {c.get("commit") for c in parent_commits}

                        # --- Load last 5 current commits ---
                        current_tag_file = current_tags[tag].get("file")
                        current_commits = []
                        if current_tag_file:
                            current_file_path = f"repos/{repo_id}/tags/{current_tag_file}"
                            current_content = read_tracking_file(commit_hash, current_file_path)
                            if current_content:
                                for line in current_content.splitlines():
                                    line = line.strip()
                                    if not line:
                                        continue
                                    try:
                                        current_commits.append(json.loads(line))
                                    except json.JSONDecodeError:
                                        continue
                                current_commits = current_commits[-5:][::-1]  # newest first

                        # --- Determine overlap ---
                        current_hashes = {c.get("commit") for c in current_commits}
                        intersection = parent_hashes & current_hashes
                        no_overlap = len(intersection) == 0

                        # --- Output current commits ---
                        for commit in current_commits:
                            if no_overlap:
                                prefix = "n"
                            else:
                                prefix = "N" if commit.get("commit") not in parent_hashes else "_"
                            markdown_output += format_commit(repo_config, commit, repo_id, prefix=prefix)

                        markdown_output += "\n"

                # 🗑️ Removed Tags
                if removed_tags:
                    markdown_output += "#### 🗑️ Removed Tags\n\n"
                    for tag in removed_tags:
                        parent_commit = parent_tags[tag].get("latest_commit", "unknown")
                        markdown_output += f"- **{tag}** (was `{parent_commit}`)\n"
                    markdown_output += "\n"

        # --- Repository branch changes ---
        all_repos = sorted(set(current_repos))  # Sort repos alphabetically
        for repo_id in all_repos:
            current_branches_raw = read_tracking_file(
                commit_hash, f"repos/{repo_id}/branches-manifest.json"
            )
            parent_branches_raw = read_tracking_file(
                parent_hash, f"repos/{repo_id}/branches-manifest.json"
            )

            try:
                current_branches = json.loads(current_branches_raw) if current_branches_raw else {}
            except json.JSONDecodeError:
                current_branches = {}

            try:
                parent_branches = json.loads(parent_branches_raw) if parent_branches_raw else {}
            except json.JSONDecodeError:
                parent_branches = {}

            # --- Detect branch differences ---
            new_branches = []
            changed_branches = []
            removed_branches = []

            for branch_name, branch_data in current_branches.items():
                if branch_name not in parent_branches:
                    new_branches.append(branch_name)
                else:
                    parent_commit = parent_branches[branch_name].get("latest_commit")
                    current_commit = branch_data.get("latest_commit")
                    if parent_commit != current_commit:
                        changed_branches.append(branch_name)

            for branch_name in parent_branches.keys():
                if branch_name not in current_branches:
                    removed_branches.append(branch_name)

            # Sort branches alphabetically for consistent display
            new_branches.sort()
            changed_branches.sort()
            removed_branches.sort()

            # --- Output if there are differences ---
            if new_branches or changed_branches or removed_branches:
                markdown_output += f"### 🌿 Branch Changes in **{repo_id}**\n\n"

                # 🆕 New Branches
                if new_branches:
                    markdown_output += "#### 🆕 New Branches\n\n"
                    for branch in new_branches:
                        cfg = repo_config.get(repo_id, {})
                        base = cfg.get("base", f"https://github.com/Zimbra/{repo_id}")
                        platform = cfg.get("platform", "github")
                        links = make_repo_links(base, platform, repo_id, branch, type="branch")

                        markdown_output += f"- **[{branch}]({links['ref']})** | [Branch]({links['ref']}) | [Tree]({links['tree']}) | [Commits]({links['commits']})"

                        if snapshot_mode:
                            snapshot_base = f"https://github.com/{SNAPSHOT_ORG}/{repo_id}"
                            snapshot_links = make_repo_links(snapshot_base, platform, repo_id, branch, type="branch")
                            markdown_output += f" | [Snapshot Branch]({snapshot_links['ref']}) | [Tree]({snapshot_links['tree']}) | [Commits]({snapshot_links['commits']})"

                        markdown_output += " | Recent commits 👇\n"

                        branch_file = current_branches[branch].get("file")
                        if branch_file:
                            branch_file_path = f"repos/{repo_id}/branches/{branch_file}"
                            markdown_output = format_recent_commits(repo_config, commit_hash, markdown_output, repo_id, branch, branch_file_path, "")
                    markdown_output += "\n"

                # 🔄 Updated Branches
                if changed_branches:
                    markdown_output += "#### 🔄 Updated Branches\n\n"
                    for branch in changed_branches:
                        cfg = repo_config.get(repo_id, {})
                        base = cfg.get("base", f"https://github.com/Zimbra/{repo_id}")
                        platform = cfg.get("platform", "github")
                        links = make_repo_links(base, platform, repo_id, branch, type="branch")

                        parent_commit_hash = parent_branches[branch].get("latest_commit")
                        current_commit_hash = current_branches[branch].get("latest_commit")

                        markdown_output += f"- **[{branch}]({links['ref']})** | [Branch]({links['ref']}) | [Tree]({links['tree']}) | [Commits]({links['commits']})"

                        if snapshot_mode:
                            snapshot_base = f"https://github.com/{SNAPSHOT_ORG}/{repo_id}"
                            snapshot_links = make_repo_links(snapshot_base, platform, repo_id, branch, type="branch")
                            markdown_output += f" | [Snapshot Branch]({snapshot_links['ref']}) | [Tree]({snapshot_links['tree']}) | [Commits]({snapshot_links['commits']})"

                        markdown_output += f" | [Previous target]({parent_commit_hash}) | Recent commits 👇\n"

                        # --- Load parent commits ---
                        parent_branch_file = parent_branches[branch].get("file")
                        parent_commits = []
                        if parent_branch_file:
                            parent_file_path = f"repos/{repo_id}/branches/{parent_branch_file}"
                            parent_content = read_tracking_file(parent_hash, parent_file_path)
                            if parent_content:
                                for line in parent_content.splitlines():
                                    line = line.strip()
                                    if not line:
                                        continue
                                    try:
                                        parent_commits.append(json.loads(line))
                                    except json.JSONDecodeError:
                                        continue
                                parent_commits = parent_commits[-5:][::-1]  # newest first
                        parent_hashes = {c.get("commit") for c in parent_commits}

                        # --- Load last 5 current commits ---
                        current_branch_file = current_branches[branch].get("file")
                        current_commits = []
                        if current_branch_file:
                            current_file_path = f"repos/{repo_id}/branches/{current_branch_file}"
                            current_content = read_tracking_file(commit_hash, current_file_path)
                            if current_content:
                                for line in current_content.splitlines():
                                    line = line.strip()
                                    if not line:
                                        continue
                                    try:
                                        current_commits.append(json.loads(line))
                                    except json.JSONDecodeError:
                                        continue
                                current_commits = current_commits[-5:][::-1]  # newest first

                        # --- Determine overlap ---
                        current_hashes = {c.get("commit") for c in current_commits}
                        intersection = parent_hashes & current_hashes
                        no_overlap = len(intersection) == 0

                        # --- Output current commits ---
                        for commit in current_commits:
                            if no_overlap:
                                prefix = "n"
                            else:
                                prefix = "N" if commit.get("commit") not in parent_hashes else "_"
                            markdown_output += format_commit(repo_config, commit, repo_id, prefix=prefix)

                        markdown_output += "\n"

                # 🗑️ Removed Branches
                if removed_branches:
                    markdown_output += "#### 🗑️ Removed Branches\n\n"
                    for branch in removed_branches:
                        parent_commit = parent_branches[branch].get("latest_commit", "unknown")
                        markdown_output += f"- **{branch}** (was `{parent_commit}`)\n"
                    markdown_output += "\n"

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

    if snapshot_mode:
        if not EXTERNAL_SNAPSHOT_GITHUB_TOKEN:
            raise RuntimeError(
                "EXTERNAL_SNAPSHOT_GITHUB_TOKEN is not defined. "
                "Please export it in your environment before running generate_changes.py"
            )


        # Skip if there are no commits or only the very first commit
        if len(tracking_commits) <= 1:
            print("ℹ️ No useful commits found. Skipping snapshot processing.")
            # Proceed to cleanup TMP_WORK_DIR and other necessary tasks
            # Do not return here, so cleanup can happen
            pass
        else:
            # --- Define current_repos based on the very first commit ---
            last_commit_hash = tracking_commits[-1]  # Get the first commit in the reversed list
            current_repos_raw = read_tracking_file(last_commit_hash, "all-repos.json")

            try:
                current_repos = json.loads(current_repos_raw) if current_repos_raw else []
            except json.JSONDecodeError:
                current_repos = []

            # If current_repos is empty or doesn't have useful data, skip snapshot processing
            if not current_repos:
                print("ℹ️ No useful repository data found in the first commit. Skipping snapshot processing.")
                # Proceed to cleanup TMP_WORK_DIR and other necessary tasks
                pass
            else:
                # Get parent commits
                parents_line = run_cmd(
                    ["git", "rev-list", "--parents", "-n", "1", last_commit_hash],
                    cwd=TRACKING_WORKTREE_DIR
                ).split()
                commit_parents = parents_line[1:]  # skip the commit itself
                parent_hash = commit_parents[0]

                # --- Repo processing and snapshot/push ---
                all_repos = sorted(set(current_repos))  # Sort repos alphabetically
                for repo_id in all_repos:

                    repo_changed = False

                    # --- Detect tag changes ---
                    current_tags_data = current_snapshot["repo_tags"].get(repo_id, {})
                    parent_tags_data = parent_snapshot["repo_tags"].get(repo_id, {})

                    new_tags = [t for t in current_tags_data if t not in parent_tags_data]
                    changed_tags = [
                        t for t in current_tags_data
                        if t in parent_tags_data and current_tags_data[t].get("latest_commit") != parent_tags_data[t].get("latest_commit")
                    ]

                    # --- Detect branch changes ---
                    current_branches = current_snapshot["repo_branches"].get(repo_id, {})
                    parent_branches = parent_snapshot["repo_branches"].get(repo_id, {})

                    new_branches = [b for b in current_branches if b not in parent_branches]
                    changed_branches = [
                        b for b in current_branches
                        if b in parent_branches and current_branches[b] != parent_branches[b]
                    ]

                    if new_tags or changed_tags or new_branches or changed_branches:
                        repo_changed = True

                    if repo_changed:
                        print(f"📦 Processing snapshots for repo {repo_id}...")

                        # --- Prepare working clone ---
                        work_dir = prepare_working_clone(repo_id)

                        # --- Create snapshot tags ---
                        for tag in new_tags + changed_tags:
                            latest_commit = current_tags_data[tag]["latest_commit"]
                            snapshot_tag = snapshot_name_for(tag)
                            subprocess.run(
                                ["git", "tag", "-f", snapshot_tag, latest_commit],
                                cwd=work_dir,
                                check=True
                            )
                            print(f"🏷️ Created snapshot tag {snapshot_tag} for {tag}")

                        # --- Create snapshot branches ---
                        for branch in new_branches + changed_branches:
                            commits = current_branches[branch]
                            latest_commit = commits[-1]
                            snapshot_branch = snapshot_name_for(branch)
                            subprocess.run(
                                ["git", "branch", "-f", snapshot_branch, latest_commit],
                                cwd=work_dir,
                                check=True
                            )
                            print(f"🌿 Created snapshot branch {snapshot_branch} for {branch}")

                        # --- Ensure remote repo exists ---
                        remote_repo_url = ensure_snapshot_remote_repo(repo_id)

                        # --- Inject token for HTTPS URL ---
                        if remote_repo_url.startswith("https://"):
                            remote_repo_url_with_token = remote_repo_url.replace(
                                "https://", f"https://{EXTERNAL_SNAPSHOT_GITHUB_TOKEN}@"
                            )
                        else:
                            remote_repo_url_with_token = remote_repo_url

                        # --- Push all local branches and tags (force) ---
                        subprocess.run(["git", "push", "--force", remote_repo_url_with_token, "--all"], cwd=work_dir, check=True)
                        subprocess.run(["git", "push", "--force", remote_repo_url_with_token, "--tags"], cwd=work_dir, check=True)
                        print(f"✅ Pushed snapshots and all refs for {repo_id}")

    if os.path.exists(TMP_WORK_DIR):
        shutil.rmtree(TMP_WORK_DIR)
        print(f"✅ Removed all temporary work clones at {TMP_WORK_DIR}")

if __name__ == "__main__":
    main()
