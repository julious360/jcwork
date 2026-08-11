#!/usr/bin/env bash
# Installs the skills in this directory into ~/.claude/skills/, where Claude Code
# discovers them by scanning each <name>/SKILL.md for YAML frontmatter.
#
# Why this exists: these skills previously lived only in ~/.claude/skills on one
# machine — not version-controlled, not portable, gone on a container reset or a new
# machine. This directory is the versioned source of truth; install.sh is how it
# reaches a machine's live skills directory.
#
# Usage:
#   toolkit/skills/install.sh              # copy every skill here into ~/.claude/skills/
#   toolkit/skills/install.sh brand-identity ui-verify   # install specific skills only
#
# Existing skills at the destination with the same name are overwritten — this
# directory is meant to be the source of truth, so an install is expected to win.
# If you've edited a skill directly under ~/.claude/skills/ and want to keep those
# edits, copy the change back into this directory first (or run the reverse:
# `cp -r ~/.claude/skills/<name> toolkit/skills/`) before installing.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

mkdir -p "$DEST"

targets=("$@")
if [ ${#targets[@]} -eq 0 ]; then
  for dir in "$HERE"/*/; do
    name="$(basename "$dir")"
    [ -f "$dir/SKILL.md" ] && targets+=("$name")
  done
fi

for name in "${targets[@]}"; do
  src="$HERE/$name"
  if [ ! -f "$src/SKILL.md" ]; then
    echo "skip: $name (no SKILL.md at $src)" >&2
    continue
  fi
  rm -rf "${DEST:?}/${name:?}"
  cp -r "$src" "$DEST/$name"
  echo "installed: $name -> $DEST/$name"
done

echo
echo "Done. Skills are discovered by Claude Code scanning $DEST/*/SKILL.md — no"
echo "restart should be required, but if a skill doesn't show as available, check"
echo "/hooks or start a new session."
