#!/bin/sh
# Custom entrypoint: seed spec-kit skills and agent workspace into the
# Docker volumes on container startup, then exec the original command.
#
# - Skills go into ~/.claude/skills/ (claude-credentials volume) so
#   /speckit-* slash commands are globally available in Claude Code.
# - The speckit agent workspace is seeded into ~/.openclaw/workspace-speckit/
#   (openclaw config volume) with an AGENTS.md that instructs the agent
#   to follow the spec-driven development workflow.

SKILLS_SRC="/opt/speckit-skills"
SKILLS_DST="/home/node/.claude/skills"
WORKSPACE_SRC="/opt/speckit-workspace"
WORKSPACE_DST="/home/node/.openclaw/workspace-speckit"

# Seed spec-kit skills (skip already-existing ones to preserve customizations)
if [ -d "$SKILLS_SRC" ]; then
  mkdir -p "$SKILLS_DST"
  for skill_dir in "$SKILLS_SRC"/*/; do
    skill_name="$(basename "$skill_dir")"
    if [ ! -d "$SKILLS_DST/$skill_name" ]; then
      cp -r "$skill_dir" "$SKILLS_DST/$skill_name"
    fi
  done
fi

# Seed speckit agent workspace (only if it doesn't exist yet)
if [ -d "$WORKSPACE_SRC" ] && [ ! -f "$WORKSPACE_DST/AGENTS.md" ]; then
  mkdir -p "$WORKSPACE_DST"
  cp -r "$WORKSPACE_SRC"/* "$WORKSPACE_DST/" 2>/dev/null || true
fi

exec "$@"
