#!/usr/bin/env bash
# Manage per-topic git worktrees for mcp-for-ocp-graphql.
#
# One worktree = one checked-out branch in its own directory, all sharing this
# repo's single .git. Run each parallel topic (and each Claude session) in its
# own worktree so concurrent sessions never switch another session's branch out
# from under it. See .claude/skills/dev-workflow/SKILL.md.
#
#   .claude/skills/dev-workflow/resources/worktree.sh new <branch-name>   create .worktrees/<name> off fresh origin/main
#   .claude/skills/dev-workflow/resources/worktree.sh list                list worktrees
#   .claude/skills/dev-workflow/resources/worktree.sh rm <branch-name>    remove the worktree dir (keeps the branch)
#
# Install dev deps with `uv sync` inside the worktree.
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Manage per-topic git worktrees for mcp-for-ocp-graphql.

Usage:
  .claude/skills/dev-workflow/resources/worktree.sh new <branch-name>   create .worktrees/<name> off fresh origin/main
  .claude/skills/dev-workflow/resources/worktree.sh list                list worktrees
  .claude/skills/dev-workflow/resources/worktree.sh rm <branch-name>    remove the worktree dir (keeps the branch)
EOF
  exit "${1:-0}"
}

# Resolve the MAIN checkout root from the shared git-common-dir, so this works
# whether invoked from the main checkout or from inside another worktree.
common_dir=$(git rev-parse --git-common-dir)
case "$common_dir" in
  /*) ;;
  *) common_dir="$(git rev-parse --show-toplevel)/$common_dir" ;;
esac
main_root=$(cd "$common_dir/.." && pwd)
wt_root="$main_root/.worktrees"

# A branch name may contain slashes (feat/foo); flatten them for the directory.
dir_for() { printf '%s/%s' "$wt_root" "$(printf '%s' "$1" | tr '/' '-')"; }

cmd="${1:-}"
case "$cmd" in
  new)
    name="${2:-}"
    [ -z "$name" ] && { echo "error: branch name required" >&2; usage 1; }
    dir=$(dir_for "$name")
    [ -e "$dir" ] && { echo "error: worktree already exists at $dir" >&2; exit 1; }

    echo "Fetching origin/main..."
    git -C "$main_root" fetch origin --quiet

    echo "Creating worktree $dir on branch '$name' (off origin/main)..."
    git -C "$main_root" worktree add -b "$name" "$dir" origin/main

    echo ""
    echo "Ready: $dir   [branch $name]"
    echo "Open THIS folder in a new editor window / Claude session and work there."
    echo "Install dev deps with: uv sync"
    ;;
  list)
    git -C "$main_root" worktree list
    ;;
  rm|remove)
    name="${2:-}"
    [ -z "$name" ] && { echo "error: branch name required" >&2; usage 1; }
    dir=$(dir_for "$name")
    git -C "$main_root" worktree remove "$dir"
    echo "Removed $dir. Branch '$name' still exists (delete with: git -C \"$main_root\" branch -d '$name')."
    ;;
  ""|-h|--help|help)
    usage 0
    ;;
  *)
    echo "error: unknown command '$cmd'" >&2
    usage 1
    ;;
esac
