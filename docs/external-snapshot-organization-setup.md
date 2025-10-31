# External Snapshot Organization GitHub Token Setup

This document explains how to create a **GitHub Personal Access Token (PAT)** that can be used in `generate_changes.py` to push commits, branches, and tags into an **external snapshot organization**, including creating repositories if they don’t exist.

---

## 1. Log in to GitHub

1. Open [GitHub](https://github.com/) in your browser.
2. Log in with a user account that has **admin or owner permissions** for the external snapshot organization.

---

## 2. Navigate to Personal Access Tokens

1. Click your profile picture in the top-right corner → **Settings**.
2. In the left sidebar, select **Developer settings**.
3. Click **Personal access tokens** → **Fine-grained tokens**
4. Click **Generate new token**.

---

## 3. Configure the Token for Organization Access

1. Give the token a descriptive name, e.g., `External Snapshot Organization Token`.
2. Resource Owner: The external organization
3. Set an expiration date for security.
4. Repository access:
   - All repositories
5. Permissions:
    - **Repository permissions**:
      - `Administration` → **Read & write**

6. Click **Generate token** at the bottom.
7. **Generate token** on the summary (Administration: R/W, Metadata: R/O).

---

## 4. Copy and Save the Token

1. Copy the generated token immediately — you won’t be able to see it again.
2. Store it securely (e.g., in a password manager).
3. Do **not** commit it to your repository.

---

## 5. Set the Token in Your Environment

On your local machine or CI environment, define the environment variable:

```bash
export EXTERNAL_SNAPSHOT_GITHUB_TOKEN="your_generated_token_here"
