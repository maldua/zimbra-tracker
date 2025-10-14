# Zimbra Tracker

A simple tool that exports every branch and tag in a Git repository into
separate text files — one per ref — using filesystem-safe filenames.  
Ideal for diffing, archiving, or auditing history over time.

Aimed at tracking Zimbra Github organization repos specifically.

---

**WARNING: The development stage is in ALPHA QUALITY and it is not ready for production deployment.**

---

## 🔧 Features

- Exports all **branches** and **tags** separately.
- Each ref is written to its own `.txt` file.
- Filenames are **percent-encoded** to avoid filesystem issues.
- Creates a `refs-manifest.json` mapping encoded ↔ original names.
- Easy to diff between branches or tags using standard tools.

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
