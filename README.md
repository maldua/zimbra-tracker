# Zimbra Tracker

A simple tool that exports every branch and tag in a Git repository into
separate text files — one per ref — using filesystem-safe filenames.  
Ideal for diffing, archiving, or auditing history over time.

Aimed at tracking Zimbra Github organization repos specifically.

---

**WARNING: The development stage is in ALPHA QUALITY and it is not ready for production deployment.**

---

## Configuration

The Repository tracking system uses three main configuration files:

1. **`config.py`** – Defines general settings such as snapshot mode and the destination organization.
2. **`tracked_repos.list`** – Lists the repositories to track, including their Git clone URLs and optional platform information.
3. **`categories.yaml`** – Organizes repositories into categories with descriptions, priorities, and assigned repo identifiers.

### Using Sample Files

We provide sample files as templates:

- `config.py.sample`
- `tracked_repos.list.sample`
- `categories.yaml.sample`

You can use these sample files as a guide to create your own configuration files. Simply copy the sample, adjust the values for your organization, repositories, and categories, and save them without the `.sample` extension (e.g., `config.py`, `tracked_repos.list`, `categories.yaml`).

### Generating Suggested Configuration Files

Optionally, you can use the `suggest_conf.py` script to generate suggested configuration files automatically. This can help you get started quickly with defaults based on a public GitHub organization.

Example usage:

```bash
python3 suggest_conf.py Zimbra maldua-zimbra-snapshot True
```

- Zimbra – The source GitHub organization to fetch repositories from (public).
- maldua-zimbra-snapshot – The destination organization for snapshot mode (optional).
- True – Enable snapshot mode (optional; defaults to False).

The script will generate:

- config.py.suggested
- tracked_repos.list.suggested
- categories.yaml.suggested

You can review these suggested files, make any adjustments needed, and then copy them as your default configuration files.

## Setup

This repo needs to write to a remote by default.

You can either set it up to write it back to Github:
```bash
cd zimbra-tracker
git fetch origin tracking
git branch tracking origin/tracking
git branch --set-upstream-to=origin/tracking tracking
```

Or you can make it write to a local directory with something like:
```bash
cd zimbra-tracker
mkdir ../zimbra-tracking-local-repo
git clone . ../zimbra-tracking-local-repo
git remote add localtracking ../zimbra-tracking-local-repo

git fetch origin
git branch tracking origin/tracking

cd ../zimbra-tracking-local-repo
git fetch origin
git branch tracking origin/tracking

cd ../zimbra-tracker
git fetch localtracking tracking
git branch --set-upstream-to=localtracking/tracking tracking
```

## 🔧 Features

- Exports all **branches** and **tags** separately.
- Each ref is written to its own `.txt` file.
- Filenames are **percent-encoded** to avoid filesystem issues.
- Creates a `refs-manifest.json` mapping encoded ↔ original names.
- Easy to diff between branches or tags using standard tools.

## How to add events

```
python add_event.py --title "Acme NE 10.1.1" --date "2025-10-13T14:30:00Z" --description "$(cat <<'MARKDOWN'
Acme NE 10.1.1 has been released.

**Bold**

- Feature A
- Feature B

MARKDOWN
)"
```

## 📦 Tracking Branch File Structure (Per Repo)

Each tracked repository has its own directory containing separate folders for branches and tags, along with a manifest mapping encoded filenames back to the original ref names.

Example structure for multiple repos:

```
repos/
├── zm-mailbox/
│ ├── branches/
│ │ ├── main.txt
│ │ └── feature%2Fapi-v2.txt
│ ├── tags/
│ │ ├── v1.0.0.txt
│ │ └── hotfix%3Av1.0.1.txt
│ └── refs-manifest.json
├── zm-zcs/
│ ├── branches/
│ │ └── main.txt
│ ├── tags/
│ │ └── v10.0.0.txt
│ └── refs-manifest.json
└── zm-build/
├── branches/
│ └── main.txt
├── tags/
│ └── v1.0.0.txt
└── refs-manifest.json
```


### 🔹 Notes

- Each branch or tag has its **own text file** containing the commits (ID + first line of message, optionally with date).
- This structure allows easy diffing, incremental tracking, and per-repo snapshots.
