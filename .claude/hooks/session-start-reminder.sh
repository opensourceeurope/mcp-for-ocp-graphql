#!/usr/bin/env bash
# SessionStart hook: front-loads the dev-workflow skill requirement so the
# assistant invokes it BEFORE the first edit, instead of being caught by
# branch-guard.sh mid-task. The branch guard is the safety net; this is the
# actual instruction.

set -u

jq -n '{
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: (
      "DEV-WORKFLOW REQUIREMENT (mcp-for-ocp-graphql):\n" +
      "Before ANY tool call that mutates this repo (Edit, Write, MultiEdit, NotebookEdit, " +
      "or Bash commands that change files / git state / installed deps), " +
      "you MUST invoke the `dev-workflow` skill via the Skill tool and follow it.\n\n" +
      "The flow: work in a per-topic worktree off main (never edit main directly), open a PR, " +
      "let CI pass (commitlint.yml conventional-commit lint; security-audit.yml — zizmor workflow " +
      "lint + pip-audit), merge to main, then release-please (release.yml) handles versioning, " +
      "changelog, the plugin version/pin, the tag + GitHub Release, and the PyPI publish. " +
      "Branching is only the first step — invoking the skill is non-negotiable, even if you already know to branch.\n\n" +
      "If the PreToolUse branch guard denies an edit, the correct response is to invoke the `dev-workflow` skill " +
      "FIRST and then follow it end to end. Do not just `git switch -c` and retry — that bypasses the workflow."
    )
  }
}'
