# OpenClaw Docker Setup Guide

Personal Docker setup for running OpenClaw in an isolated container with GitHub CLI and Claude Pro plan authentication.

This guide is designed to be followed by an AI agent assisting a human. Each step clearly marks what the agent can automate vs what requires human input.

## Prerequisites

- Docker Desktop (or Docker Engine) + Docker Compose v2
- At least 2 GB RAM for image build
- A Claude Pro/Max subscription
- A GitHub account with `gh` CLI authenticated on the host

## Secrets inventory

| Secret | How to obtain | Written to |
|--------|--------------|------------|
| `OPENCLAW_GATEWAY_TOKEN` | Agent generates via `openssl rand -hex 32` | `.env`, `~/.openclaw/openclaw.json` |
| `GH_TOKEN` | Human provides (https://github.com/settings/tokens) | `.env` |
| `CLAUDE_OAUTH_TOKEN` | Human runs `claude setup-token` and provides output | `~/.openclaw/agents/main/agent/auth-profiles.json` |
| `TELEGRAM_BOT_TOKEN` | Human creates bot via @BotFather on Telegram | `.env`, `docker-compose.yml`, `~/.openclaw/openclaw.json` |
| `GIT_USER_NAME` | Human provides | `.env` (passed as `GIT_AUTHOR_NAME`/`GIT_COMMITTER_NAME`) |
| `GIT_USER_EMAIL` | Human provides | `.env` (passed as `GIT_AUTHOR_EMAIL`/`GIT_COMMITTER_EMAIL`) |

## Step 1: Fork and clone the repo

**Agent can automate.** No human input needed if `gh` is authenticated.

```bash
gh repo fork openclaw/openclaw --clone=true
cd openclaw
```

If already cloned from upstream, reconfigure remotes:

```bash
git remote rename origin upstream
git remote add origin https://github.com/<your-username>/openclaw.git
```

This keeps `upstream` pointing to the original repo for pulling updates, and `origin` pointing to your fork for pushing customizations.

## Step 2: Create the custom Dockerfile

**Agent can automate.** Write `Dockerfile.custom` to the repo root. This layers tools on top of the base OpenClaw image without modifying the upstream Dockerfile.

```dockerfile
FROM openclaw:local

USER root

# GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      -o /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gh && \
    rm -rf /var/lib/apt/lists/*

# Add more tools below as needed, e.g.:
# RUN apt-get update && apt-get install -y --no-install-recommends python3 ripgrep && rm -rf /var/lib/apt/lists/*

USER node
```

## Step 3: Generate the gateway token

**Agent can automate.** Generate a random 64-character hex token. This value is reused in `.env` and `openclaw.json`.

```bash
openssl rand -hex 32
```

Store the output -- it is needed in Steps 4 and 5.

## Step 4: Create the `.env` file

**Requires human input** for `GH_TOKEN`. The agent writes the file, using the generated gateway token and a placeholder for `GH_TOKEN`.

The `.env` file is gitignored and must never be committed.

```bash
cp .env.example .env
```

Required values:

```env
OPENCLAW_IMAGE=openclaw:custom
OPENCLAW_GATEWAY_TOKEN=<generated in Step 3>
OPENCLAW_GATEWAY_BIND=lan
OPENCLAW_CONFIG_DIR=~/.openclaw
OPENCLAW_WORKSPACE_DIR=~/.openclaw/workspace
GH_TOKEN=<ASK HUMAN: GitHub personal access token>
GIT_USER_NAME=<ASK HUMAN: Git commit author name (e.g. GitHub username)>
GIT_USER_EMAIL=<ASK HUMAN: Git commit email>
```

**Agent instruction:** Do not use `cp .env.example` -- write the `.env` file directly with the values above. Ask the human to provide:
- `GH_TOKEN`: GitHub personal access token. Validate it starts with `ghp_` (classic) or `github_pat_` (fine-grained).
- `GIT_USER_NAME`: their GitHub username or preferred git author name.
- `GIT_USER_EMAIL`: their git commit email.

Also add the GitHub username and email to the `Owner Identity` section of `~/.openclaw/workspace/AGENTS.md` so OpenClaw knows the human's GitHub username for cloning personal repos.

## Step 5: Configure Claude Pro authentication

**Requires human input** for the Claude setup token.

### 5a. Create config directories

**Agent can automate.**

```bash
mkdir -p ~/.openclaw/agents/main/agent ~/.openclaw/workspace
```

### 5b. Obtain the Claude setup token

**Human must run this** on any machine where they are logged into Claude:

```bash
claude setup-token
```

**Agent instruction:** Ask the human to run `claude setup-token` and provide the output. Validate it starts with `sk-ant-oat01-` and is at least 80 characters long.

### 5c. Write the auth profile

**Agent can automate** once the token is provided. Write to `~/.openclaw/agents/main/agent/auth-profiles.json`:

```json
{
  "profiles": {
    "anthropic:manual": {
      "type": "token",
      "provider": "anthropic",
      "token": "<CLAUDE_OAUTH_TOKEN from Step 5b>"
    }
  }
}
```

### 5d. Write the gateway config

**Agent can automate.** Write to `~/.openclaw/openclaw.json`, reusing the gateway token from Step 3:

```json
{
  "gateway": {
    "mode": "local",
    "bind": "lan",
    "auth": {
      "token": "<OPENCLAW_GATEWAY_TOKEN from Step 3>"
    },
    "controlUi": {
      "allowedOrigins": ["http://localhost:18789", "http://127.0.0.1:18789"]
    }
  },
  "auth": {
    "profiles": {
      "anthropic:manual": {
        "provider": "anthropic",
        "mode": "token"
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "anthropic/claude-sonnet-4-6"
      },
    }
  },
  "tools": {
    "exec": {
      "security": "full"
    }
  }
}
```

`tools.exec.security: "full"` auto-approves all command execution without prompting. This is safe because the Docker container is isolated -- it can only access the workspace and config volumes, not the host filesystem. Access is further locked by `dmPolicy: "allowlist"` on Telegram.

## Step 6: Update `docker-compose.yml`

**Agent can automate.** Add the following to both `openclaw-gateway` and `openclaw-cli` services in `docker-compose.yml`:

- In the `environment` block: `GH_TOKEN: ${GH_TOKEN:-}` and `TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}`
The container only has access to `~/.openclaw` (config) and `~/.openclaw/workspace` (coding projects). The rest of the host filesystem is inaccessible. Use the workspace folder to clone repos and work on projects.

### Volume access summary

| Container path | Host path | Purpose |
|---|---|---|
| `/home/node/.openclaw` | `~/.openclaw` | Config, auth, sessions |
| `/home/node/.openclaw/workspace` | `~/.openclaw/workspace` | Coding projects |

## Step 7: Build and start

**Agent can automate.**

```bash
# Build the base OpenClaw image
docker build -t openclaw:local -f Dockerfile .

# Layer custom tools on top
docker build -t openclaw:custom -f Dockerfile.custom .

# Start the gateway
OPENCLAW_IMAGE=openclaw:custom docker compose up -d openclaw-gateway
```

## Step 8: Verify

**Agent can automate.** Wait 8-10 seconds after `docker compose up` for the gateway to initialize, then run these checks:

```bash
# Wait for gateway to initialize
sleep 10

# Liveness probe (expect {"ok":true,"status":"live"})
curl -fsS http://127.0.0.1:18789/healthz

# Readiness probe (expect {"ready":true})
curl -fsS http://127.0.0.1:18789/readyz

# Model auth status
OPENCLAW_IMAGE=openclaw:custom docker compose run --rm -T openclaw-cli models status
```

**Agent instruction:** If the health check returns a connection error, wait another 10 seconds and retry (up to 3 attempts). Check `models status` output for:
- `anthropic` should show `profiles=1 (... token=1 ...)` -- if it shows "Missing auth", the auth-profiles.json path is wrong (see Troubleshooting).
- `github-copilot` should show `env=ghp_...` -- if missing, `GH_TOKEN` is not set in `.env`.
If errors appear, check logs with `docker compose logs openclaw-gateway | tail -40`.

## Step 9: Open the Control UI and approve the browser device

**Agent can partially automate.** The browser must be paired before the human can use the Control UI.

### 9a. Get the dashboard URL with embedded token

```bash
docker compose run --rm -T openclaw-cli dashboard --no-open
```

This outputs a URL like `http://127.0.0.1:18789/#token=<GATEWAY_TOKEN>`. Give this URL to the human to open in their browser.

### 9b. Approve the browser pairing request

After the human opens the URL, a pairing request is created. The agent must approve it:

```bash
# List pending pairing requests
docker compose run --rm -T openclaw-cli devices list

# Approve the pending request (use the Request ID from the Pending table)
docker compose run --rm -T openclaw-cli devices approve <request-id>
```

**Agent instruction:** First, ask the human to confirm they have opened the dashboard URL in their browser. Then run `devices list`, find the row in the "Pending" table, extract the `Request` UUID, and run `devices approve <uuid>`. If no pending requests appear, ask the human to refresh the browser page and retry after a few seconds. Once approved, tell the human to refresh the page -- they should now have full access.

## Step 10: Use the CLI

```bash
OPENCLAW_IMAGE=openclaw:custom docker compose run --rm openclaw-cli channels status
OPENCLAW_IMAGE=openclaw:custom docker compose run --rm openclaw-cli models status
```

**Tip:** To avoid repeating `OPENCLAW_IMAGE=openclaw:custom`, add it to your `.env` file:

```env
OPENCLAW_IMAGE=openclaw:custom
```

## Step 11: Add Telegram channel (optional)

**Requires human input** for the bot token.

### 11a. Create a Telegram bot

**Human must do this** in Telegram:

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a display name (e.g. "My OpenClaw Bot")
4. Choose a username ending in `bot` (e.g. `my_openclaw_bot`)
5. BotFather replies with a token like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

**Agent instruction:** Ask the human to create a bot via @BotFather and provide the token. Validate it matches the pattern `<digits>:<alphanumeric string>`.

### 11b. Configure Telegram

**Agent can automate** once the token is provided.

1. Add `TELEGRAM_BOT_TOKEN=<token>` to `.env`
2. Add `TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}` to the `environment` block of both services in `docker-compose.yml`
3. Restart the gateway: `docker compose down && docker compose up -d openclaw-gateway`
4. Wait 10 seconds, then register the channel:

```bash
docker compose run --rm -T openclaw-cli channels add --channel telegram --token "<token>"
```

5. Verify:

```bash
docker compose run --rm -T openclaw-cli channels status
```

Expected output should show: `Telegram default: enabled, configured, running, mode:polling`

### 11c. Enable exec approvals and lock access

**Agent can automate** once the human's Telegram user ID is known (provided in the pairing message).

Add these fields to `channels.telegram` in `~/.openclaw/openclaw.json`:

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "botToken": "<token>",
      "dmPolicy": "allowlist",
      "allowFrom": [<TELEGRAM_USER_ID>],
      "execApprovals": {
        "enabled": true,
        "target": "dm"
      }
    }
  }
}
```

- `dmPolicy: "allowlist"` + `allowFrom` locks the bot to only the human's Telegram user ID
- `execApprovals.enabled: true` lets the human approve/deny command execution directly in Telegram DMs
- `target: "dm"` sends approval prompts to the human's DM (not a group)

**Agent instruction:** The human's Telegram user ID appears in the bot's first "access not configured" reply. Extract it from there or ask the human. Restart the gateway after updating the config.

### 11d. Approve the Telegram user

The first time a user messages the bot, OpenClaw replies with a pairing code. The agent must approve it:

```bash
docker compose run --rm -T openclaw-cli pairing approve telegram <PAIRING_CODE>
```

**Agent instruction:** Ask the human to send any message to the bot on Telegram. The bot will reply with a pairing code (e.g. `3655FQUC`). Run the approve command with that code. After approval, tell the human to resend their message.

The human can now message the bot on Telegram and OpenClaw will respond.

## Step 12: Enable voice message transcription (optional)

**Requires human input** for the Deepgram API key.

### 12a. Get a Deepgram API key

**Human must do this** at https://console.deepgram.com (free tier with $200 credit).

### 12b. Configure Deepgram

**Agent can automate** once the key is provided.

1. Add `DEEPGRAM_API_KEY=<key>` to `.env`
2. Add `DEEPGRAM_API_KEY: ${DEEPGRAM_API_KEY:-}` to the `environment` block of both services in `docker-compose.yml`
3. Add `ffmpeg` to `Dockerfile.custom` (needed for audio format conversion)
4. Enable the Deepgram plugin and audio config in `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "deepgram": {
        "enabled": true
      }
    }
  },
  "tools": {
    "media": {
      "audio": {
        "enabled": true,
        "models": [
          { "provider": "deepgram", "model": "nova-3" }
        ],
        "providerOptions": {
          "deepgram": {
            "detect_language": true,
            "punctuate": true,
            "smart_format": true
          }
        }
      }
    }
  }
}
```

5. Rebuild the custom image (`docker build -t openclaw:custom -f Dockerfile.custom .`)
6. Recreate the container (`docker compose down && docker compose up -d openclaw-gateway`)

**Important:** The Deepgram plugin must be explicitly enabled via `plugins.entries.deepgram.enabled: true`. The audio config alone is not enough.

**Note:** `detect_language: true` enables automatic French/English (and other languages) detection.

## Day-to-day commands

```bash
# Start
OPENCLAW_IMAGE=openclaw:custom docker compose up -d openclaw-gateway

