"""
refname_utils.py

Helper functions to convert Git branch or tag names into filesystem-safe filenames
and back, using percent-encoding. This ensures safe storage on any filesystem,
including ext4, NTFS, or macOS HFS/APFS.

Also provides optional helpers for generating full paths under a per-repo directory.
"""

import urllib.parse
import os

def safe_refname_to_filename(ref_name: str) -> str:
    """
    Encode a Git ref name into a filesystem-safe filename.
    All characters except alphanumerics, '-', '_', and '.' are percent-encoded.
    """
    return urllib.parse.quote(ref_name, safe='A-Za-z0-9-_.') + ".txt"

def filename_to_refname(filename: str) -> str:
    """
    Decode a filename back into the original Git ref name.
    Assumes the filename ends with '.txt' and was percent-encoded.
    """
    if filename.endswith(".txt"):
        filename = filename[:-4]
    return urllib.parse.unquote(filename)

def branch_file_path(repo_dir: str, branch_name: str) -> str:
    """
    Return the full path to store a branch commit list under a given repo directory.
    Example: repos/zm-mailbox/branches/<encoded-branch>.txt
    """
    filename = safe_refname_to_filename(branch_name)
    return os.path.join(repo_dir, "branches", filename)

def tag_file_path(repo_dir: str, tag_name: str) -> str:
    """
    Return the full path to store a tag commit list under a given repo directory.
    Example: repos/zm-mailbox/tags/<encoded-tag>.txt
    """
    filename = safe_refname_to_filename(tag_name)
    return os.path.join(repo_dir, "tags", filename)

# Optional: simple test
if __name__ == "__main__":
    test_refs = ["main", "feature/feature1", "release/9.0.0", "hotfix:urgent"]
    for ref in test_refs:
        f = safe_refname_to_filename(ref)
        r = filename_to_refname(f)
        print(f"{ref} -> {f} -> {r}")
        assert ref == r, "Round-trip failed!"
