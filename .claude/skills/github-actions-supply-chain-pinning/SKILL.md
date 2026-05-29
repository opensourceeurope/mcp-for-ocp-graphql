---
name: github-actions-supply-chain-pinning
description: "Use when editing any file under .github/workflows/, adding a new GitHub Actions workflow, reviewing a workflow, or installing a CLI tool in a CI step (npm install -g, pipx install, uses: someone/setup-*). Enforces commit-SHA pinning for actions and explicit version pinning for installed tools — the two most common supply-chain holes in GitHub Actions."
---

# GitHub Actions Supply-Chain Pinning

## The two rules

**Rule 1 — Third-party AND first-party actions must be pinned to a full 40-character commit SHA, with the human-readable version as a trailing comment:**

```yaml
uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1
```

Never `@v4`, `@main`, `@latest`, or any moving ref. `actions/*` from GitHub get the same treatment as third-party — the supply-chain risk is identical (compromised maintainer account, malicious tag retag).

**Rule 2 — CLI tools installed inside a step must be pinned to an explicit version, never `@latest` / `version: latest`:**

```yaml
# BAD
- run: npm install --global vercel@latest
- uses: supabase/setup-cli@<sha>
  with:
    version: latest

# GOOD
env:
  VERCEL_CLI_VERSION: 54.4.1
steps:
  - run: npm install --global vercel@${VERCEL_CLI_VERSION}
  - uses: supabase/setup-cli@<sha> # vX.Y.Z
    with:
      version: 2.101.0
```

## How to resolve a SHA correctly

```bash
# Lightweight tag (points directly at a commit):
gh api repos/<owner>/<repo>/git/refs/tags/<tag> --jq '.object.sha'

# Annotated tag (object.type == "tag" — must dereference one more level):
gh api repos/<owner>/<repo>/git/tags/<tag-object-sha> --jq '.object.sha'
```

Verify the SHA exists and confirm the human-readable version before you write the comment:

```bash
gh api repos/<owner>/<repo>/commits/<sha> --jq '.sha'
gh api repos/<owner>/<repo>/tags --paginate \
  --jq '.[] | select(.commit.sha=="<sha>") | .name'
```

If you can't run `gh`, say so — do not guess a SHA. A wrong SHA either fails the workflow or, worse, silently points at the wrong code.

## Bumping a pin

- One pin per commit (or one logical group per commit), referencing the upstream changelog in the message.
- Update the SHA **and** the trailing version comment together. A stale `# v4.3.1` next to a v5 SHA is worse than no comment.

## Red flags — stop and fix

| You see / are about to write                        | Do this instead                       |
|-----------------------------------------------------|---------------------------------------|
| `uses: foo/bar@v4` or `@main` / `@master`           | Resolve to SHA, add `# v4.x.y`        |
| `uses: actions/checkout@<sha>` with no version note | Add `# vX.Y.Z` trailing comment       |
| `npm i -g <tool>@latest`, `pipx install <tool>`     | Pin to explicit version               |
| `with: { version: latest }`                         | Pin to explicit version               |
| Bumping a pin but leaving the old version comment   | Update SHA and comment in one edit    |

## Rationalizations to reject

- "It's just `actions/checkout`, it's from GitHub." → Same risk class as any third-party action.
- "The repo has Dependabot, it'll bump it." → Dependabot only works if the *starting state* is pinned to a SHA.
- "Pinning makes the workflow harder to read." → The trailing `# vX.Y.Z` comment restores readability. Non-negotiable.
- "I'll pin later." → Later = never. Pin in the same change.

## CI enforcement (defense in depth)

Pinning by hand is necessary but not sufficient. Recommend the repo also runs [`zizmor`](https://github.com/zizmorcore/zizmor) in CI against `.github/workflows/` — it catches unpinned actions, `@latest` installs, and other supply-chain smells automatically. The skill enforces correctness during authoring; zizmor enforces it at PR time.
