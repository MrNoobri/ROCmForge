# ROCmForge — Execution Plan (3-Person Team, 6-Day Sprint)

> Companion document to `ROCmForge_Project_Plan.md`. That file = **what** we're building. This file = **who builds what, when, with which tools, and exactly what to ask GPT for.**

**Hackathon window:** 2026-05-04 (Day 1) → 2026-05-09 (submission).
**Team size:** 3.

---

## 0. AI Collaboration Protocol — READ BEFORE SENDING ANY PROMPT TO AN AI

Every prompt in this document is meant to be sent to an AI assistant (ChatGPT, Claude, Cursor, **GitHub Copilot Chat in agent mode**, etc.). Those tools sometimes try to be "helpful" by running `git push`, `git commit -am`, force-pushing, or installing global packages. **We do not want that.** The human owns git. The AI writes code.

> **Note for GitHub Copilot users (all 3 of us):** Copilot's *inline* tab-completion does not run terminal commands and is fine without the rules block. But **Copilot Chat in agent mode** (the one that can edit files and run commands) is just like ChatGPT/Claude — it must get the §0 Standing Rules block at the top of every task.

### The Standing Rules (every AI prompt must include this block)

Copy-paste this block at the **top of every prompt** you send to an AI for this project:

> **Project rules — follow strictly:**
>
> 1. **Do NOT run `git push`, `git commit`, `git add`, `git merge`, or any state-changing git command.** I will commit and push myself.
> 2. **Do NOT create or switch branches.** I have already created and checked out the correct branch before invoking you. If you think a branch change is needed, tell me — don't do it.
> 3. **Do NOT install packages globally.** Use the project's `requirements.txt` and `.venv/`. If a new dependency is needed, _add it to `requirements.txt`_ and tell me to `pip install -r requirements.txt`.
> 4. **Do NOT delete files outside the directory you were asked to modify.** No `rm -rf`, no "cleanup" sweeps.
> 5. **Do NOT touch `.streamlit/secrets.toml`, `.env`, any file matching `*secret*` or `*key*`, or `LICENSE`.** Read them only if I explicitly point you at them.
> 6. **Add any temp files, caches, build artifacts, model downloads, or run outputs you create to `.gitignore`.** Don't let them sneak into a commit.
> 7. **Stay on the current working directory's project.** Do not modify files in other repos or `~/.config/*`.
> 8. **At the end of your work, output two things:**
>    - a) A **summary of every file you created or modified** (relative paths, one per line).
>    - b) A **suggested git workflow**: the branch name I should be on, the exact `git add` lines for the files you changed (no `git add .`), a single conventional-commit message (e.g. `feat(scanner): add CUDA pattern detector`), and the `git push -u origin <branch>` command. **Do not run those commands** — just print them so I can run them myself.

### Branch workflow (the human runs these — never the AI)

Before sending an AI any prompt that produces code, the human runs:

```bash
# from the repo root, on a clean main
git checkout main
git pull
git checkout -b phase-<N>-<short-name>      # e.g. phase-2-scanner
# now invoke the AI with the prompt for that phase
```

After the AI finishes, the human reviews the diff, then:

```bash
git status                                  # sanity check — no surprise files
git add <specific files the AI listed>      # never `git add .`
git commit -m "<conventional commit message the AI suggested>"
git push -u origin phase-<N>-<short-name>
# open a PR on GitHub for review by another teammate
```

Only after PR approval and merge does the work land on `main`.

### What goes in `.gitignore` from Day 1

The Phase 0 scaffold prompt is the right place to set this up. The `.gitignore` must include from the start:

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# Virtualenvs
.venv/
venv/
env/

# Environment / secrets — NEVER COMMIT THESE
.env
.env.*
!.env.example
.streamlit/secrets.toml
*.pem
*.key
*_rsa
*_ed25519

# Editors / OS
.vscode/
.idea/
.DS_Store
Thumbs.db
*.swp

# RAG / model artifacts
.chroma/
*.sqlite3
*.bin
*.safetensors
models/

