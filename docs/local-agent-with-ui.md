# Local agent with a desktop UI — no terminal needed

A fully local setup for using this MCP with an AI, designed for **non-technical users**: a desktop app, point-and-click model picker, no Docker, barely any terminal. All conversation and data stays on your machine.

> Prefer the terminal? The CLI path (Ollama + Goose) lives in [local-agent-with-ollama.md](local-agent-with-ollama.md).

We recommend **[Cherry Studio](https://github.com/CherryHQ/cherry-studio)** (open-source) because it can install the **exact querying skill this project ships** — one click, the same guidance the Claude Code plugin bundles — right alongside the MCP server. It runs your model through **[Ollama](https://ollama.com/)**, a small free local model runner. If you'd rather have everything in one app with no separate model runner, **[LM Studio](https://lmstudio.ai/)** is a great alternative — see the [LM Studio section](#alternative--lm-studio) at the end.

Either way the MCP runs locally: the app starts it for you with your Open Collective token, and it talks to Open Collective directly. There is no server to set up and no sign-in webpage.

---

## What you'll end up with

- Cherry Studio + Ollama running on your laptop
- A local AI model (no cloud account)
- This MCP connected **and** the querying skill installed, so the AI pulls Open Collective data *and* queries it well
- A chat window that looks like ChatGPT — but nothing leaves your machine

---

## Before you start

- A laptop with **at least 16 GB RAM** (24 GB+ for a noticeably smarter model)
- About **20 GB of free disk space** for the model
- An **Open Collective personal token** — get one at [opencollective.com/dashboard/personal-tokens](https://opencollective.com/dashboard/personal-tokens) and copy it; you'll paste it into the MCP server settings in Step 5.

---

## Step 1 — Install Ollama and pull a model

Cherry Studio doesn't bundle a model runtime, so install **Ollama** — a small free local model runner.

- **macOS:** `brew install ollama` (or the installer at [ollama.com/download](https://ollama.com/download))
- **Linux:** `curl -fsSL https://ollama.com/install.sh | sh`
- **Windows:** the installer at [ollama.com/download](https://ollama.com/download)

On macOS the desktop app starts the daemon automatically; on Linux run `ollama serve &`.

Then pull a model sized to your RAM (bigger = smarter but slower):

| If your laptop has… | Pull | Size |
|---|---|---|
| **16 GB RAM** | `ollama pull qwen3:14b` | ~9 GB |
| **24 GB RAM** *(recommended)* | `ollama pull gpt-oss:20b` | ~14 GB |
| **32 GB RAM** | `ollama pull qwen3:32b` | ~20 GB |
| **48 GB+ RAM** | `ollama pull llama3.3:70b` | ~43 GB |

> **Don't pick a tiny model.** Answering these questions means writing real GraphQL and chaining a few tool calls; models ≤ 8 B get that wrong. Stick with the table.

---

## Step 2 — Install Cherry Studio

Download from [github.com/CherryHQ/cherry-studio/releases](https://github.com/CherryHQ/cherry-studio/releases) — DMG for macOS (**arm64** for Apple Silicon incl. M-series, **x64** for Intel), EXE for Windows, AppImage/.deb for Linux. Install like any other app; no account needed.

---

## Step 3 — Install uv (one-time, ~2 minutes)

The MCP runs as a small program Cherry launches for you. It needs **uv** — a small free runtime that brings its own Python, so there's nothing else to install. This is the one time you'll touch a terminal — a single pasted line.

- **macOS / Linux:**
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Windows** (PowerShell):
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

Close and reopen the terminal (and Cherry Studio) so the new `uvx` command is picked up. You'll never open uv directly.

---

## Step 4 — Point Cherry Studio at your local model

> **Use a normal chat — not the "Agents" tab.** Cherry's **Agents** tab runs *CLI coding agents* (Claude Code, Codex, …), which expect Claude/Codex-class cloud models. If you pick one of those agents and hand it an Ollama model, you'll get `There's an issue with the selected model … Run --model` — that's the **Claude Code CLI** rejecting a non-Claude model, **not** an Ollama permissions problem (local Ollama needs no auth, and Ollama is never even contacted). For local models, use a regular **chat / Assistant** with the **Ollama** provider, as below.

1. Make sure Ollama is running (Step 1).
2. Cherry Studio → **Settings → Model Providers → Ollama**.
3. Set the API host to `http://localhost:11434`, then click **Manage/Refresh Models** — your pulled model appears. No API key, no sign-in.
4. Open a new chat and select your Ollama model at the top.

---

## Step 5 — Add the MCP server

1. Cherry Studio → **Settings → MCP Servers → Add Server**.
2. Set **Type**: `stdio`, **Command**: `uvx`, **Arguments**: `mcp-for-ocp-graphql`, and add an **environment variable** `OC_PERSONAL_TOKEN` = the token you copied (leave it out to run anonymously against public data).
3. Save. **The first launch downloads the program** (a minute or two on a slow connection); after that it starts instantly.

> **Where your token lives:** the MCP never writes your token to disk or logs it — it only holds it in memory while running. The one saved copy is in Cherry's server settings on your machine, in plain text. That's normal for a personal machine — just don't share it or sync it to a public place.

---

## Step 6 — Install the querying skill

So the model queries Open Collective *well* — search-first, counting via `totalCount`, the field gotchas, and the personal-data rules — install the skill this project ships:

1. Download [`opencollective-cherry-skill.zip`](https://github.com/opensourceeurope/mcp-for-ocp-graphql/releases/latest/download/opencollective-cherry-skill.zip) (attached to each release).
2. Cherry Studio → **Skills → install from zip file** (or unzip it and use **install from directory**).

It bundles the analyst framing plus the full query playbook — the same guidance the Claude Code plugin ships as a skill + agent, merged into one Cherry skill.

---

## Step 7 — Start chatting

Select your Ollama model, make sure the Open Collective tools and the skill are active, and try a tame aggregate question first:

> How many active collectives are under the host with slug `europe`? Use the Open Collective tools. Just give me a number.

The AI should call a tool, briefly show the call, and answer with a count. Then something meatier:

> For the host `europe`, list the 10 collectives with the most approved expenses in the last 90 days. Don't fetch the expense contents — just counts.

If it answers with real numbers, you're done. The conversation and tool results never leave your laptop.

---

## Working with personal data

Because the model runs on your laptop, you *can* ask about personal data (emails, contact info) without anyone else seeing it. But files the AI saves on your machine are still personal data — handle them carefully:

- Don't paste those files into a hosted AI later (ChatGPT, Claude.ai, etc.).
- If your laptop syncs files to iCloud / OneDrive / Dropbox, those copies leave your machine.
- Follow the same care you'd give any export of personal data.

> **A note on the personal-data rule with local models.** The skill's PII guardrails are *instructions*, not code — the server will happily return any field your token can read. Smaller local models follow such rules less reliably than a frontier model does, so treat the PII rule as a reminder for **you**, not a guarantee. When in doubt, don't ask for email/contact fields.

See [using-with-ai-safely.md](using-with-ai-safely.md) for the full picture.

---

## Alternative — LM Studio

Prefer a **single app** that bundles the model runtime, model downloader, chat UI, *and* MCP support — no separate Ollama to install? Use **[LM Studio](https://lmstudio.ai/)**. The trade-off: LM Studio has **no skill import**, so the querying guidance goes in as a pasted **system prompt / preset** rather than the installable skill.

### 1 — Install LM Studio and download a model

1. Get it from [lmstudio.ai](https://lmstudio.ai/) → **Download** (auto-detects macOS/Windows/Linux). No account needed. (macOS needs Apple Silicon; see [system requirements](https://lmstudio.ai/docs/app/system-requirements).)
2. Click the **🔍 Discover** icon and download a model sized to your RAM — `qwen3-14b` (16 GB), `gpt-oss-20b` (24 GB, recommended), `qwen3-32b` (32 GB), `llama-3.3-70b` (48 GB+). Don't pick a ≤ 8 B model.

Install **uv** too (Step 3 above) — LM Studio launches the MCP with it.

### 2 — Tell LM Studio about the MCP

> **One-click shortcut:** clicking [![Add to LM Studio](https://files.lmstudio.ai/deeplink/mcp-install-light.svg)](lmstudio://add_mcp?name=opencollective&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtY3AtZm9yLW9jcC1ncmFwaHFsIl19) opens LM Studio and adds the server (as **opencollective**) — but *without your token* (anonymous, public data only). To use your token, do the manual steps below instead; they include it. (Requires LM Studio 0.3.17+.)

1. Open LM Studio and click the **💬 Chat** icon (left sidebar) — the right-hand sidebar with the developer tabs only shows in the Chat view.
2. In the right-hand sidebar, click the **terminal icon** (`>_`) — LM Studio labels this tab **Program**. Don't see it? LM Studio hides developer tabs in the default view: use the mode selector at the **bottom of the window** to switch from **User** to **Power User**, then look again.
3. Click **Install** → **Edit mcp.json**. A small in-app text editor opens.

   > **Can't find the icon? Edit the file directly** — this always works, whatever the UI looks like. Open **`~/.lmstudio/mcp.json`** (macOS/Linux) or **`%USERPROFILE%\.lmstudio\mcp.json`** (Windows) in any text editor. LM Studio loads it automatically when you save.
4. Paste this, replacing `PASTE-YOUR-TOKEN-HERE` with your token:

   ```json
   {
     "mcpServers": {
       "opencollective": {
         "command": "uvx",
         "args": ["mcp-for-ocp-graphql"],
         "env": { "OC_PERSONAL_TOKEN": "PASTE-YOUR-TOKEN-HERE" }
       }
     }
   }
   ```

5. Save (Cmd-S / Ctrl-S). The first launch downloads the program (a few minutes), then it's instant. Your token stays in this file on your laptop.

### 3 — Give the AI the querying playbook (system prompt)

LM Studio has no skill import, so paste the block below into LM Studio's **System Prompt** field (right sidebar in the chat view, under the model settings), then open the **preset** dropdown at the top of the chat and choose **Save as new preset** so you don't repeat it.

```text
You answer questions about Open Collective using three MCP tools. Never guess field names — look them up.

Work in this order:
1. search_docs("…") — find which query and fields to use.
2. schema_lookup("Name") — confirm a type/field's exact fields and which arguments are truly required. Trust its `required` flag, not the `!` in the type (most `!` args have defaults and can be omitted).
3. graphql_query("…") — run a READ-ONLY GraphQL query. Mutations and subscriptions are rejected.

Rules:
- To count, select `totalCount` with `limit: 1`. Never fetch rows just to count them.
- Many fields (host, parent, isApproved) are NOT on the base Account type — select them inside an inline fragment, e.g. `... on AccountWithHost { host { slug } }`. If you get an error, it names the fragment type to use.
- Keep results small: select only the fields asked for; page large collections with `limit`/`offset`.
- Host-filtered results reflect membership at record time (migrated accounts still show up). To state an account's CURRENT host, query `account(slug: $s) { ... on AccountWithHost { host { slug } } }`.

Personal data: email and contact fields on individual people are PII. Do NOT select them by default. Before retrieving any PII, tell the user it will enter this model's context and wait for their confirmation.
```

Then pick your model, confirm **opencollective** appears in the tool list, and use the same test questions as Step 7 above. The local-model PII caveat applies here too.

---

## References

- [Cherry Studio releases](https://github.com/CherryHQ/cherry-studio/releases) · [Ollama](https://ollama.com/)
- [LM Studio download](https://lmstudio.ai/) · [MCP docs](https://lmstudio.ai/docs/app/mcp)
- [uv installation](https://docs.astral.sh/uv/getting-started/installation/)
- [`mcp-for-ocp-graphql` on PyPI](https://pypi.org/project/mcp-for-ocp-graphql/)
