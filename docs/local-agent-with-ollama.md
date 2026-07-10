# Local agent with Ollama (CLI) — quick start

A lightweight, fully local setup for querying the Open Collective MCP with no data leaving your machine: **Ollama** for the model, **Goose** as the agent, and this MCP running locally in **stdio mode** — no hosted server, no OAuth, no bridge.

> Prefer a graphical app to the terminal? See [local-agent-with-ui.md](local-agent-with-ui.md) — same stack philosophy, but LM Studio (or Cherry Studio) instead of the CLI.

Why this stack:

- **Ollama** — easiest local model runner, one binary, every popular model.
- **Goose** — open-source CLI agent with native Ollama and MCP support, no IDE required.
- **`mcp-for-ocp-graphql` in stdio mode** — Goose launches the MCP as a local subprocess and talks to it over stdio. Your OC personal token is passed straight to it via an env var; nothing leaves your machine except the calls Open Collective itself has to answer.

Everything runs on your machine. There is no remote MCP instance and no OAuth handshake — `uvx` fetches and runs the server locally.

---

## Prerequisites

- **macOS, Linux, or Windows** with at least **16 GB RAM** (24 GB+ recommended for the strongest models).
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** (to run `uvx mcp-for-ocp-graphql`). uv manages its own Python, so you don't need Python installed separately.
- A few GB of free disk and network for the **first run**: `uvx` installs the server's Python dependencies (including PyTorch), and the first `search_docs` call downloads the embedding model (~500 MB). `graphql_query`/`schema_lookup` work immediately without it.
- An **Open Collective personal token** — get one at [opencollective.com/dashboard/personal-tokens](https://opencollective.com/dashboard/personal-tokens). Optional: with no token the server runs anonymously against public data.

---

## Step 1 — Install Ollama

**macOS** (Homebrew):

```bash
brew install ollama
```

**Linux**:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows**: download the installer from [ollama.com/download](https://ollama.com/download).

Then start the daemon (macOS/Linux):

```bash
ollama serve &
```

On macOS, the Ollama desktop app starts it automatically.

---

## Step 2 — Pull a model

The MCP exposes **three tools** — `search_docs`, `schema_lookup`, `graphql_query` — and a typical analytics task needs the model to chain them: search the docs, confirm the exact fields, then **hand-write a raw GraphQL query**, paginate, and aggregate. Authoring valid GraphQL and following that multi-step flow is what smaller models struggle with. Pick by RAM, not by hype:

| RAM available | Recommended | Disk size | Why |
|---|---|---|---|
| **16 GB** | `qwen3:14b` | 9.3 GB | Strongest "stable with many tools" small model. Reliable function calls. |
| **24 GB** | `gpt-oss:20b` | 14 GB | Native function calling, adjustable reasoning effort, surprisingly fast. **Best balance**. |
| **32 GB** | `qwen3:32b` or `qwen2.5:32b` | 20 GB | Multi-step analytics with comfortable headroom. |
| **48 GB+** | `llama3.3:70b` or `gpt-oss:120b` | 43–65 GB | Cloud-model-tier quality. Slow on CPU; fine on Apple Silicon with unified memory. |

**Avoid for this workload**: anything ≤ 8B parameters. Small models are unreliable at authoring valid GraphQL and at chaining tool calls over several steps — expect malformed queries, repeated 400s from the API, and silent give-ups. (Goose contributors report the same fragility in tool-calling loops: [block/goose#6883](https://github.com/block/goose/issues/6883), [block/goose discussion #1403](https://github.com/block/goose/discussions/1403).)

Pull your pick:

```bash
ollama pull gpt-oss:20b
# or whichever row from the table fits your RAM
```

Sanity check:

```bash
ollama run gpt-oss:20b "Say hi in one word."
```

---

## Step 3 — Install Goose

**macOS** (Homebrew):

```bash
brew install block-goose-cli
```

**Linux / macOS without Homebrew**:

```bash
curl -fsSL https://github.com/aaif-goose/goose/releases/download/stable/download_cli.sh | bash
```

**Windows**: see [Goose installation docs](https://goose-docs.ai/docs/getting-started/installation/).

Configure:

```bash
goose configure
```

When prompted:

- **Provider**: `Ollama`
- **Host**: `http://localhost:11434` (the default — accept it)
- **Model**: the name you pulled, e.g. `gpt-oss:20b`

Goose writes its config to `~/.config/goose/config.yaml`. You'll edit it in the next step.

---

## Step 4 — Bump the Ollama context window

Ollama defaults to a **2048-token context**, which Goose's system prompt alone nearly fills. Without this fix, your prompts will be silently truncated and tool calls will fail in mysterious ways ([block/goose#1253](https://github.com/block/goose/issues/1253)).

Open `~/.config/goose/config.yaml` and ensure the Ollama provider block sets `num_ctx`:

```yaml
GOOSE_PROVIDER: ollama
GOOSE_MODEL: gpt-oss:20b
OLLAMA_HOST: http://localhost:11434
OLLAMA_NUM_CTX: 16384   # or 32768 if your model and RAM allow
```

The exact key may vary by Goose version — if `OLLAMA_NUM_CTX` doesn't take effect, check the model's `Modelfile` and bake the context in there with `ollama create`.

---

## Step 5 — Add the OC MCP as a Goose extension

The MCP runs locally over stdio; Goose launches it and passes your token via an env var. No browser, no OAuth, no token cache.

```bash
goose configure
```

Choose **Add Extension → Command-line Extension** and fill in:

- **Name**: `opencollective`
- **Command**: `uvx`
- **Args**: `mcp-for-ocp-graphql`
- **Timeout**: 300 (seconds)
- **Environment variables**: add `OC_PERSONAL_TOKEN` = your Open Collective personal token

Save. The resulting block in `~/.config/goose/config.yaml` looks like:

```yaml
extensions:
  opencollective:
    enabled: true
    type: stdio
    cmd: uvx
    args:
      - mcp-for-ocp-graphql
    envs:
      OC_PERSONAL_TOKEN: "<your token>"
    timeout: 300
```

> **First launch is slow.** The first time Goose starts the extension, `uvx` installs the server's Python dependencies (including PyTorch) — that can take a few minutes and may exceed the 300 s timeout on a slow connection. Pre-warm it once by running `uvx mcp-for-ocp-graphql` in a terminal (Ctrl-C after it prints its startup line), then start Goose.

> **Where your token lives:** the MCP server never writes your token to disk or logs it — it only holds it in memory while running. The one persistent copy is this `config.yaml`, where Goose stores it in plaintext (Goose's `envs` takes literal values, so there's no env-variable indirection here). That's acceptable for a single-user local machine — treat the file like any other secret: don't commit it, don't sync it to a shared cloud drive.

Goose now starts `mcp-for-ocp-graphql` as a subprocess on every session and talks to it over stdio.

---

## Step 6 — First query

```bash
goose session
```

Try a tame, aggregate query first — no PII, exercises tool selection and counting:

```
How many active collectives are under the host with slug "opensource-europe"?
Use the OC MCP. Just give me the totalCount.
```

The agent should use `search_docs`/`schema_lookup` to shape the query, then call `graphql_query` with something like `{ accounts(host: [{slug: "opensource-europe"}], limit: 1) { totalCount } }`, read `totalCount`, and return a number. If it does, the stack is working.

Then a real analytics question:

```
For the host "opensource-europe", list the 10 collectives with the
most approved expenses in the last 90 days. Use totalCount, do not
fetch row contents. Roll Project/Event children into their parent.
```

The patterns this exercises (using `totalCount` instead of fetching rows, rolling children into parents) are the ones documented in [plugins/oc-platform-api/skills/querying-opencollective-graphql/SKILL.md](../plugins/oc-platform-api/skills/querying-opencollective-graphql/SKILL.md) — feed that file's content to the model as a system prompt if you want it to follow them reliably.

---

## Working with personal data

Local model = the data stays on your machine. You can ask for emails and contact fields without them reaching any provider. But the disk artifacts the agent creates are still personal data:

- Files Goose writes (reports, CSVs, transcripts) are PII on disk — handle them under whatever care your GDPR setup requires.
- If you sync `~` to a cloud backup (iCloud, Dropbox, Time Machine to a networked drive), those files leave your machine.
- Don't paste local-session transcripts into a hosted AI later.

See [docs/using-with-ai-safely.md](using-with-ai-safely.md) for the full handling rules.

---

## Troubleshooting

**The agent keeps switching from JSON tool calls to XML.**
You're using a small model with too many tools loaded. Switch to `gpt-oss:20b` or `qwen3:14b` minimum. ([block/goose#6883](https://github.com/block/goose/issues/6883))

**Goose system prompt seems truncated; tool calls misfire silently.**
You skipped Step 4. Ollama's 2048-token default isn't enough — bump `num_ctx` to at least 16384.

**The extension fails to start / "command not found".**
Make sure `uv` is installed and `uvx` is on your `PATH` (`uvx --version`). The first run downloads the package and its Python dependencies (including PyTorch) — that needs network and can take a few minutes; pre-warm with `uvx mcp-for-ocp-graphql` in a terminal.

**A query returns an auth error or empty private data.**
The server does **not** require a token — with none it runs anonymously against public data. If you need private data, `OC_PERSONAL_TOKEN` in the extension's `envs` is missing or wrong; an invalid token is rejected by Open Collective on the first query. Re-check the value in `~/.config/goose/config.yaml`.

**The first `search_docs` call hangs for a while.**
That's the one-time embedding-model download (~500 MB). Subsequent searches are fast. `graphql_query` and `schema_lookup` don't need the model.

**The model invents fields and gets 400s from the API.**
The OC schema has inline-fragment quirks (e.g. `host`, `parent`, `isApproved` aren't on the base `Account` type). Paste the contents of [`plugins/oc-platform-api/skills/querying-opencollective-graphql/SKILL.md`](../plugins/oc-platform-api/skills/querying-opencollective-graphql/SKILL.md) into the system prompt — it's the same playbook hosted Claude uses.

**Performance is unusable on CPU.**
Apple Silicon with unified memory handles `gpt-oss:20b` and `qwen3:14b` well. On x86 without a discrete GPU, drop to a 7–8B model and accept the tool-calling weakness, or run a smaller model with shorter conversations.

---

## References

- [Goose installation](https://goose-docs.ai/docs/getting-started/installation/) · [config file](https://block.github.io/goose/docs/guides/config-file/)
- [Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling) · [Goose integration](https://docs.ollama.com/integrations/goose)
- Models: [qwen3](https://ollama.com/library/qwen3) · [qwen2.5](https://ollama.com/library/qwen2.5) · [gpt-oss](https://ollama.com/library/gpt-oss) · [llama3.3](https://ollama.com/library/llama3.3) · [mistral-small3.2](https://ollama.com/library/mistral-small3.2)
- [`mcp-for-ocp-graphql` on PyPI](https://pypi.org/project/mcp-for-ocp-graphql/) · [uv installation](https://docs.astral.sh/uv/getting-started/installation/)
