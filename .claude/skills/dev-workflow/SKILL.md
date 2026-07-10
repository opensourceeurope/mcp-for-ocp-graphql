---
name: dev-workflow
description: Use when starting any change to mcp-for-ocp-graphql — starting a change, branching, running locally, writing a commit, opening a PR, bumping a version, or cutting a release. Covers per-topic worktrees, the branch + PR + CI flow, conventional commits, the release-please release-PR flow, what release-please owns (never hand-edit), and the release → PyPI + hosted-deploy chain.
---

# mcp-for-ocp-graphql Dev Workflow

## Step 0 — know your branch, every time

Before reading code to answer a question OR before editing, run `git status -sb`.
The checked-out tree is often a **stale topic branch**: reporting "the code does X"
from it is wrong if `main` already changed X. If HEAD is behind `origin/main`, say so
up front and answer against `origin/main` (`git grep … origin/main`,
`git show origin/main:<file>`), not the stale working tree.

## Parallel topics — one worktree per topic

A single checkout has one `HEAD`, so two sessions sharing one directory fight over the
branch. Use a **git worktree per topic** — each is its own directory with its own
checked-out branch, all backed by this repo's single `.git`.

**The one rule: never edit/develop on main; always a topic worktree.**

```bash
.claude/skills/dev-workflow/resources/worktree.sh new feat/<short-name>   # creates .worktrees/<name> off fresh origin/main
.claude/skills/dev-workflow/resources/worktree.sh list
.claude/skills/dev-workflow/resources/worktree.sh rm  feat/<short-name>    # removes the dir; branch stays
```

Then open `.worktrees/<name>` and work there. Install dev deps with `uv sync` inside the
worktree. `.worktrees/` is gitignored, and the branch-guard hook is worktree-aware (it
gates each file by the branch of the worktree that owns it).

**A worktree is required, not optional:** the branch-guard hook makes the shared main
checkout read-only for edits (any branch), so all topic work happens in a
`.worktrees/<topic>` directory. The main checkout's HEAD is shared and a concurrent
session can switch it mid-task, landing your commit on the wrong branch; a worktree pins
one branch to one directory, which git enforces.

## The flow

```
.claude/skills/dev-workflow/resources/worktree.sh new feat/<short-name>  # 1. fresh worktree off origin/main
# open .worktrees/feat-<short-name> and work THERE
# ... make changes; before pushing run /simplify (or /code-review) on the diff ...
git push -u origin feat/<short-name>  # 2. push the branch
# 3. open a PR
# 4. CI must pass:
#      - commitlint.yml: every commit is a conventional commit
#      - security-audit.yml: zizmor (workflow supply-chain lint) + pip-audit
#      (runs when .github/**, pyproject.toml, or uv.lock change)
#    Run the test suite locally before pushing: `uv run pytest` (and, after an
#    OpenCrane bump or corpus change, the opt-in `uv run pytest -m e2e`).
# 5. merge the PR to main
# 6. release-please (release.yml) opens/updates a rolling release PR (version + changelog + pins)
# 7. that release PR AUTO-MERGES once CI is green → tag vX.Y.Z + GitHub Release, and the
#      SAME release.yml run publishes mcp-for-ocp-graphql to PyPI (trusted publishing)
# 8. build-and-push.yml (on push to main) rebuilds the Docker image and redeploys the
#      hosted Scaleway container
```

**There is NO per-PR preview environment.** You review on the diff + CI, not a preview URL.

Releases are automated by **release-please**. Write conventional commits; release-please
does all the version/changelog/tag work and the release PR auto-merges once its CI is
green. Your job is to commit correctly — never hand-bump anything, and normally not even
merge the release PR.

## Conventional commits (required)

| Prefix | Example | Version effect |
|---|---|---|
| `fix:` | `fix: reject subscriptions too` | **patch** |
| `feat:` | `feat: add transaction search` | **minor** |
| `feat!:` or a `BREAKING CHANGE:` footer | `feat!: drop stdio transport` | **major** |
| `docs:` `ci:` `chore:` `refactor:` `test:` `perf:` | `chore: bump dep` | no release |

