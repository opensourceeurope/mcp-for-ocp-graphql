# Local agent with a desktop UI — no terminal needed

A fully local setup for using this MCP with an AI, designed for **non-technical users**: one downloadable app, point-and-click model picker, no Docker, no command line beyond a single copy-pasted line. All conversation and data stays on your machine.

> Prefer the terminal? The CLI path (Ollama + Goose) lives in [local-agent-with-ollama.md](local-agent-with-ollama.md).

We recommend **[LM Studio](https://lmstudio.ai/)** because it bundles the model runtime, model downloader, chat UI, *and* MCP support in a single app. There's no separate "AI engine" to install. (A second option, **[Cherry Studio](https://github.com/CherryHQ/cherry-studio)**, is at the end if you already use Ollama or want an open-source app.)

The MCP runs locally: LM Studio starts it for you with your Open Collective token, and it talks to Open Collective directly. There is no server to set up and no sign-in webpage.

---

## What you'll end up with

- LM Studio running on your laptop
- A local AI model downloaded inside it (no cloud account)
- This MCP connected, so the AI can pull data from Open Collective
- A chat window that looks like ChatGPT — but nothing leaves your machine

---

## Before you start

- A laptop with **at least 16 GB RAM** (24 GB+ for a noticeably smarter model)
- About **20 GB of free disk space** for the model
- An **Open Collective personal token** — get one at [opencollective.com/dashboard/personal-tokens](https://opencollective.com/dashboard/personal-tokens) and copy it; you'll paste it into a settings file in step 4

---

## Step 1 — Install LM Studio

1. Go to [**lmstudio.ai**](https://lmstudio.ai/) and click **Download**.
2. The site auto-detects your operating system (macOS, Windows, Linux). Run the installer like any other app.
3. Open LM Studio. The first launch may take a minute as it sets up.

LM Studio is free for personal and commercial use. It does not require an account.

---

## Step 2 — Download a model

In LM Studio, click the **🔍 Discover** icon in the left sidebar. Search for one of these names and click **Download** on the result. LM Studio will pick the right file size for your laptop automatically.

| If your laptop has… | Search for | Download size |
|---|---|---|
| **16 GB RAM** | `qwen3-14b` | ~9 GB |
| **24 GB RAM** *(recommended)* | `gpt-oss-20b` | ~14 GB |
| **32 GB RAM** | `qwen3-32b` | ~20 GB |
| **48 GB+ RAM** | `llama-3.3-70b` | ~43 GB |

> **Don't pick the smallest model.** Answering these questions means writing real GraphQL queries and chaining a few tool calls; smaller models (7–8 B) get that wrong. Stick with the table.

Download takes a few minutes on a fast connection. While it runs, continue to step 3.

---

## Step 3 — Install uv (one-time, ~2 minutes)

The MCP runs as a small program that LM Studio launches for you. It needs **uv** — a small free runtime that also brings its own Python, so there's nothing else to install. You will not write any code; it runs itself. This is the one time you'll touch a terminal — a single pasted line.

- **macOS / Linux** — open the **Terminal** app and paste:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Windows** — open **PowerShell** and paste:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

That's it. Close and reopen the terminal (and LM Studio, later) so it picks up the new `uvx` command. You will never open uv directly.

---

## Step 4 — Tell LM Studio about the MCP

> **One-click shortcut:** clicking [![Add to LM Studio](https://files.lmstudio.ai/deeplink/mcp-install-light.svg)](lmstudio://add_mcp?name=opencollective&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtY3AtZm9yLW9jcC1ncmFwaHFsIl19) opens LM Studio and adds the server (as **opencollective**) — but *without your token* (anonymous, public data only). To use your token, do the manual steps below instead; they include it. (Requires LM Studio 0.3.17+.)

1. Open LM Studio.
2. Click the **🧩 Program** icon in the right sidebar.
3. Click **Install** → **Edit mcp.json**. A small text editor opens.
4. Paste exactly this, replacing `PASTE-YOUR-TOKEN-HERE` with the Open Collective personal token you copied in "Before you start":

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

5. Save (Cmd-S or Ctrl-S) and close the editor.

LM Studio starts the MCP in the background. **The very first time it may take a few minutes** — it downloads the program and its components; after that it starts instantly. No browser tab, no sign-in page. Your token stays in this file on your laptop.

> **Where your token lives:** the MCP program never saves your token or sends it anywhere except Open Collective — it only keeps it in memory while running. The one saved copy is this `mcp.json` file, in plain text. That's normal for a personal machine — just don't share the file or sync it to a public place.

---

## Step 5 — Start chatting

1. In LM Studio, click the **💬 Chat** icon in the left sidebar.
2. At the top, pick the model you downloaded.
3. Make sure **opencollective** appears in the tool list (look for a small puzzle-piece icon next to the input box).
4. Try a simple question:

   > How many active collectives are under the host with slug `opensource-europe`? Use the Open Collective tools. Just give me a number.

   The AI should call a tool, briefly show the call, and answer with a count.

5. Then try something more interesting:

   > For the host `opensource-europe`, list the 10 collectives with the most approved expenses in the last 90 days. Don't fetch the expense contents — just counts.

If it works, you're done. The conversation and tool results never leave your laptop.

---

## Step 6 — (optional but recommended) give the AI the querying playbook

The Claude Code plugin ships a *skill* that teaches the assistant how to query Open Collective well — the search-first workflow, how to count without dumping rows, the field gotchas, and the personal-data rules. LM Studio has no "skills", but it has the next best thing: a **system prompt** you can save as a reusable **preset**.

Paste the block below into LM Studio's **System Prompt** field (right sidebar in the chat view, under the model settings), then — so you don't repeat this every time — open the **preset** dropdown at the top of the chat and choose **Save as new preset**.

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

> **A note on the personal-data rule with local models.** These guardrails are *instructions*, not code — the server will happily return any field your token can read. Smaller local models follow such rules less reliably than a frontier model does, so treat the PII rule as a reminder for **you**, not a guarantee. When in doubt, don't ask for email/contact fields. See [using-with-ai-safely.md](using-with-ai-safely.md).

---

## Working with personal data

Because the model runs on your laptop, you *can* ask about personal data (emails, contact info) without anyone else seeing it. But files the AI saves on your machine are still personal data — handle them carefully:

- Don't paste those files into a hosted AI later (ChatGPT, Claude.ai, etc.).
- If your laptop syncs files to iCloud / OneDrive / Dropbox, those copies leave your machine.
- Follow the same care you'd give any export of personal data.

See [using-with-ai-safely.md](using-with-ai-safely.md) for the full picture.

---

## Troubleshooting

**"opencollective" doesn't appear in the tool list.**
Close LM Studio fully, open it again. If still missing, open the Program panel → check the `mcp.json` you edited for typos (most often: missing comma, missing quotes, or the token not pasted between the quotes).

**Every question comes back with an authorization error.**
The token in `mcp.json` is missing, wrong, or pasted with extra spaces/line breaks. Re-copy it from [opencollective.com/dashboard/personal-tokens](https://opencollective.com/dashboard/personal-tokens) and paste it again between the quotes after `OC_PERSONAL_TOKEN`.

**The model gives weird answers or invents data.**
You may have picked a model that's too small. Re-download a model one row higher in the table in Step 2.

**"command not found" or the MCP won't start.**
uv isn't installed or wasn't picked up. Re-do Step 3, then fully restart LM Studio so it sees the new `uvx` command.

**Everything is very slow.**
The model is too big for your laptop. Pick the row above in Step 2 (smaller model). On Apple Silicon Macs, models in the table run smoothly; on older Intel laptops without a dedicated GPU, expect slower responses.

---

## Alternative — Cherry Studio (open-source, uses Ollama)

If you already use Ollama or want an open-source app:

1. Install Ollama from [ollama.com](https://ollama.com/) and download a model with `ollama pull qwen3:14b`.
2. Install Cherry Studio from [github.com/CherryHQ/cherry-studio/releases](https://github.com/CherryHQ/cherry-studio/releases) (DMG for macOS, EXE for Windows, AppImage/.deb for Linux).
3. Open Cherry Studio → **Settings → MCP Servers → Add Server**.
4. Set **Type**: `stdio`, **Command**: `uvx`, **Arguments**: `mcp-for-ocp-graphql`, and add an **environment variable** `OC_PERSONAL_TOKEN` with your token.
5. Pick your Ollama model in the chat tab. Start chatting.

No sign-in webpage here either — the token in the server settings is all it needs.

---

## References

- [LM Studio download](https://lmstudio.ai/) · [MCP docs](https://lmstudio.ai/docs/app/mcp)
- [Cherry Studio releases](https://github.com/CherryHQ/cherry-studio/releases)
- [uv installation](https://docs.astral.sh/uv/getting-started/installation/)
- [`mcp-for-ocp-graphql` on PyPI](https://pypi.org/project/mcp-for-ocp-graphql/)
