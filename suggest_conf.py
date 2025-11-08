#!/usr/bin/env python3
"""
suggest_conf.py

Generates suggested configuration files for Zimbra repository tracking:

- config.py.suggestedconf
- zimbra_tracked_repos_suggested.txt
- categories.yaml.suggested

Usage:
    python suggest_conf.py ORIGIN_ORG [DEST_ORG] [SNAPSHOT_MODE]

Arguments:
    ORIGIN_ORG       (required) GitHub organization to fetch repos from (public)
    DEST_ORG         (optional) Destination organization for snapshot mode
    SNAPSHOT_MODE    (optional) True or False (default: False)
"""

import os
import sys
import requests

SUGGESTED_CONF_PY_FILE="config.py.suggestedconf"
SUGGESTED_ZIMBRA_TRACKED_REPOS="zimbra_tracked_repos_suggested.txt"
SUGGESTED_CATEGORIES="categories.yaml.suggested"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    print("Error: Please set the GITHUB_TOKEN environment variable.")
    sys.exit(1)

API_URL = "https://api.github.com"

def fetch_repos(org):
    """Fetch public repositories for a GitHub organization."""
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    repos = []
    page = 1
    while True:
        url = f"{API_URL}/orgs/{org}/repos?per_page=100&page={page}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            print(f"Error fetching repos from {org}: {resp.status_code}")
            sys.exit(1)
        data = resp.json()
        if not data:
            break
        for repo in data:
            repos.append(repo["name"])
        page += 1
    return sorted(repos)

def generate_config_py(dest_org, snapshot_mode):
    content = "# Example configuration for generate_changes.py\n# Copy this to config.py and edit as needed\n\n"
    if snapshot_mode:
        content += f'SNAPSHOT_ORG = "{dest_org}"\n'
        content += "SNAPSHOT_MODE = True\n"
    else:
        content += "SNAPSHOT_ORG = None\n"
        content += "SNAPSHOT_MODE = False\n"
    with open(SUGGESTED_CONF_PY_FILE, "w") as f:
        f.write(content)
    print(f"Generated {SUGGESTED_CONF_PY_FILE}")

def generate_zimbra_tracked_txt(origin_org, repos):
    lines = ["# Repository identifier      Clone URL  [optional_platform]"]
    for repo in repos:
        url = f"https://github.com/{origin_org}/{repo}.git"
        lines.append(f"{repo.ljust(28)} {url}")
    with open(SUGGESTED_ZIMBRA_TRACKED_REPOS, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Generated {SUGGESTED_ZIMBRA_TRACKED_REPOS}")

def generate_categories_yaml(repos):
    content = """# categories.yaml
# Structured category definitions for Zimbra tracked repositories.
# Each category has a description (Markdown allowed), a priority for ordering, and a list of repo identifiers.

categories:

  category1:
    description: |
      Category 1 description
    priority: 3
    repos:
      - reponame1

  uncategorized:
    description: |
      Repositories that have not been assigned to any category yet.
      These may be new, experimental, or awaiting classification.
    priority: 100
    repos:
"""
    for repo in repos:
        content += f"      - {repo}\n"

    with open(SUGGESTED_CATEGORIES, "w") as f:
        f.write(content)
    print(f"Generated {SUGGESTED_CATEGORIES}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python suggest_conf.py ORIGIN_ORG [DEST_ORG] [SNAPSHOT_MODE]")
        sys.exit(1)

    origin_org = sys.argv[1]
    dest_org = None
    snapshot_mode = False

    if len(sys.argv) >= 3:
        dest_org = sys.argv[2]
    if len(sys.argv) >= 4:
        snapshot_mode = sys.argv[3].lower() in ("true", "1", "yes")

    if snapshot_mode and not dest_org:
        print("Error: snapshot mode requires a destination organization argument.")
        sys.exit(1)

    repos = fetch_repos(origin_org)
    generate_config_py(dest_org, snapshot_mode)
    generate_zimbra_tracked_txt(origin_org, repos)
    generate_categories_yaml(repos)

if __name__ == "__main__":
    main()