`commitlint.yml` fails a PR whose commits don't conform (a mistyped type silently skips
the version bump). Subjects may lead with acronyms/proper nouns — `subject-case` is
disabled in `.commitlintrc.json`.

## The release flow

```
commit feat:/fix:/feat!: to main
  → release.yml (release-please) maintains a rolling release PR that:
      - bumps the version in .release-please-manifest.json + pyproject.toml (release-type python)
      - regenerates CHANGELOG.md
      - writes the version into plugins/opencollective-graphql/.claude-plugin/plugin.json ($.version)
      - a follow-up step runs scripts/sync-plugin-version.sh to rewrite the
        `mcp-for-ocp-graphql==X.Y.Z` pin in plugins/opencollective-graphql/.mcp.json,
        committed onto the PR branch
      - arms GitHub auto-merge (gh pr merge --auto --squash)
  → release PR auto-merges once CI is green → tag vX.Y.Z + GitHub Release, and IN THE SAME
      run release.yml's `publish` job (gated on `releases_created`) builds the wheel and
      publishes to PyPI via trusted publishing.
```

There is no separate `publish-pypi.yml` / `release: published` handoff — publish is a job
in `release.yml`. The hosted Docker image + Scaleway deploy are handled by
`build-and-push.yml` on every push to `main`.

One-time maintainer setup (see `release.yml` header): the `RELEASE_TOKEN` secret (PAT/App
token, Contents + PRs write) must exist; "Allow auto-merge" enabled with `commitlint`
required on `main`; and the PyPI trusted publisher's `workflow_ref` must point at
`release.yml`.

## release-please OWNS these — never hand-edit

- `CHANGELOG.md` — regenerated from commits.
- `pyproject.toml` `[project].version` — release-please python updater.
- `plugins/opencollective-graphql/.claude-plugin/plugin.json` `version` — json updater.
- `plugins/opencollective-graphql/.mcp.json` `mcp-for-ocp-graphql==` pin — the sync step.
- `.release-please-manifest.json` — release-please's version STATE file (auto-managed).
- git tags `vX.Y.Z` + GitHub Releases — created on release-PR merge.

To change a version, land a conventional commit and let release-please bump.
`scripts/sync-plugin-version.sh` exists only for the workflow (and manual recovery with an
explicit version arg) — not for routine edits.

## Invariants enforced by hooks

- **No edits in the shared main checkout** — the PreToolUse branch-guard denies
  `Edit`/`Write` on any file in the primary checkout (and on `main`/`master` in any
  worktree). Edits are only allowed in a linked worktree on a topic branch.
- **Skill discovery** — the SessionStart reminder ensures this skill is invoked before
  any branch-touching action.
- **Wrap-up gate** — the Stop hook reviews whether this session's diff (or a learning)
  should update docs, `.claude/skills`, `.claude/hooks`, or `.github/workflows`.
- `.worktrees/` is gitignored.

## Red flags — stop

- About to describe "what the code does" without checking the branch → run `git status -sb`
  first; if HEAD is behind `origin/main`, reason about `origin/main`.
- About to edit in the shared main checkout, or `git switch -c` there instead of making a
  worktree → use `.claude/skills/dev-workflow/resources/worktree.sh new feat/<name>`. Before
  opening the PR, verify isolation: `git log --oneline origin/main..HEAD` shows only your commits.
- About to `git push` to `main` directly → branch instead.
- About to hand-bump a version (pyproject, plugin.json, .mcp.json pin, manifest) → that's
  release-please's job; land a `feat:`/`fix:` commit.
- About to hand-cut a tag (`git tag vX.Y.Z`) or create a GitHub Release manually → merging
  the release PR does this, and only that path triggers the PyPI publish.
- About to write a non-conventional commit / PR title → `commitlint.yml` fails it and a
  wrong type silently skips the bump.
- About to edit `CHANGELOG.md` by hand → it's release-please-owned; write a good commit message.
