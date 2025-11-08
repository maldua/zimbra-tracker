# Example configuration for generate_changes.py
# Copy this to config.py and edit as needed

SNAPSHOT_ORG = "acmeoo-snapshot"
SNAPSHOT_MODE = True

# ----------------------
# Throttling variables
# ----------------------
_last_git_call_time = 0
_GIT_CALL_INTERVAL = 0.5  # seconds between git commands

_last_api_call_time = 0
_API_CALL_INTERVAL = 1  # seconds between GitHub API calls