# Run outputs (keep the dir, ignore contents)
outputs/*
!outputs/.gitkeep

# Logs
*.log
logs/

# Build / dist
build/
dist/
*.tar.gz

# AMD/ROCm runtime artifacts that some scripts dump
core_dump_*
hsakmt.log

# Demo cached run JSON is COMMITTED — do NOT ignore examples/cached_runs/
```

If an AI is told to add files that obviously shouldn't be in the repo (large model weights, cache dirs, etc.), it must add the matching pattern to `.gitignore` _and_ tell you in its summary.

### Reminder: Streamlit Cloud auto-deploys from `main`

When `main` updates, Streamlit Cloud redeploys. So:

- `main` is sacred — never push broken code there.
- Always work on a phase branch.
- Only merge to `main` after the branch's code has been smoke-tested locally.
- Day 5 onward: any merge to `main` triggers a redeploy of the live demo URL — coordinate merges with the team.

---

## 1. Locked Tech Stack (no more "or X")

| Layer                 | Choice                                                                   | Why                                                                                                |
| --------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| Frontend / UI         | **Streamlit**                                                            | Fast, file upload + charts + status streaming built-in, deploys free to Streamlit Community Cloud. |
| Hosting (UI)          | **Streamlit Community Cloud**                                            | Free, public URL, auto-deploys from GitHub. Required for the "Application URL" submission field.   |
| Agent framework       | **CrewAI**                                                               | Role-based agents, OpenAI-compatible LLM client, easiest to explain to judges.                     |
| LLM                   | **Qwen2.5-Coder-7B-Instruct**                                            | Coder-tuned, fits one MI300X, official lablab tutorial covers it.                                  |
| LLM serving           | **vLLM** on AMD Developer Cloud                                          | OpenAI-compatible HTTP API → CrewAI plugs in with no adapter.                                      |
| LLM hardware          | **AMD Instinct MI300X** (Dev Cloud)                                      | Provided by hackathon, single GPU enough.                                                          |
| Sandbox runtime       | Separate AMD Dev Cloud instance, **ROCm 6.x + PyTorch ROCm**             | Where migrated code is actually executed.                                                          |
| RAG (Knowledge Agent) | **ChromaDB** (local file) + `sentence-transformers` (`all-MiniLM-L6-v2`) | Tiny, local, no API calls, no extra service.                                                       |
| Backend language      | **Python 3.11**                                                          | What everything else expects.                                                                      |
| Patch format          | **unified diff** via Python's `difflib`                                  | Standard, easy to display in Streamlit.                                                            |
| Charts                | Streamlit native + **Plotly**                                            | Stick with built-ins unless we have time.                                                          |
| Source control        | **GitHub** (public, MIT license)                                         | Required for submission.                                                                           |
| Secrets               | `.streamlit/secrets.toml` (gitignored) + Streamlit Cloud secrets UI      | Stores vLLM endpoint URL + API key.                                                                |
| AMD docs ingest       | Markdown files we curate by hand into `docs_rag/corpus/`                 | Tiny, controlled, no scraping risk.                                                                |
| Hugging Face piece    | **Optimum-AMD** referenced in patches (not a runtime dep)                | Bonus point for partner integration.                                                               |

**What we are NOT using (avoid scope creep):**

- LangGraph, AutoGen, custom React frontend, FastAPI backend, Postgres, Docker-compose for local stack, GitHub PR creation API, multi-model benchmarks, PDF export, fine-tuning anything.

### AI tooling — when to use which

All three teammates have **GitHub Copilot**. Combined with chat-style assistants, our AI toolkit splits cleanly:

| Tool | Best for | Not for |
|---|---|---|
| **GitHub Copilot (inline)** | Tab-completing boilerplate inside a file you're already editing — Streamlit components, regex variants, Pydantic field declarations, paramiko boilerplate, type hints, docstrings. Fast, no prompt overhead. | Producing whole new files from a paragraph spec — it loses scope quickly. |
| **Copilot Chat (in VS Code)** | Quick "explain this function" or "refactor this block" with the file open. Cheaper than spinning up ChatGPT. | Multi-file changes or running terminal commands — same §0 rules apply if you flip on agent mode. |
| **ChatGPT / Claude / Cursor (chat-style, whole-prompt)** | Executing a Phase prompt from §3 — these are designed for paragraph-spec → multi-file output. **Always prepend §0 Standing Rules.** | Inline single-line completions (slow, tokens wasted). |

**Rule of thumb:** Copilot for keystrokes saved inside files. Chat-style AI for whole phases. Both must obey §0.

---

## 2. Roles (3 people)

We'll call you three: **A**, **B**, **C**. You can swap names later.

### Person A — Cloud + Infrastructure Lead

**Owns: AMD Developer Cloud (primary vLLM endpoint on A's account), sandbox runner code, deployment.**

Responsibilities:

- Sign up for the AMD AI Developer Program on A's own account, claim A's $100 credits, share the endpoint URL + API key with B and C.
- Stand up & keep alive the **primary vLLM Qwen-Coder instance** on A's account.
- Build the **sandbox runner** code (`core/benchmark_runner.py`) — the Python module that SSHs into the sandbox instance, copies a patched script, runs it under `time` + `rocm-smi` in a fresh per-run venv, captures stdout/stderr/runtime/GPU memory, returns JSON.
- Deploy Streamlit app to Community Cloud on Day 5.
- Tracks own ($100) credit budget — checks A's AMD Dev Cloud usage at start of standup. **B and C track their own accounts; nobody is gatekeeper.**

Skills needed: SSH, basic Linux, willingness to read AMD Dev Cloud docs.

**Note (since each teammate has $100):** B and C also know how to stand up the vLLM endpoint — if A's instance dies, B or C can spin up a backup on their own account in ~10 minutes (see §6 contingency).

### Person B — Agents + LLM Plumbing

**Owns: CrewAI agents, prompts, RAG, scoring, report generation.**

Responsibilities:

- All six agents in `agents/`.
- The CrewAI `Crew` definition that wires them together.
- Pattern scanner (`core/pattern_scanner.py`) — pure-Python regex/AST.
- Patch utilities (`core/patch_utils.py`) — apply structured edits + build unified diff via `difflib`.
- ChromaDB ingest of the curated AMD docs corpus.
- Scoring logic (`core/scoring.py`).
- Markdown report generator.
- **Hosts the AMD MI300X sandbox instance on B's $100 account** (A's runner code SSHs into it). B starts/stops the instance and shares its hostname + SSH key with A.
- Tracks own ($100) credit budget at standup.

Skills needed: comfortable with Python, prompt engineering, basic regex.

### Person C — Frontend + Demo + Submission

**Owns: Streamlit app, demo content, video, slides, submission form.**

Responsibilities:

- All of `app.py` and any UI helpers.
- The deliberately-broken demo repo `examples/broken_cuda_demo/`.
- README with hero image, architecture diagram, run instructions, judging-criteria mapping.
- Cover image (1280×720).
- Demo video (≤5 min, see §29 of the project plan for the script).
- Slide deck (8–10 slides).
- Filling out the lablab.ai submission form on Day 6.
- **C's $100 credit account is the recording-day reserve** — keeps a warm instance during video takes and serves as the second backup vLLM endpoint if both A's and B's accounts have issues.
- Tracks own ($100) credit budget at standup.

Skills needed: Streamlit, basic graphic design, video editing (OBS / DaVinci Resolve / iMovie).

### Shared (everyone owns a slice)

- Daily 15-min standup (morning).
- Code review on each other's PRs.
- Testing the demo run end-to-end on Day 5 evening.

---

## 3. Phases — Built So You Can Hand Each One to GPT

Each phase below is a **self-contained prompt block**. Copy the block into GPT (or Claude Code) and it will know enough to produce code. Each phase has: **Owner**, **Day**, **Deliverable**, **GPT-Ready Prompt**, and **Done When**.

> **Before you paste any phase prompt into an AI:**
>
> 1. Make sure you're on a fresh phase branch: `git checkout main && git pull && git checkout -b phase-<N>-<short-name>`
> 2. **Prepend the "Standing Rules" block from §0** (the no-push, no-commit, no-branch, no-secrets-touching rules) to the phase prompt below.
> 3. The AI must end its response with the file summary + suggested git commands (printed, NOT executed). You run the git commands yourself after reviewing the diff.

---

### Phase 0 — Repo Scaffold _(Day 1, morning, ~30 min)_

**Owner:** B (with C reviewing).
**Deliverable:** Empty repo with the structure from §17 of the project plan, MIT license, basic `pyproject.toml` / `requirements.txt`, `.gitignore`, `.streamlit/secrets.toml.example`.

**Branch setup (human runs BEFORE invoking the AI):**

```bash
# Create the GitHub repo (public, MIT) via the GitHub web UI first, then:
git clone <repo-url> rocmforge && cd rocmforge
git checkout -b phase-0-scaffold
```

**GPT-Ready Prompt** _(prepend the Standing Rules block from §0 before sending)_:

> Create the initial scaffold for a Python project called `rocmforge` in the **current working directory**. Do NOT run any git commands.
>
> Use this directory layout: `app.py`, `agents/{scanner,compatibility,knowledge,migration,qa,report}_agent.py`, `core/{repo_loader,pattern_scanner,patch_utils,benchmark_runner,scoring}.py`, `docs_rag/{ingest_docs,retriever}.py`, `examples/broken_cuda_demo/`, `examples/cached_runs/`, `outputs/.gitkeep`.
>
> Files to create:
>
> - `LICENSE` — full MIT license text, copyright "2026 ROCmForge Team".
> - `.gitignore` — use the exact contents specified in §0 of `ROCmForge_Execution_Plan.md` (Python + venv + secrets + Chroma + outputs/\* keeping .gitkeep + examples/cached_runs/ NOT ignored). Do NOT improvise; copy the listed patterns exactly.
> - `requirements.txt`: `streamlit`, `crewai`, `openai`, `chromadb`, `sentence-transformers`, `plotly`, `python-dotenv`, `pydantic`, `gitpython`, `paramiko`.
> - `.streamlit/secrets.toml.example` with placeholder keys: `VLLM_ENDPOINT_URL`, `VLLM_API_KEY`, `AMD_SANDBOX_HOST`, `AMD_SANDBOX_USER`, `DEFAULT_DEMO_MODE`.
> - Each Python module: a single placeholder function with a docstring describing its purpose. `core/patch_utils.py` should reference stdlib `difflib` in its docstring (no external diff library).
> - Top-level `README.md`: one-liner pitch + "run locally" instructions (clone, `python -m venv .venv`, activate, `pip install -r requirements.txt`, `cp .streamlit/secrets.toml.example .streamlit/secrets.toml`, `streamlit run app.py`).
>
> At the end, print:
>
> 1. The list of files you created (relative paths, one per line).
> 2. The exact `git add <files>` command (list each file explicitly — no `git add .`).
> 3. A suggested commit message: `chore: scaffold project structure and tooling`.
> 4. The push command: `git push -u origin phase-0-scaffold`.
>
> **Do NOT run git commands.** Just print them.

**Done when:**

- All files exist locally; `streamlit run app.py` launches without import errors (after `pip install -r requirements.txt`).
- Human has reviewed the diff (`git status`, `git diff --cached` after staging).
- Human has run the printed `git add`, `git commit`, and `git push -u origin phase-0-scaffold` commands themselves.
- A PR is opened on GitHub from `phase-0-scaffold` → `main`.
- After PR review by another teammate, merged to `main`. MIT license now shows in the GitHub UI.

---

### Phase 1 — AMD Developer Cloud + vLLM Endpoint _(Day 1, ~3 hrs)_

**Owner:** A.
**Deliverable:** A reachable HTTPS URL serving Qwen2.5-Coder via vLLM.

**Resources Person A needs to read:**

1. https://www.amd.com/en/developer/resources/cloud-access/amd-developer-cloud.html — sign up, claim $100 credits.
2. https://lablab.ai/ai-tutorials/amd-developer-cloud-host-llm-vllm — exact step-by-step for our exact use case.
3. https://docs.vllm.ai/en/latest/getting_started/amd-installation.html — vLLM ROCm install.

**Steps:**

1. Sign up to AMD AI Developer Program → claim $100 credits.
2. Provision a single MI300X instance.
3. Pull the official ROCm vLLM Docker image.
4. **Generate a strong API key** locally:
   ```bash
   python -c "import secrets; print('sk-' + secrets.token_urlsafe(32))"
   ```
5. Run vLLM with auth + concurrency cap:
   ```bash
   python -m vllm.entrypoints.openai.api_server \
     --model Qwen/Qwen2.5-Coder-7B-Instruct \
     --port 8000 \
     --api-key sk-<generated-key> \
     --max-num-seqs 8
   ```
6. **Expose via Cloudflare Tunnel** (preferred over raw public port — hides the MI300X IP from bot scans, free, no install on the instance beyond `cloudflared`):
   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```
   Or use whatever HTTPS proxy AMD Dev Cloud provides — but **never expose port 8000 directly to the public internet**.
7. Verify with `curl -H "Authorization: Bearer sk-..." <url>/v1/models` and confirm a request **without** the header returns 401.
8. Share endpoint URL + key with B in the team's secrets channel (private, never in the repo).

### Security checklist (do not skip — your $100 credit budget is at risk)

- [ ] vLLM started with `--api-key sk-<32+ random bytes>`
- [ ] `--max-num-seqs 8` cap set so a single attacker can't burn credits at full throttle
- [ ] Endpoint accessed via Cloudflare Tunnel or HTTPS proxy — no raw public port
- [ ] Unauthenticated request returns 401 (verify with curl)
- [ ] API key stored only in Streamlit Cloud secrets and team secrets channel — never committed

**GPT-Ready Prompt (for the test client only — A writes this themselves to verify)** _(prepend §0 Standing Rules; no git commands)_:

> Write a 20-line Python script that calls a vLLM OpenAI-compatible endpoint at `$VLLM_ENDPOINT_URL` with API key `$VLLM_API_KEY`, sends the prompt "Write a Python function that adds two numbers", and prints the response. Use the `openai` package with `base_url` overridden. Also write a second 5-line script that hits the same endpoint **without** the auth header and asserts the response status is 401.

**Done when:** A second team member can run the test script from their machine and get a response, AND the no-auth script confirms 401 is returned.

---

### Phase 2 — Pattern Scanner _(Day 1 afternoon → Day 2 morning, ~3 hrs)_

**Owner:** B.
**Deliverable:** `core/pattern_scanner.py` that takes a directory or single `.py` file and returns a list of issue dicts.

**GPT-Ready Prompt** _(prepend §0 Standing Rules; AI must not run any git commands; AI must end with a file list + suggested `git add` / commit message / `git push` lines for the human to run)_:

> Implement `core/pattern_scanner.py` for the ROCmForge project. Export a function `scan(path: str) -> list[Issue]` where `Issue` is a dataclass with fields: `file: str`, `line: int`, `severity: Literal["high","medium","low"]`, `pattern_id: str`, `snippet: str`, `description: str`. The function must walk `path` (file or dir), read each `.py`, `Dockerfile`, `requirements.txt`, `README*` file, and detect these patterns:
>
> - **High severity:** `nvidia/cuda` in any Dockerfile (pattern_id `docker_nvidia_base`); `bitsandbytes` or `flash-attn` in `requirements.txt` (`dep_cuda_only`); `import bitsandbytes` in Python (`import_bitsandbytes`).
> - **Medium severity:** `.cuda()` method calls in Python (`pytorch_cuda_method`); `torch.cuda.set_device(` (`hardcoded_gpu`); `CUDA_HOME` env reference (`cuda_home_ref`); `nvcc` references in any file (`nvcc_ref`).
> - **Low severity:** README mentions `nvidia-smi` or `CUDA Toolkit` (`readme_cuda_mention`).
>
> Return all issues found. Do NOT use an LLM here — pure Python with `re` and `ast` only. Add a CLI `python -m core.pattern_scanner <path>` that prints results as JSON. Include doctests on three example snippets.

**Done when:** Running it on `examples/broken_cuda_demo/` (built in Phase 3) returns ≥5 issues across ≥3 files.

---

### Phase 3 — Broken Demo Fixture _(Day 2 morning, ~1 hr)_

**Owner:** C.
**Deliverable:** `examples/broken_cuda_demo/` containing `app.py`, `requirements.txt`, `Dockerfile`, `README.md` with deliberate, obvious CUDA dependencies.

**GPT-Ready Prompt** _(prepend §0 Standing Rules; AI must not run any git commands; AI must end with a file list + suggested `git add` / commit message / `git push` lines for the human to run)_:

> Create a deliberately-broken-on-AMD PyTorch demo project under `examples/broken_cuda_demo/`. Files:
>
> - `app.py`: a 30-line PyTorch inference script that loads a tiny ResNet18 from torchvision, calls `.cuda()` twice (once on the model, once on a tensor), and runs one forward pass. Include `torch.cuda.set_device(0)`.
> - `requirements.txt`: `torch`, `torchvision`, `bitsandbytes`, `flash-attn`.
> - `Dockerfile`: `FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04`, installs Python and pip-installs requirements, runs `app.py`.
> - `README.md`: "Run with `nvidia-smi` to verify GPU, then `python app.py`. Requires CUDA Toolkit 12.1."
>
> The script should be valid Python and would run fine on an NVIDIA box. We want exactly 5–7 detectable issues for the scanner.

**Done when:** Phase 2 scanner finds at least 5 issues in this directory.

---

### Phase 4 — Streamlit UI Shell _(Day 2 afternoon, ~3 hrs)_

**Owner:** C.
**Deliverable:** Working `app.py` with all 6 tabs from §12 of the project plan, wired to mocked data. No AI yet.

**GPT-Ready Prompt** _(prepend §0 Standing Rules; AI must not run any git commands; AI must end with a file list + suggested `git add` / commit message / `git push` lines for the human to run)_:

> Build `app.py` for ROCmForge using Streamlit. Layout: a sidebar with input (text area for pasting a Python script + a text input for a GitHub URL + a "Start Migration" button) and a main area with 6 tabs: "Input", "Scan Results", "Migration Patch", "AMD Test", "Benchmark", "Final Report".
>
> For each tab, render with placeholder/mocked data right now. Specifically:
>
> - **Scan Results**: render a list of issue cards using `st.container` with a colored severity badge, file:line, and description. Show a big "AMD Readiness Score: 38/100" header at top.
> - **Migration Patch**: show a unified diff in `st.code(language="diff")` and a list of generated files (Dockerfile.rocm, rocm_setup.md).
> - **AMD Test**: show an agent timeline using `st.status` blocks (Code Analyzer ✓, ROCm Knowledge ✓, Migration Engineer ✓, QA Tester ⏳, Benchmark ⏸, Report ⏸) and a log area below.
> - **Benchmark**: show a simple Plotly bar chart comparing "before" (failed) vs "after" (8.4s, 6.2 GB) and metric tiles.
> - **Final Report**: render a long markdown string and offer a download button for `migration_report.md`.
>
> Use `st.session_state` to persist results between tab switches. The "Start Migration" button should populate `st.session_state.results` with the mocked data so all tabs light up.

**Done when:** `streamlit run app.py` shows a polished dashboard with mock data; all 6 tabs render without errors.

---

### Phase 4.5 — Demo Mode Plumbing _(Day 5 morning, ~1 hr)_

**Owner:** C, with B providing one good cached run from Phase 6's output.
**Deliverable:** A toggle-controlled cached path through the entire app — the safety net for the live demo and the video recording.

**Why this exists:** Live demos break (vLLM OOM, AMD Cloud blip, Streamlit timeout). Demo Mode is also the only sane way to record a clean 5-minute video — you'll need 5–10 takes, and live runs are too inconsistent. It's also a credit saver during dev.

**GPT-Ready Prompt** _(prepend §0 Standing Rules; AI must not run any git commands; AI must end with a file list + suggested `git add` / commit message / `git push` lines for the human to run)_:

> Add a Demo Mode to ROCmForge's Streamlit app. Steps:
>
> 1. Create `examples/cached_runs/broken_cuda_demo.json` containing one full successful results dict (the same shape `agents.run_migration()` returns: `issues`, `patch_text`, `generated_files`, `qa_result`, `score_before`, `score_after`, `report_markdown`, `attempts`).
> 2. In `app.py`, add a sidebar toggle `demo_mode = st.sidebar.toggle("Demo Mode (cached)", value=DEFAULT_DEMO_MODE)` where `DEFAULT_DEMO_MODE` reads from `st.secrets.get("DEFAULT_DEMO_MODE", True)`.
> 3. Add a function `load_cached_results() -> dict` that reads the JSON and, when invoked, plays back the agent timeline by yielding each step with a 0.6s `time.sleep` so the `st.status` blocks animate. Wrap with `st.status(...)` exactly like the live path.
> 4. The "Start Migration" button branches: `if demo_mode: results = load_cached_results()  else: results = run_migration(input)`.
> 5. When demo mode is ON, render a persistent banner at the top: `st.info("📦 DEMO MODE — cached run from May 8, 2026. Toggle off in the sidebar for a live AMD run.")`.
> 6. Add `examples/cached_runs/` to the repo (committed, NOT gitignored).

**Done when:** Toggling Demo Mode ON → "Start Migration" → all six tabs populate from cached data in <5s with the timeline visibly stepping through. Toggle OFF → live flow runs as before.

**Recording strategy:** record the video using Demo Mode for consistent takes. Open the video with one cut showing the toggle OFF and a real run finishing (proves it works live), then switch to Demo Mode for the rest of the recording.

**Default for the public Streamlit URL:** Demo Mode ON, so judges browsing without credentials see a working demo immediately.

---

### Phase 5 — RAG Knowledge Base _(Day 2 evening, ~2 hrs)_

**Owner:** B.
**Deliverable:** `docs_rag/` populated with curated chunks; `retriever.py` exposes `retrieve(query, k=4) -> list[str]`.

**Resources Person B needs to gather (curate by hand, no scraping):**

- ROCm PyTorch install matrix → copy into `docs_rag/corpus/01_rocm_pytorch.md`
- vLLM ROCm install guide → `docs_rag/corpus/02_vllm_rocm.md`
- Hugging Face Optimum-AMD README → `docs_rag/corpus/03_optimum_amd.md`
- AMD Dev Cloud quickstart → `docs_rag/corpus/04_amd_dev_cloud.md`
- Hand-written cheatsheet of common CUDA→ROCm replacements → `docs_rag/corpus/05_migration_cheatsheet.md`

Keep each file under ~200 lines. Total corpus ≤1000 lines.

**GPT-Ready Prompt** _(prepend §0 Standing Rules; AI must not run any git commands; AI must end with a file list + suggested `git add` / commit message / `git push` lines for the human to run)_:

> Implement `docs_rag/ingest_docs.py` and `docs_rag/retriever.py` for ROCmForge. Use ChromaDB persistent client at `./.chroma/` and `sentence-transformers/all-MiniLM-L6-v2` for embeddings.
>
> `ingest_docs.py`: walks `docs_rag/corpus/*.md`, chunks each file by H2 headings (or every ~400 tokens), upserts chunks with metadata `{source, heading}`. CLI entrypoint `python -m docs_rag.ingest_docs`.
>
> `retriever.py`: exposes `retrieve(query: str, k: int = 4) -> list[dict]`, returning `[{text, source, heading, score}]`. Lazily loads the collection on first call.
>
> Include a `__main__` smoke test in `retriever.py` that retrieves "how to install pytorch on rocm" and prints results.

**Done when:** smoke test prints relevant chunks from the corpus.

---

### Phase 6 — Six CrewAI Agents Wired Up _(Day 3, full day)_

**Owner:** B.
**Deliverable:** End-to-end CrewAI flow: input → scanner → analyzer → knowledge → migration → patch → mocked test → report. Real LLM calls to A's vLLM endpoint, but QA still mocked.

**GPT-Ready Prompt** _(prepend §0 Standing Rules; AI must not run any git commands; AI must end with a file list + suggested `git add` / commit message / `git push` lines for the human to run)_:

> Implement six CrewAI agents in `agents/` and a `Crew` definition in `agents/__init__.py` that orchestrates them. Use the OpenAI-compatible LLM client pointing at `$VLLM_ENDPOINT_URL` (read from Streamlit secrets or `.env`). Model name: `Qwen/Qwen2.5-Coder-7B-Instruct`.
>
> Agents (each gets a dedicated file):
>
> 1. `scanner_agent.py` — wraps `core.pattern_scanner.scan()` as a Tool. Role: "Intake & Scanner". Goal: produce a structured issue list.
> 2. `compatibility_agent.py` — takes the issue list, asks the LLM to enrich each issue with severity rationale and a one-line fix hint. Output: same list, enriched.
> 3. `knowledge_agent.py` — for each issue, calls `docs_rag.retriever.retrieve()` and asks the LLM to summarize the AMD-recommended fix in 2 sentences, citing the chunk source.
> 4. `migration_agent.py` — given enriched issues + knowledge, asks the LLM to produce **structured JSON edits**, NOT a raw unified diff. The LLM's output schema is enforced via a Pydantic model:
>
>    ```python
>    class Edit(BaseModel):
>        file: str
>        original_block: str   # exact substring to replace (multi-line ok)
>        replacement_block: str
>        rationale: str
>    class MigrationOutput(BaseModel):
>        edits: list[Edit]
>        new_files: dict[str, str]    # filename -> full content (e.g. Dockerfile.rocm)
>        commentary: str              # human-readable notes shown in the UI
>    ```
>
>    `core/patch_utils.py` then takes `MigrationOutput`, applies each `Edit` to a temp copy of the source, and uses `difflib.unified_diff` to produce the final diff text. **The LLM never writes diff syntax** — this eliminates malformed-hunk crashes that 7B coder models cause.
>
>    Use CrewAI's structured output / `output_pydantic` feature (or a strict system prompt + `json.loads` with retry) to enforce the schema. If parsing fails, retry once with the parser error included in the prompt; on second failure, mark the patch as "manual review required" and continue.
>
>    The Migration agent returns `{patch_text, generated_files: {filename: content}, commentary, edits_raw}` — `patch_text` is built by `patch_utils`, not by the LLM. `edits_raw` is kept for debugging.
>
>    Additionally, before producing edits, scan the issue list for two specific triggers and emit ROCm-specific optimization notes when they fire:
>    - If any issue references `transformers.AutoModelFor` or `AutoTokenizer`, append to `rocm_setup.md` a section titled **"ROCm Optimization Note: vLLM Serving"** with: a one-paragraph explanation that vLLM on ROCm gives 3–5× higher throughput on MI300X for transformer inference, plus a starter command `python -m vllm.entrypoints.openai.api_server --model <detected-model-name> --port 8000`.
>    - If any issue has `pattern_id` `import_bitsandbytes` or `dep_cuda_only` referencing `bitsandbytes`, in the `commentary` field (and in the report) explicitly recommend **Hugging Face Optimum-AMD** as the AMD-native replacement, citing the relevant chunk from the Knowledge agent's RAG output.
>
>    These suggestions must NOT fire when the triggers are absent. Do not generate a full vLLM serving script — just the note and starter command.
>
> 5. `qa_agent.py` — takes patch + original repo dir. For now, MOCK the AMD run: write the patched script to a temp dir, run `python -c "import ast; ast.parse(open('app.py').read())"` to confirm syntactically valid, return `{status: "passed", logs: "...", runtime: 8.4, gpu_memory_gb: 6.2}`. Real AMD execution comes in Phase 8.
> 6. `report_agent.py` — assembles the final markdown report following the template in §7 Agent 6 of the project plan. Saves to `outputs/migration_report.md`.
>
> Top-level entry: `def run_migration(input_path_or_url: str) -> dict` that returns a single results dict consumed by the Streamlit UI.

**Done when:** Calling `run_migration("examples/broken_cuda_demo")` from a Python REPL returns a populated results dict with non-empty patch, score, and report.

---

### Phase 7 — Wire Streamlit to Real Crew _(Day 4 morning, ~2 hrs)_

**Owner:** C, with B available.
**Deliverable:** Streamlit app calls `run_migration` and streams progress.

**GPT-Ready Prompt** _(prepend §0 Standing Rules; AI must not run any git commands; AI must end with a file list + suggested `git add` / commit message / `git push` lines for the human to run)_:

> Modify `app.py` so the "Start Migration" button calls `agents.run_migration()` instead of using mocked data. Wrap the call in `st.status` blocks per agent so users see live progress. Show a spinner. On error, surface the exception in a `st.error` panel. Persist the result in `st.session_state.results` exactly as before so the existing tab rendering code continues to work.

**Done when:** Pasting the broken demo's `app.py` content and clicking "Start Migration" runs the full flow and populates all 6 tabs with real data.

---

### Phase 8 — Real AMD Sandbox Runner _(Day 4 afternoon, ~4 hrs)_

**Owner:** A, with B integrating.
**Deliverable:** `core/benchmark_runner.py` that actually runs migrated code on AMD Dev Cloud sandbox.

**Resources Person A needs:**

- A second AMD Dev Cloud instance (small, ROCm + PyTorch ROCm installed). Keep it stopped, start only on demand.
- SSH key set up so the runner can `paramiko`-connect.

**GPT-Ready Prompt** _(prepend §0 Standing Rules; AI must not run any git commands; AI must end with a file list + suggested `git add` / commit message / `git push` lines for the human to run)_:

> Implement `core/benchmark_runner.py` for ROCmForge. Function `run_on_amd(patched_dir: str, entrypoint: str = "app.py", timeout_sec: int = 120) -> dict`. Behavior:
>
> 1. Start (or reuse) the AMD sandbox instance via the AMD Dev Cloud API or assume a pre-running instance with hostname from env `$AMD_SANDBOX_HOST`.
> 2. Use `paramiko` to SCP the `patched_dir` to `/tmp/rocmforge_run_<uuid>/` on the sandbox.
> 3. **Create a fresh per-run virtualenv** to prevent state pollution across runs. Each run gets its own isolated Python environment that is deleted afterward. SSH-execute:
>    ```bash
>    cd /tmp/rocmforge_run_<uuid> && \
>      python -m venv .venv && \
>      .venv/bin/pip install --no-cache-dir --quiet -r requirements.txt && \
>      /usr/bin/time -v .venv/bin/python <entrypoint>
>    ```
>    Capture stdout, stderr, exit code. The `--no-cache-dir` flag prevents wheel cache pollution; the per-run `.venv` prevents site-packages bleed-over. The base AMD sandbox stays clean — only `python`, `pip`, ROCm, and PyTorch ROCm need to be system-wide.
> 4. Run `rocm-smi --showmeminfo vram --json` before and after to get GPU memory delta.
> 5. Return `{status: "passed"|"failed", logs: str, runtime_sec: float, gpu_memory_gb: float, exit_code: int}`.
>
> Read SSH host/user/key from env vars. Fail loudly if env not set. **Always delete the entire temp dir (including `.venv`) on the sandbox after the run**, even on failure (use a try/finally block).
>
> Update `agents/qa_agent.py` to call this function instead of the mock. If `$AMD_SANDBOX_HOST` is unset, fall back to mock and log a warning.

**Done when:** Running the broken demo through the full flow produces a real "AMD Test: passed, runtime 8.4s, memory 6.2 GB" populated by the actual MI300X instance.

---

### Phase 9 — Self-Healing Loop _(Day 4 evening, ~2 hrs)_

**Owner:** B.
**Deliverable:** When QA fails, the migration agent gets the error and tries again (max 2 retries).

**GPT-Ready Prompt** _(prepend §0 Standing Rules; AI must not run any git commands; AI must end with a file list + suggested `git add` / commit message / `git push` lines for the human to run)_:

> In `agents/__init__.py`, modify the orchestration so that after the QA agent runs, if `result.status == "failed"`, the orchestrator feeds the error logs back to the Migration Engineer agent with a system message: "The previous patch failed with the following error. Produce a corrected patch." Re-run QA on the new patch. Cap at 2 retries. Record each attempt in `result.attempts: list[{patch, qa_result}]`. The Streamlit AMD Test tab should show all attempts.

**Done when:** Manually breaking the migration agent's first patch (e.g., with a prompt-injection in the test repo) causes a second corrected patch to be generated and the second run passes.

---

### Phase 10 — Scoring + Final Report Polish _(Day 5 morning, ~2 hrs)_

**Owner:** B.
**Deliverable:** `core/scoring.py` produces "before" and "after" scores per the rubric in §18.

**GPT-Ready Prompt** _(prepend §0 Standing Rules; AI must not run any git commands; AI must end with a file list + suggested `git add` / commit message / `git push` lines for the human to run)_:

> Implement `core/scoring.py` with `score(issues: list[Issue], qa_result: dict) -> int`. Start at 100. Subtract: 20 for any Dockerfile-NVIDIA-base issue present, 15 for any `.cuda()` issue, 15 for each CUDA-only dependency, 10 for any README-CUDA mention, 20 if `qa_result.status == "failed"`. Floor at 0. Add `score_before(issues)` (treats all issues as present, QA failed) and `score_after(issues_remaining_after_patch, qa_result)` helpers. Wire both into the report agent.

**Done when:** Demo run shows a clear before→after delta (e.g., 38 → 82).

---

### Phase 11 — Deploy + Demo Polish _(Day 5 afternoon, ~3 hrs)_

**Owner:** C with A.
**Deliverable:** Public Streamlit Cloud URL; cover image; clean styling.

Steps:

1. Connect GitHub repo to Streamlit Community Cloud.
2. Add secrets via the Streamlit dashboard (`VLLM_ENDPOINT_URL`, `VLLM_API_KEY`, `AMD_SANDBOX_HOST`, SSH key).
3. Deploy. Test the full flow on the public URL.
4. C designs cover image (Figma/Canva, 1280×720, shows the 38→82 score).
5. Tighten Streamlit styling — consistent colors, clear headings, hide the default menu.

**GPT-Ready Prompt (for styling tweaks)** _(prepend §0 Standing Rules; no git commands; end with file list + suggested git workflow)_:

> Add a custom theme to `.streamlit/config.toml` for ROCmForge: primary color `#ED1C24` (AMD red), background white, font sans-serif. Hide Streamlit's default menu and footer using a small `st.markdown` CSS block at the top of `app.py`.

**Done when:** Public URL works from a fresh browser session; a stranger could click through the demo without help.

---

### Phase 12 — Video, Slides, Submission _(Day 5 evening + Day 6, ~5 hrs)_

**Owner:** C with A and B reviewing.
**Deliverables:**

- 5-minute demo video (script in §29 of project plan)
- 8–10 slide deck
- Lablab submission form filled

**GPT-Ready Prompt (for the slide outline)** _(prepend §0 Standing Rules; no git commands; this prompt produces text content only — no code)_:

> Generate an 8-slide deck outline for ROCmForge for an AI hackathon. Slide 1: title + tagline. Slide 2: the problem (CUDA assumptions block AMD adoption). Slide 3: solution one-liner + architecture diagram description (six agents, vLLM on MI300X, sandbox on AMD). Slide 4: live demo screenshot — scan results. Slide 5: live demo screenshot — patch + AMD test passed. Slide 6: before/after readiness score (38→82). Slide 7: AMD stack used (Dev Cloud, MI300X, ROCm, vLLM, Optimum-AMD reference). Slide 8: team + GitHub URL + thanks. Each slide: title + 3 short bullets max.

**Submission form fields (fill on Day 6 morning):**

- Title: `ROCmForge — Proof-Backed AMD Migration Lab` (≤50 chars ✓)
- Short desc (≤255 chars): "A multi-agent system that scans CUDA PyTorch projects, generates ROCm-compatible patches, runs the migrated code on AMD Developer Cloud, and produces a proof-backed migration report."
- Long desc: ≥100 words version of the pitch from §21.
- Tags: `AI Agents`, `Multi-Agent`, `ROCm`, `AMD Developer Cloud`, `vLLM`, `PyTorch`, `Code Migration`, `Hugging Face`
- Cover image, video, slides, GitHub URL, Application URL.

**Done when:** Submission shows "submitted" on lablab.ai before the Day 6 deadline.

---

## 4. Resources to Gather Now (before Day 1 ends)

### Person A

- [ ] AMD AI Developer Program account → claim $100 credits
- [ ] Read: https://lablab.ai/ai-tutorials/amd-developer-cloud-host-llm-vllm
- [ ] Read: AMD Developer Cloud quickstart docs
- [ ] Generate SSH key for sandbox access
- [ ] Decide on a region/instance type (MI300X)

### Person B

- [ ] Install Python 3.11, set up local venv
- [ ] Read CrewAI docs: https://docs.crewai.com/ — focus on `Agent`, `Task`, `Crew`, `Tool`, custom LLM
- [ ] Read CrewAI + OpenAI-compatible custom endpoint guide
- [ ] Hand-curate the 5 markdown files for `docs_rag/corpus/`
- [ ] Read ChromaDB Python quickstart

### Person C

- [ ] Install Streamlit locally, run a hello-world
- [ ] Skim Streamlit docs on `st.status`, `st.session_state`, `st.tabs`, secrets
- [ ] Decide video tool: OBS (free) recommended
- [ ] Decide slide tool: Google Slides or Figma Slides
- [ ] Sign up for Streamlit Community Cloud, link GitHub
- [ ] Sign up for lablab.ai, register for the hackathon

### Shared

- [ ] Create the GitHub repo (public, MIT) — A or B
- [ ] Create a shared Notion / shared doc / Discord channel for secrets and standups
- [ ] All three: register on lablab.ai for the hackathon and join the team there

---

## 5. Daily Schedule

| Day           | A (Cloud)                                               | B (Agents)                                                                     | C (UI/Demo)                                                                                                       |
| ------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| **1 — May 4** | Sign up, claim credits, vLLM endpoint up (Phase 1)      | Repo scaffold (Phase 0), pattern scanner (Phase 2)                             | Read Streamlit docs, sign up Streamlit Cloud + lablab                                                             |
| **2 — May 5** | Standby for B's integration; provision sandbox instance | RAG ingest (Phase 5)                                                           | Broken demo fixture (Phase 3), UI shell with mocks (Phase 4)                                                      |
| **3 — May 6** | Standby; cost check                                     | Six agents wired up (Phase 6)                                                  | Polish UI components, start architecture diagram                                                                  |
| **4 — May 7** | Sandbox runner (Phase 8)                                | Wire UI ↔ Crew (Phase 7), self-healing loop (Phase 9)                          | Test demo flow end-to-end, take screenshots                                                                       |
| **5 — May 8** | Help C deploy; final cost audit                         | Provide good cached run JSON for Phase 4.5; scoring + report polish (Phase 10) | Demo Mode plumbing (Phase 4.5, morning), deploy (Phase 11), record video using Demo Mode, draft slides (Phase 12) |
| **6 — May 9** | Final smoke test on public URL                          | Final smoke test                                                               | Submit on lablab.ai, post launch tweet                                                                            |

---

## 6. Communication & Defaults

- **Standup:** 9 AM each day, 15 min, on Discord/Zoom. What I did, what I'll do, what's blocking.
- **Code review:** Every PR needs one approval from a non-author. Phase-0 and Phase-12 can be self-merged.
- **Branching:** `main` is always deployable. Feature branches per phase: `phase-N-<short-name>`. **Humans create branches and run all git commands** — see §0 AI Collaboration Protocol. AIs never push, never commit, never branch.
- **AI prompts:** every prompt sent to an AI **must** be prepended with the §0 Standing Rules block. The AI's output must end with a file list + suggested `git add` / commit message / `git push` lines that the human runs after reviewing the diff.
- **When stuck >30 min:** post in the team channel with the exact error. No silent suffering.
- **Secrets:** never commit. Use `.streamlit/secrets.toml` (gitignored) locally and Streamlit Cloud secrets in prod. Same for `.env`, SSH keys, and any file matching `*secret*`/`*key*` — these are gitignored from Day 1 (see §0).
- **vLLM endpoint contingency (we have $300 across 3 accounts):** if A's primary vLLM endpoint dies, B (or C as second fallback) can stand up the same `vllm.entrypoints.openai.api_server` command on their own AMD Dev Cloud account in ~10 minutes. Workflow: B/C generates a new API key, runs the vLLM command with the same model and `--max-num-seqs 8`, exposes via Cloudflare Tunnel, posts the new URL+key in the team secrets channel. C updates Streamlit Cloud secrets in the dashboard — Streamlit redeploys automatically. Document this once on Day 1 so anyone can do it without referencing back to A's setup.
- **Daily credit checks:** at standup, each person reports their AMD Dev Cloud usage. If anyone is past 70% of their $100, rebalance workloads (move sandbox runs to a less-burdened account, or pause non-essential dev instances).

---

## 7. What If We Fall Behind?

Cut in this order (lowest priority first):

1. Self-healing loop (Phase 9) — easy to mock for the video.
2. Real AMD sandbox runner (Phase 8) — keep mocked QA, record cached AMD logs.
3. RAG (Phase 5) — Knowledge agent can call LLM with a hardcoded "AMD migration cheatsheet" prompt instead.
4. GitHub repo input (Option B from §6 of project plan) — only support pasted scripts.

Cuts NOT allowed: the six agents existing, the before/after card, the Streamlit deployment, the video, the submission, **Demo Mode (Phase 4.5)**. Those are the spine.

**Demo Mode is mandatory once Phase 6 produces a working cached run — it's the video safety net and the live-demo fallback.** Do not cut it under any circumstances.

---

## 8. Definition of "Submittable"

By Day 6 noon we must have:

- [ ] Public GitHub repo with MIT license
- [ ] Streamlit Cloud URL that loads
- [ ] `examples/cached_runs/broken_cuda_demo.json` committed and Demo Mode toggle works on the public Streamlit URL
- [ ] One full successful demo run cached (for the video at minimum)
- [ ] 5-min video uploaded
- [ ] Cover image uploaded
- [ ] Slide deck uploaded
- [ ] All form fields filled
- [ ] Submission button clicked

If any one of those is missing, we don't have a submission. Day 5 evening is the dress rehearsal — everything must work then, not on Day 6.
