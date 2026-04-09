# OpenClaw Docker Setup Guide

Personal Docker setup for running OpenClaw in an isolated container. Supports two provider modes: local Ollama (free) or Anthropic Claude (paid).

This guide is designed to be followed by an AI agent assisting a human. Each step clearly marks what the agent can automate vs what requires human input.

## Provider choice

**Agent must ask the human before starting:**

> Which model provider would you like to use?
>
> **A) Local Ollama (free, private)** -- Runs LLM inference on your Mac via Ollama. Requires Apple Silicon and enough RAM (24 GB+ recommended). Models: Llama 3.1 8B (main) + Qwen 3 14B (coding subagent). Zero API cost.
>
> **B) Anthropic Claude (paid, cloud)** -- Uses Claude via API key or setup token. Requires an Anthropic API key or Claude Pro/Max subscription. Better quality but costs money per request.

- If the human chooses **A (Ollama)**: follow this guide as written.
- If the human chooses **B (Anthropic)**: skip Step 2 (Ollama install), and in Step 6 replace the `models.providers.ollama` block with an `auth.profiles` block pointing to Anthropic. Set `agents.defaults.model.primary` to `anthropic/claude-sonnet-4-6`. The human will need to run `claude setup-token` and write the output to `~/.openclaw/agents/main/agent/auth-profiles.json`. Docker Desktop can keep the default 8 GB RAM since Ollama is not needed.

## Prerequisites

- Docker Desktop (or Docker Engine) + Docker Compose v2
- If using Ollama: Docker Desktop configured with **4 GB RAM** (not the default 8 GB -- Ollama needs the remaining host memory)
- If using Ollama: macOS with Apple Silicon (for Metal GPU acceleration)
- A GitHub account with `gh` CLI authenticated on the host

## Architecture overview

### [Ollama mode]

```
┌──────────────────────────────────┐
│         macOS Host               │
│                                  │
│  Ollama (brew service)           │
│  ├─ llama3.1:8b    (main agent)  │
│  └─ qwen3:14b      (subagent)   │
│  Bound to 127.0.0.1:11434       │
│                                  │
│  ┌────────────────────────────┐  │
│  │     Docker (4 GB VM)       │  │
│  │                            │  │
│  │  openclaw-gateway          │  │
│  │  ├─ port 18789 (gateway)   │  │
│  │  └─ port 18790 (bridge)    │  │
│  │                            │  │
│  │  whisper (transcription)   │  │
│  │  └─ port 8000              │  │
│  │                            │  │
│  │  → host.docker.internal    │  │
│  │    reaches Ollama on host  │  │
│  └────────────────────────────┘  │
└──────────────────────────────────┘
```

### [Anthropic mode]

```
┌──────────────────────────────────┐
│         macOS Host               │
│                                  │
│  ┌────────────────────────────┐  │
│  │     Docker (8 GB VM)       │  │
│  │                            │  │
│  │  openclaw-gateway          │  │
│  │  ├─ port 18789 (gateway)   │  │
│  │  └─ port 18790 (bridge)    │  │
│  │  └─ → api.anthropic.com   │  │
│  │                            │  │
│  │  whisper (transcription)   │  │
│  │  └─ port 8000              │  │
│  └────────────────────────────┘  │
└──────────────────────────────────┘
```

## Secrets inventory

