#!/usr/bin/env python3
"""
add_event.py
Add an event to the Zimbra Tracker events branch.
Copyright (C) 2025 BTACTIC, S.C.C.L.

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software Foundation,
version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.
You should have received a copy of the GNU General Public License along with this program.
If not, see <http://www.gnu.org/licenses/>.

Usage:
    add_event.py --title "Event title" --description "Event markdown content" [--date YYYY-MM-DDTHH:MM:SSZ]
"""

import os
import sys
import subprocess
import argparse
from datetime import datetime
import yaml

EVENTS_BRANCH = "events"

def run(cmd, cwd=None, capture=True):
    """Run a command and return stdout"""
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=capture)
    if result.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
        sys.exit(1)
    return result.stdout.strip() if capture else None

def get_current_branch():
    """Return the current branch name"""
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"])

def ensure_events_branch():
    """Create or switch to the events orphan branch"""
    branches = run(["git", "branch", "--list", EVENTS_BRANCH]).splitlines()
    if not branches:
        print(f"Creating orphan branch '{EVENTS_BRANCH}'...")
        run(["git", "checkout", "--orphan", EVENTS_BRANCH])
        run(["git", "rm", "-rf", "."])  # start clean
        run(["git", "commit", "--allow-empty", "-m", f"Initial {EVENTS_BRANCH} branch"])
    else:
        print(f"Switching to existing '{EVENTS_BRANCH}' branch...")
        run(["git", "checkout", EVENTS_BRANCH])
        run(["git", "pull"])

def save_event(title, description, date_str):
    """Save the event as a YAML file"""
    os.makedirs("events", exist_ok=True)
    if not date_str:
        date_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    filename = f"events/{date_str.replace(':','').replace('-','').replace('T','_')}_{title.replace(' ','_')}.yaml"
    event = {
        "title": title,
        "date": date_str,
        "description": description
    }
    with open(filename, "w", encoding="utf-8") as f:
        yaml.dump(event, f, sort_keys=False)
    return filename

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True, help="Title of the event")
    parser.add_argument("--description", required=True, help="Markdown description of the event")
    parser.add_argument("--date", help="Date of the event (ISO format), default UTC now")
    args = parser.parse_args()

    original_branch = get_current_branch()  # save original branch

    ensure_events_branch()
    event_file = save_event(args.title, args.description, args.date)

    run(["git", "add", event_file], capture=False)
    run(["git", "commit", "-m", f"Add event: {args.title}"], capture=False)
    run(["git", "push", "--set-upstream", "origin", EVENTS_BRANCH], capture=False)
    print(f"Event '{args.title}' added in {EVENTS_BRANCH} branch.")

    # Switch back to the original branch
    run(["git", "checkout", original_branch])
    print(f"Returned to original branch '{original_branch}'.")

if __name__ == "__main__":
    main()
