"""
refname_utils.py

Helper functions to convert Git branch or tag names into filesystem-safe filenames
and back, using percent-encoding. This ensures safe storage on any filesystem,
including ext4, NTFS, or macOS HFS/APFS.

Also provides optional helpers for generating full paths under a per-repo directory.
"""

import urllib.parse
import os
import subprocess
import time
import requests
import config

_last_git_call_time = config._last_git_call_time
_GIT_CALL_INTERVAL = config._GIT_CALL_INTERVAL
_last_api_call_time = config._last_api_call_time
_API_CALL_INTERVAL = config._API_CALL_INTERVAL

_last_git_call_time = getattr(config, "_last_git_call_time", 0)
_GIT_CALL_INTERVAL = getattr(config, "_GIT_CALL_INTERVAL", 0.5)  # seconds between Git commands
_last_api_call_time = getattr(config, "_last_api_call_time", 0)
_API_CALL_INTERVAL = getattr(config, "_API_CALL_INTERVAL", 1)  # seconds between GitHub API calls

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

def github_api_request(method, url, **kwargs):
    """Throttle GitHub API requests to avoid hitting rate limits."""
    global _last_api_call_time
    elapsed = time.time() - _last_api_call_time
    if elapsed < _API_CALL_INTERVAL:
        time.sleep(_API_CALL_INTERVAL - elapsed)
    response = requests.request(method, url, **kwargs)
    _last_api_call_time = time.time()

    if response.status_code in (403, 429):
        # Optional: retry after waiting
        retry_after = int(response.headers.get("Retry-After", 3))
        print(f"⚠️ Rate limit hit, waiting {retry_after}s...")
        time.sleep(retry_after)
        return github_api_request(method, url, **kwargs)

    return response

def run_throttled_git_cmd(cmd, cwd=None, capture=True, check=True):
    """Throttle GitHub-interacting git commands."""
    global _last_git_call_time
    elapsed = time.time() - _last_git_call_time
    if elapsed < _GIT_CALL_INTERVAL:
        time.sleep(_GIT_CALL_INTERVAL - elapsed)

    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=capture)
    _last_git_call_time = time.time()

    if check and result.returncode != 0:
        raise RuntimeError(f"Git command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip() if capture else None

# Optional: simple test
if __name__ == "__main__":
    test_refs = ["main", "feature/feature1", "release/9.0.0", "hotfix:urgent"]
    for ref in test_refs:
        f = safe_refname_to_filename(ref)
        r = filename_to_refname(f)
        print(f"{ref} -> {f} -> {r}")
        assert ref == r, "Round-trip failed!"