| Secret                   | How to obtain                                       | Written to                                                  | Required for    |
| ------------------------ | --------------------------------------------------- | ----------------------------------------------------------- | --------------- |
| `OPENCLAW_GATEWAY_TOKEN` | Agent generates via `openssl rand -hex 32`          | `.env`, `~/.openclaw/openclaw.json`                         | Both            |
| `GH_TOKEN`               | Human provides (https://github.com/settings/tokens) | `.env`                                                      | Both            |
| `CLAUDE_OAUTH_TOKEN`     | Human runs `claude setup-token`                     | `~/.openclaw/agents/main/agent/auth-profiles.json`          | Anthropic only  |
| `TELEGRAM_BOT_TOKEN`     | Human creates bot via @BotFather on Telegram        | `.env`, `~/.openclaw/openclaw.json`                         | Both (optional) |
| `GIT_USER_NAME`          | Human provides                                      | `.env` (passed as `GIT_AUTHOR_NAME`/`GIT_COMMITTER_NAME`)   | Both            |
| `GIT_USER_EMAIL`         | Human provides                                      | `.env` (passed as `GIT_AUTHOR_EMAIL`/`GIT_COMMITTER_EMAIL`) | Both            |

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

## Step 2: Install and configure Ollama on the host [Ollama only]

**Skip this step if using Anthropic.**

**Agent can automate.** Ollama runs natively on macOS (not in Docker) for Metal GPU acceleration.

### 2a. Install Ollama

```bash
brew install ollama
brew services start ollama
```

### 2b. Pull the models

```bash
ollama pull llama3.1:8b        # Main agent model (~5 GB)
ollama pull qwen3:14b          # Coding subagent model (~9.3 GB)
ollama pull nomic-embed-text   # Embedding model for memory (~274 MB)
```

### 2c. Configure persistent keep-alive

By default Ollama unloads models after 5 minutes of inactivity. Reloading takes 30-60 seconds and causes gateway timeouts. Set `OLLAMA_KEEP_ALIVE=-1` to keep models in memory permanently.

Edit the launchd plist (**do not use `brew services restart`** afterward -- it overwrites the plist):

```bash
# Open the plist
nano ~/Library/LaunchAgents/homebrew.mxcl.ollama.plist
```

Add this key inside the `<dict>` under `EnvironmentVariables`:

```xml
<key>OLLAMA_KEEP_ALIVE</key>
<string>-1</string>
```

Reload the service (without overwriting the plist):

```bash
launchctl kickstart -k gui/$(id -u)/homebrew.mxcl.ollama
```

### 2d. Verify

```bash
# Check Ollama is listening on localhost only (security)
lsof -iTCP:11434 -sTCP:LISTEN -P -n
# Expected: 127.0.0.1:11434

# Preload the model and test inference
curl -s http://127.0.0.1:11434/api/chat \
  -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"Say hi"}],"stream":false}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['message']['content'])"

# Check model stays loaded
curl -s http://127.0.0.1:11434/api/ps \
  | python3 -c "import sys,json; [print(f\"{m['name']}: loaded\") for m in json.load(sys.stdin)['models']]"
```

**Security note:** Ollama binds to `127.0.0.1` (localhost only) by default. Do not change this -- the Docker containers reach it via `host.docker.internal` which maps to the host's loopback on Docker Desktop.

### 2e. Important: restarting Ollama

Never use `brew services restart ollama` -- it overwrites the plist and removes `OLLAMA_KEEP_ALIVE`. Instead use:

```bash
launchctl kickstart -k gui/$(id -u)/homebrew.mxcl.ollama
```

## Step 2B: Configure Claude Pro authentication [Anthropic only]

**Skip this step if using Ollama.**

**Requires human input** for the Claude setup token.

### 2B-a. Obtain the Claude setup token

**Human must run this** on any machine where they are logged into Claude:

```bash
claude setup-token
```

**Agent instruction:** Ask the human to run `claude setup-token` and provide the output. Validate it starts with `sk-ant-oat01-` and is at least 80 characters long.

### 2B-b. Write the auth profile

**Agent can automate** once the token is provided. Write to `~/.openclaw/agents/main/agent/auth-profiles.json`:

```bash
mkdir -p ~/.openclaw/agents/main/agent
```

```json
{
  "version": 1,
  "profiles": {
    "anthropic:manual": {
      "type": "token",
      "provider": "anthropic",
      "token": "<CLAUDE_OAUTH_TOKEN from Step 2B-a>"
    }
  }
}
```

## Step 3: Create the custom Dockerfile

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

# ffmpeg for audio/video transcription
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Add more tools below as needed, e.g.:
# RUN apt-get update && apt-get install -y --no-install-recommends ripgrep && rm -rf /var/lib/apt/lists/*

USER node
```

## Step 4: Generate the gateway token

**Agent can automate.** Generate a random 64-character hex token. This value is reused in `.env` and `openclaw.json`.

```bash
openssl rand -hex 32
```

Store the output -- it is needed in Steps 5 and 6.

## Step 5: Create the `.env` file

**Requires human input** for `GH_TOKEN`. The agent writes the file, using the generated gateway token and a placeholder for `GH_TOKEN`.

The `.env` file is gitignored and must never be committed.

Required values (common to both modes):

```env
# Docker image
OPENCLAW_IMAGE=openclaw:custom

# Gateway
OPENCLAW_GATEWAY_TOKEN=<generated in Step 4>
OPENCLAW_GATEWAY_BIND=lan

# Docker paths (used by docker-compose.yml)
OPENCLAW_CONFIG_DIR=~/.openclaw
OPENCLAW_WORKSPACE_DIR=~/.openclaw/workspace

# GitHub CLI
GH_TOKEN=<ASK HUMAN: GitHub personal access token>

# Git identity
GIT_USER_NAME=<ASK HUMAN: Git commit author name>
GIT_USER_EMAIL=<ASK HUMAN: Git commit email>

# Audio transcription (local Whisper via faster-whisper-server)
WHISPER_MODEL=small
OPENAI_API_KEY=sk-local

# Channels
TELEGRAM_BOT_TOKEN=<ASK HUMAN: Telegram bot token, optional>
```

**[Ollama only]** -- no additional env vars needed. Ollama runs on the host with no API key.

**[Anthropic only]** -- add this line (the token is stored in auth-profiles.json, not here; this is for reference only):

```env
# Anthropic token stored in ~/.openclaw/agents/main/agent/auth-profiles.json (see Step 2B)
```

**Agent instruction:** Do not use `cp .env.example` -- write the `.env` file directly with the values above. Ask the human to provide:

- `GH_TOKEN`: GitHub personal access token. Validate it starts with `ghp_` (classic) or `github_pat_` (fine-grained).
- `GIT_USER_NAME`: their GitHub username or preferred git author name.
- `GIT_USER_EMAIL`: their git commit email.

Also add the GitHub username and email to the `Owner Identity` section of `~/.openclaw/workspace/AGENTS.md` so OpenClaw knows the human's GitHub username for cloning personal repos.

## Step 6: Write the gateway config

**Agent can automate.** Write to `~/.openclaw/openclaw.json`, reusing the gateway token from Step 4:

```bash
mkdir -p ~/.openclaw/agents/main/agent ~/.openclaw/workspace
```

### [Ollama mode] openclaw.json

```json
{
  "gateway": {
    "mode": "local",
    "bind": "lan",
    "auth": {
      "token": "<OPENCLAW_GATEWAY_TOKEN from Step 4>"
    },
    "controlUi": {
      "allowedOrigins": ["http://localhost:18789", "http://127.0.0.1:18789"]
    }
  },
  "models": {
    "providers": {
      "ollama": {
        "baseUrl": "http://host.docker.internal:11434",
        "api": "ollama",
        "apiKey": "ollama-local",
        "models": [
          {
            "id": "llama3.1:8b",
            "name": "Llama 3.1 8B",
            "reasoning": false,
            "input": ["text"],
            "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
            "contextWindow": 32768,
            "maxTokens": 8192
          },
          {
            "id": "qwen3:14b",
            "name": "Qwen 3 14B",
            "reasoning": false,
            "input": ["text"],
            "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
            "contextWindow": 32768,
            "maxTokens": 8192
          }
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "ollama/llama3.1:8b"
      },
      "subagents": {
        "model": "ollama/qwen3:14b"
      },
      "heartbeat": {
        "every": "0m"
      },
      "llm": {
        "idleTimeoutSeconds": 300
      },
      "timeoutSeconds": 900,
      "memorySearch": {
        "enabled": true,
        "provider": "ollama",
        "model": "nomic-embed-text",
        "remote": {
          "baseUrl": "http://host.docker.internal:11434"
        }
      }
    }
  },
  "plugins": {
    "entries": {
      "deepgram": { "enabled": false },
      "ollama": { "enabled": true },
      "acpx": {
        "enabled": true,
        "config": {
          "permissionMode": "approve-all",
          "timeoutSeconds": 600
        }
      }
    }
  },
  "tools": {
    "exec": {
      "security": "full"
    },
    "media": {
      "audio": {
        "enabled": true,
        "models": [
          {
            "provider": "openai",
            "model": "small",
            "baseUrl": "http://whisper:8000/v1"
          }
        ]
      }
    }
  }
}
```

- `models.providers.ollama.baseUrl` uses `host.docker.internal` to reach the host's Ollama service from inside Docker.
- `agents.defaults.subagents.model` routes coding tasks spawned via `sessions_spawn` to Qwen 3 14B.
- `agents.defaults.heartbeat.every: "0m"` disables heartbeat. Periodic heartbeats are too slow and error-prone with local models (can cause runaway agent loops and context overflow on small models).
- `agents.defaults.llm.idleTimeoutSeconds: 300` releases model connections after 5 minutes of inactivity.
- `plugins.entries.acpx` enables the embedded ACP runtime backend for subagent support. `permissionMode: "approve-all"` lets subagents read/write freely (required for headless Docker -- no one is present to approve manually). `timeoutSeconds: 600` caps subagent turns at 10 minutes (local models on Apple Silicon need more time than cloud APIs).
- `plugins.entries.ollama` enables the Ollama provider plugin for model discovery.
- `plugins.entries.deepgram` is disabled (not needed when using local Whisper).
- `agents.defaults.memorySearch` uses `nomic-embed-text` via Ollama for vector memory search (conversation recall, session context). Without this, memory falls back to OpenAI embeddings which requires a paid API key.

### [Anthropic mode] openclaw.json

```json
{
  "gateway": {
    "mode": "local",
    "bind": "lan",
    "auth": {
      "token": "<OPENCLAW_GATEWAY_TOKEN from Step 4>"
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
      "timeoutSeconds": 300
    }
  },
  "tools": {
    "exec": {
      "security": "full"
    },
    "media": {
      "audio": {
        "enabled": true,
        "models": [
          {
            "provider": "openai",
            "model": "small",
            "baseUrl": "http://whisper:8000/v1"
          }
        ]
      }
    }
  }
}
```

- `auth.profiles` references the token written in Step 2B-b.

### Common notes (both modes)

- `tools.exec.security: "full"` auto-approves all command execution without prompting. This is safe because the Docker container is isolated -- it can only access the workspace and config volumes, not the host filesystem.

## Step 7: Ensure `docker-compose.yml` has host access [Ollama only]

**Skip this step if using Anthropic.** The gateway does not need host access when using cloud APIs.

**Agent can automate.** Both `openclaw-gateway` and `openclaw-cli` services need `extra_hosts` to resolve `host.docker.internal`:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Add this to both services. Docker Desktop on macOS usually provides this by default, but explicit is safer.

## Step 8: Build and start

**Agent can automate.**

```bash
# Build the base OpenClaw image
docker build -t openclaw:local -f Dockerfile .

# Layer custom tools on top
docker build -t openclaw:custom -f Dockerfile.custom .

# Start the gateway (pulls Whisper image on first run)
docker compose up -d openclaw-gateway
```

## Step 9: Verify

**Agent can automate.** Wait 15-20 seconds after `docker compose up` for the gateway to initialize and Whisper to become healthy.

```bash
# Wait for gateway to initialize
sleep 20

# Liveness probe (expect {"ok":true,"status":"live"})
curl -fsS http://127.0.0.1:18789/healthz

# Readiness probe (expect {"ready":true})
curl -fsS http://127.0.0.1:18789/readyz

# Check gateway logs for model confirmation
docker logs openclaw-openclaw-gateway-1 2>&1 | grep "agent model"
# Expected [Ollama]: agent model: ollama/llama3.1:8b
# Expected [Anthropic]: agent model: anthropic/claude-sonnet-4-6

# Model auth status [Anthropic only]
docker compose run --rm -T openclaw-cli models status
# Expected: anthropic should show profiles=1 (... token=1 ...)

# Test inference from container [Ollama only]
docker exec openclaw-openclaw-gateway-1 node -e "
fetch('http://host.docker.internal:11434/api/chat', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({model:'llama3.1:8b', messages:[{role:'user',content:'Say hi'}], stream:false})
}).then(r => r.json()).then(d => console.log(d.message.content)).catch(e => console.error('FAILED:', e.message));
"
```

**Agent instruction [Ollama]:** If the inference test fails, check:

1. Ollama is running on the host: `brew services info ollama`
2. Model is loaded: `curl -s http://127.0.0.1:11434/api/ps`
3. If model is not loaded, preload it: `curl -s http://127.0.0.1:11434/api/chat -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"hi"}],"stream":false,"keep_alive":-1}'`

**Agent instruction [Anthropic]:** If `models status` shows "Missing auth - anthropic", the auth-profiles.json path is wrong. Ensure it is at `~/.openclaw/agents/main/agent/auth-profiles.json` (not `~/.openclaw/agents/default/`).

## Step 10: Open the Control UI and approve the browser device

**Agent can partially automate.** The browser must be paired before the human can use the Control UI.

### 10a. Get the dashboard URL with embedded token

```bash
docker compose run --rm -T openclaw-cli dashboard --no-open
```

This outputs a URL like `http://127.0.0.1:18789/#token=<GATEWAY_TOKEN>`. Give this URL to the human to open in their browser.

### 10b. Approve the browser pairing request

After the human opens the URL, a pairing request is created. The agent must approve it:

```bash
# List pending pairing requests
docker compose run --rm -T openclaw-cli devices list

# Approve the pending request (use the Request ID from the Pending table)
docker compose run --rm -T openclaw-cli devices approve <request-id>
```

**Agent instruction:** First, ask the human to confirm they have opened the dashboard URL in their browser. Then run `devices list`, find the row in the "Pending" table, extract the `Request` UUID, and run `devices approve <uuid>`. If no pending requests appear, ask the human to refresh the browser page and retry after a few seconds. Once approved, tell the human to refresh the page -- they should now have full access.

## Step 11: Use the CLI

```bash
docker compose run --rm -T openclaw-cli channels status
docker compose run --rm -T openclaw-cli models status
```

**Tip:** `OPENCLAW_IMAGE=openclaw:custom` is already in `.env`, so `docker compose` picks it up automatically.

## Step 12: Add Telegram channel (optional)

**Requires human input** for the bot token.

### 12a. Create a Telegram bot

**Human must do this** in Telegram:

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a display name (e.g. "My OpenClaw Bot")
4. Choose a username ending in `bot` (e.g. `my_openclaw_bot`)
5. BotFather replies with a token like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

**Agent instruction:** Ask the human to create a bot via @BotFather and provide the token. Validate it matches the pattern `<digits>:<alphanumeric string>`.

### 12b. Configure Telegram

**Agent can automate** once the token is provided.

1. Add `TELEGRAM_BOT_TOKEN=<token>` to `.env`
2. Restart the gateway: `docker compose up -d openclaw-gateway --force-recreate`
3. Wait 15 seconds, then register the channel:

```bash
docker compose run --rm -T openclaw-cli channels add --channel telegram --token "<token>"
```

4. Verify:

```bash
docker compose run --rm -T openclaw-cli channels status
```

Expected output should show: `Telegram default: enabled, configured, running, mode:polling`

### 12c. Enable exec approvals and lock access

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

**Agent instruction:** The human's Telegram user ID appears in the bot's first "access not configured" reply. Extract it from there or ask the human. Recreate the gateway after updating the config: `docker compose up -d openclaw-gateway --force-recreate`.

### 12d. Approve the Telegram user

The first time a user messages the bot, OpenClaw replies with a pairing code. The agent must approve it:

```bash
docker compose run --rm -T openclaw-cli pairing approve telegram <PAIRING_CODE>
```

**Agent instruction:** Ask the human to send any message to the bot on Telegram. The bot will reply with a pairing code (e.g. `3655FQUC`). Run the approve command with that code. After approval, tell the human to resend their message.

The human can now message the bot on Telegram and OpenClaw will respond.

## Step 13: Enable voice message transcription (optional)

**Agent can automate.** No external API key needed -- transcription runs locally via a self-hosted Whisper container.

### 13a. Whisper Docker image

The `whisper/` directory contains a custom Docker image that runs [faster-whisper](https://github.com/SYSTRAN/faster-whisper) behind a minimal FastAPI server exposing an OpenAI-compatible `/v1/audio/transcriptions` endpoint.

Available models (set via `WHISPER_MODEL` in `.env`):

| Model       | Size   | RAM     | Speed (30s audio) | Quality                |
| ----------- | ------ | ------- | ----------------- | ---------------------- |
| `tiny`      | 75 MB  | ~150 MB | ~2s               | Basic                  |
| `base`      | 140 MB | ~300 MB | ~3s               | Decent                 |
| **`small`** | 460 MB | ~1 GB   | **~5s**           | **Good (recommended)** |
| `medium`    | 1.5 GB | ~3 GB   | ~12s              | Very good              |
| `large-v3`  | 3 GB   | ~6 GB   | ~25s              | Excellent              |

The model is downloaded automatically on first transcription request.

### 13b. Configure Whisper

**Agent can automate.** If you followed Step 5, the `.env` already contains `WHISPER_MODEL=small` and `OPENAI_API_KEY=sk-local`. The audio transcription config is already in `openclaw.json` from Step 6.

The `whisper` service is defined in `docker-compose.yml` and the gateway waits for it to be healthy before starting.

### 13c. Verify

```bash
# Check Whisper is healthy
curl -s http://localhost:8000/health

# Check Whisper is reachable from the gateway
docker compose exec openclaw-gateway sh -c 'curl -sf http://whisper:8000/health'
```

Send a voice message on Telegram -- you should see `POST /v1/audio/transcriptions 200 OK` in `docker compose logs whisper`.

## Day-to-day commands

```bash
# Start
docker compose up -d openclaw-gateway

# Stop
docker compose down

# View logs
docker compose logs -f openclaw-gateway

# Rebuild after upstream updates
git fetch upstream
git merge upstream/main
docker build -t openclaw:local -f Dockerfile .
docker build -t openclaw:custom -f Dockerfile.custom .
docker compose up -d openclaw-gateway --force-recreate
```

### [Ollama only] day-to-day commands

```bash
# Restart Ollama (without overwriting config)
launchctl kickstart -k gui/$(id -u)/homebrew.mxcl.ollama

# Check loaded Ollama models
curl -s http://127.0.0.1:11434/api/ps | python3 -c "import sys,json; [print(f\"{m['name']}: loaded\") for m in json.load(sys.stdin)['models']]"

# Preload model after reboot
curl -s http://127.0.0.1:11434/api/chat \
  -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"hi"}],"stream":false,"keep_alive":-1}' > /dev/null
```

## Memory budget [Ollama mode] (24 GB Mac)

| Component                     | RAM          |
| ----------------------------- | ------------ |
| macOS + system                | ~6 GB        |
| Docker VM (gateway + whisper) | 4 GB         |
| Ollama llama3.1:8b            | ~5 GB        |
| Ollama qwen3:14b              | ~9.3 GB      |
| Ollama nomic-embed-text       | ~0.3 GB      |
| **Total**                     | **~24.6 GB** |

**Important:** With both models loaded, a 24 GB Mac is at capacity. Set Docker Desktop to **4 GB RAM** in Settings > Resources. The default (~8 GB) leaves too little memory for Ollama. Only one model is active at a time (Ollama swaps models as needed), but if both are loaded simultaneously, expect memory pressure. Consider using `ollama stop qwen3:14b` when not needed to free ~9 GB.

## Memory budget [Anthropic mode]

No special memory requirements. Docker Desktop can use the default 8 GB. No local model inference.

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

### Auth profile not found / "Missing auth - anthropic" [Anthropic only]

The gateway looks for `auth-profiles.json` in `~/.openclaw/agents/main/agent/`, not `~/.openclaw/agents/default/`. Ensure the file is at the correct path.

### Ollama inference times out / gateway returns "Request timed out" [Ollama only]

1. Check if the model is loaded: `curl -s http://127.0.0.1:11434/api/ps`
2. If empty, preload it: `curl -s http://127.0.0.1:11434/api/chat -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"hi"}],"stream":false,"keep_alive":-1}'`
3. Check memory pressure: `memory_pressure` -- if "free pages" is very low, reduce Docker RAM or use a smaller model
4. After a reboot, the model needs to be loaded on first request (~30-60s). Send a warmup request or use the preload command above.

### Ollama KEEP_ALIVE resets after brew upgrade [Ollama only]

`brew upgrade ollama` may overwrite the launchd plist. After upgrading, re-add `OLLAMA_KEEP_ALIVE` to `~/Library/LaunchAgents/homebrew.mxcl.ollama.plist` and reload with `launchctl kickstart -k gui/$(id -u)/homebrew.mxcl.ollama`.

### Config invalid: Unrecognized key under agents.defaults

`openclaw.json` is strict about its schema. Common mistakes:

- `elevated` belongs under `tools.exec.security`, not `agents.defaults.elevated`
- `auth.profiles` is a top-level key, not under `agents.defaults.auth`

If the gateway crash-loops with "Config invalid", check `docker compose logs openclaw-gateway` for the exact rejected key.

### New env vars not picked up after restart

`docker compose restart` reuses the existing container -- it does NOT re-read `.env`. You must recreate the container:

```bash
docker compose up -d openclaw-gateway --force-recreate
```

### Context window filling up (87% used warning) [Ollama only]

Type `/new` in the OpenClaw chat to start a fresh session with a clean context window. Models are configured with 32k context windows. Long conversations or tool-heavy subagent loops fill this up quickly. If the agent crashes with "Context overflow: prompt too large", use `/new` or `/reset` to clear the session.

### GH_TOKEN picked up as github-copilot provider

This is expected. OpenClaw auto-detects `GH_TOKEN` as a GitHub Copilot credential. It works alongside the Ollama provider.

## Volume access summary

| Container path                   | Host path               | Purpose                |
| -------------------------------- | ----------------------- | ---------------------- |
| `/home/node/.openclaw`           | `~/.openclaw`           | Config, auth, sessions |
| `/home/node/.openclaw/workspace` | `~/.openclaw/workspace` | Coding projects        |

The container only has access to these paths. The rest of the host filesystem is inaccessible.

## File overview

| File                                                |    Contains secrets?    |      Committed?       | Purpose                                             | Mode      |
| --------------------------------------------------- | :---------------------: | :-------------------: | --------------------------------------------------- | --------- |
| `Dockerfile`                                        |           No            |          Yes          | Base OpenClaw image (upstream)                      | Both      |
| `Dockerfile.custom`                                 |           No            |          Yes          | Custom tool additions (gh, ffmpeg)                  | Both      |
| `docker-compose.yml`                                |           No            |          Yes          | Service definitions (gateway + cli + whisper)       | Both      |
| `.env`                                              |         **Yes**         |  **No** (gitignored)  | Runtime secrets and config                          | Both      |
| `~/.openclaw/openclaw.json`                         | **Yes** (gateway token) | **No** (outside repo) | Gateway, model providers, and agent config          | Both      |
| `~/.openclaw/agents/main/agent/auth-profiles.json`  | **Yes** (Claude token)  | **No** (outside repo) | Claude auth token                                   | Anthropic |
| `~/Library/LaunchAgents/homebrew.mxcl.ollama.plist` |           No            |          No           | Ollama service config (keep-alive, flash attention) | Ollama    |