# Stop
docker compose down

# View logs
docker compose logs -f openclaw-gateway

# Rebuild after upstream updates
git fetch upstream
git merge upstream/main
docker build -t openclaw:local -f Dockerfile .
docker build -t openclaw:custom -f Dockerfile.custom .
```

## Adding more tools to the container

Edit `Dockerfile.custom` and add install commands between `USER root` and `USER node`, then rebuild:

```bash
docker build -t openclaw:custom -f Dockerfile.custom .
```

For tools available as standard APT packages, the base Dockerfile also supports a build arg:

```bash
docker build -t openclaw:local \
  --build-arg OPENCLAW_DOCKER_APT_PACKAGES="python3 wget jq" \
  -f Dockerfile .
```

## Troubleshooting

### Config invalid: Unrecognized key "auth" under agents.defaults

Auth profiles belong at the top-level `auth.profiles` key in `openclaw.json`, not under `agents.defaults.auth`. See the config in Step 5d.

### Auth profile not found / "Missing auth - anthropic"

The gateway looks for `auth-profiles.json` in `~/.openclaw/agents/main/agent/`, not `~/.openclaw/agents/default/`. Ensure the file is at the correct path.

### Connection reset on health check right after start

The gateway needs a few seconds to initialize. Wait 8-10 seconds after `docker compose up` before probing `/healthz`.

### Config invalid: Unrecognized key under agents.defaults

`openclaw.json` is strict about its schema. Common mistakes:
- `elevated` belongs under `tools.exec.security`, not `agents.defaults.elevated`
- `auth.profiles` is a top-level key, not under `agents.defaults.auth`

If the gateway crash-loops with "Config invalid", check `docker compose logs openclaw-gateway` for the exact rejected key.

### New env vars not picked up after restart

`docker compose restart` reuses the existing container -- it does NOT re-read `.env`. You must recreate the container:

```bash
docker compose down && docker compose up -d openclaw-gateway
```

### GH_TOKEN picked up as github-copilot provider

This is expected. OpenClaw auto-detects `GH_TOKEN` as a GitHub Copilot credential. It works alongside the Anthropic auth profile.

## File overview

| File | Contains secrets? | Committed? | Purpose |
|------|:-:|:-:|---------|
| `Dockerfile` | No | Yes | Base OpenClaw image (upstream) |
| `Dockerfile.custom` | No | Yes | Custom tool additions (gh, etc.) |
| `docker-compose.yml` | No | Yes | Service definitions (gateway + cli) |
| `.env` | **Yes** | **No** (gitignored) | Runtime secrets and config |
| `~/.openclaw/openclaw.json` | **Yes** (gateway token) | **No** (outside repo) | Gateway and agent config |
| `~/.openclaw/agents/main/agent/auth-profiles.json` | **Yes** (Claude token) | **No** (outside repo) | Claude auth token |
