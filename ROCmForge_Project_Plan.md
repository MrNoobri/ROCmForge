# ROCmForge — Multi-Agent AMD/ROCm Migration Lab

## 0. Hackathon Fit (AMD x lablab.ai, May 4–9, 2026)

ROCmForge is built for the **AMD Developer Hackathon**, an AI-Agents–centered event running on AMD Developer Cloud and ROCm.

- **Theme alignment:** This is an agentic workflow — six specialized CrewAI agents coordinate to scan, migrate, test, and benchmark code. Reasoning is powered by an open-source LLM served via **vLLM on AMD Developer Cloud (MI300X)**.
- **AMD resources used:**
  - AMD AI Developer Program → unlocks **$100 AMD Developer Cloud credits per person ($300 total for the 3-person team)**
  - **AMD Instinct MI300X** GPUs (cloud-hosted, no local hardware)
  - **ROCm** runtime + PyTorch on ROCm for the migrated code
  - **Hugging Face Optimum-AMD** for ROCm-native dependency suggestions (replaces `bitsandbytes` etc.)
- **Timeline (today = 2026-05-04 = Day 1, deadline = 2026-05-09):**
  - Day 1 (May 4): AMD Developer Program signup, claim credits, scaffold repo, stand up vLLM endpoint, build pattern scanner.
  - Day 2 (May 5): Streamlit UI shell, scanner integrated, demo "broken repo" fixture committed.
  - Day 3 (May 6): Migration Engineer agent + patch generation working end-to-end.
  - Day 4 (May 7): QA Tester agent runs migrated code on AMD Cloud sandbox; self-healing loop wired.
  - Day 5 (May 8): Benchmark + Report agents, polish UI, deploy to Streamlit Community Cloud, record demo video, write slides.
  - Day 6 (May 9): Final pass, cover image, submit before deadline.

---

## 1. One-Line Pitch

**ROCmForge is a multi-agent system that takes CUDA/NVIDIA-focused AI code, migrates it toward AMD/ROCm compatibility, tests it on AMD Developer Cloud, benchmarks it, and produces a proof-backed migration report.**

The core idea is simple:

> **Not just code conversion — proof-backed migration.**

---

## 2. The Problem

A lot of machine learning and AI projects are written with NVIDIA/CUDA assumptions.

Common examples:

```python
model = model.cuda()
```

```dockerfile
FROM nvidia/cuda:12.1.0
```

```txt
bitsandbytes
flash-attn
```

These projects may not run properly on AMD GPUs without changes.

For developers and companies that want to try AMD hardware, the hard part is not only rewriting code. The hard part is knowing:

- what will break,
- how to fix it,
- whether the fix actually works,
- what performance looks like on AMD,
- and what still needs manual review.

That is the gap ROCmForge solves.

---

## 3. The Solution

ROCmForge acts like a small migration team made of agents.

The user gives ROCmForge either:

1. a GitHub repository URL, or
2. a single CUDA/PyTorch script.

ROCmForge then:

1. scans the code,
2. finds CUDA/NVIDIA-specific issues,
3. checks ROCm/AMD guidance,
4. generates migration patches,
5. applies the patch in a safe temporary copy,
6. runs the migrated code on AMD Developer Cloud,
7. collects logs and benchmark data,
8. and generates a final migration report.

---

## 4. What Makes ROCmForge Different

Many teams may build a basic “CUDA to ROCm converter.”

ROCmForge should stand out because it is not just a converter.

It has four important differences:

### 4.1 It is proof-backed

It does not only say:

> “This code should work on AMD.”

It tries to actually run the migrated code on AMD Developer Cloud and shows the result.

### 4.2 It uses multiple agents

Each agent has a clear role:

- analyzing,
- migrating,
- testing,
- benchmarking,
- reporting.

This fits the hackathon theme better than a single chatbot.

### 4.3 It has a self-healing loop

If the migrated code fails, the QA agent sends the error back to the migration agent.

The workflow becomes:

```text
Analyze → Migrate → Test → Error → Fix → Test Again → Report
```

Even showing this loop once in the demo will make the project feel much more advanced.

### 4.4 It shows before/after results visually

The app should show a clear before/after difference:

```text
Before:
AMD Readiness: 38/100
Test Status: Failed

After:
AMD Readiness: 82/100
Test Status: Passed
Runtime: 8.4 seconds
GPU Memory: 6.2 GB
```

This is much easier for judges to understand than just showing code.

---

## 5. Target Users

ROCmForge is for:

- developers trying AMD/ROCm for the first time,
- companies with old CUDA-based ML code,
- AI teams exploring AMD Developer Cloud,
- students and researchers with PyTorch projects,
- hackathon teams trying to move workloads onto AMD hardware.

---

## 6. MVP Scope

The MVP should **not** try to migrate every CUDA project in the world.

That is too big.

The MVP should focus on:

- PyTorch inference scripts,
- small LLM or ML demo repos,
- common CUDA-specific patterns,
- simple dependency issues,
- simple Docker/setup migration,
- AMD execution proof on one controlled benchmark.

### Supported MVP Inputs

#### Option A: Paste a Python script

This is the safest for the demo.

Example:

```python
import torch

model = MyModel()
model = model.cuda()

x = torch.randn(1, 3, 224, 224).cuda()
out = model(x)
```

#### Option B: Paste a GitHub repo URL

This is more impressive, but slightly more complex.

The system clones the repo and scans files like:

```text
requirements.txt
Dockerfile
README.md
*.py
```

### MVP Output

The MVP should produce:

1. detected issues,
2. suggested patches,
3. generated ROCm setup file,
4. AMD test result,
5. benchmark chart,
6. final migration report.

---

## 7. The Agents

For the MVP, keep the system to **6 main agents**.

Do not overcomplicate it with 15 agents at the start.

---

### Agent 1: Intake / Repo Scanner Agent

#### Purpose

This agent understands what the user submitted.

It checks whether the input is:

- a GitHub repo,
- a Python script,
- or a zip/project folder.

#### What It Does

It identifies important files:

```text
requirements.txt
pyproject.toml
Dockerfile
README.md
Python files
model files
inference scripts
```

It creates a simple map of the project.

#### Example Output

```json
{
  "project_type": "PyTorch inference project",
  "important_files": ["app.py", "requirements.txt", "Dockerfile"],
  "likely_entrypoint": "app.py"
}
```

---

### Agent 2: CUDA/ROCm Compatibility Analyzer Agent

#### Purpose

This agent finds things that may break on AMD/ROCm.

#### What It Looks For

Common patterns:

```text
.cuda()
torch.cuda
nvidia/cuda Docker image
bitsandbytes
flash-attn
custom CUDA extensions
cupy
triton-specific assumptions
hardcoded GPU IDs
CUDA_HOME
nvcc
```

#### Example Output

```text
Found 5 AMD migration issues:

1. app.py uses model.cuda()
2. app.py creates tensors directly on CUDA
3. Dockerfile uses nvidia/cuda base image
4. requirements.txt includes bitsandbytes
5. README installation instructions assume CUDA
```

#### Why It Matters

This agent gives the project a clear “before” state.

---

### Agent 3: ROCm Knowledge Agent

#### Purpose

This agent gives the migration system AMD/ROCm knowledge.

It should use a small RAG pipeline loaded with selected ROCm and AMD Developer Cloud documentation. Concrete starter corpus (~20–40 markdown chunks, kept tiny):

- ROCm PyTorch install matrix
- vLLM-on-ROCm guide
- **Hugging Face Optimum-AMD** docs (this is critical — it provides the AMD-native replacements for `bitsandbytes`, `flash-attn`, etc.)
- AMD Developer Cloud quickstart
- A hand-curated cheatsheet of common CUDA→ROCm replacements

#### What It Does

It helps answer questions like:

- Which Docker image should be used?
- Is this PyTorch pattern ROCm-safe?
- Is this dependency risky on AMD?
- What setup command should be recommended?
- What benchmark command should be used?

#### Important Note

This agent should not be presented as “just RAG.”

It should be described as:

> “The agent that checks AMD/ROCm documentation before suggesting fixes.”

That sounds more useful and product-like.

---

### Agent 4: Migration Engineer Agent

#### Purpose

This agent writes the actual migration suggestions.

#### What It Does

It generates:

- code patches,
- safer PyTorch device handling,
- ROCm setup instructions,
- alternative dependency suggestions,
- a ROCm-ready Dockerfile,
- and a migration plan.

#### Example Patch

```diff
- model = model.cuda()
+ device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
+ model = model.to(device)
```

```diff
- x = torch.randn(1, 3, 224, 224).cuda()
+ x = torch.randn(1, 3, 224, 224).to(device)
```

#### Output Files It May Generate

```text
Dockerfile.rocm
rocm_setup.md
rocm_requirements.txt
migration.patch
```

#### MVP Rule

For the first version, this agent should generate patches/diffs.

It should not directly push changes to the user’s real GitHub repo.

---

### Agent 5: Build & QA Tester Agent

#### Purpose

This agent tests the migrated code.

This is one of the most important parts of ROCmForge.

#### What It Does

It:

1. creates a temporary copy of the repo/script,
2. applies the migration patch,
3. installs dependencies,
4. runs a small test command,
5. captures logs,
6. checks if the code passes or fails.

#### The Self-Healing Loop

If the test fails, the QA Tester sends the error logs back to the Migration Engineer Agent.

Example:

```text
Runtime error:
NameError: device is not defined
```

Then the Migration Engineer creates a new patch.

The loop becomes:

```text
Patch → Test → Error → Fix → Test Again
```

#### MVP Rule

For the MVP, the QA agent can test one controlled repo or one controlled script.

That is enough.

---

### Agent 6: Benchmark & Report Agent

This can be one agent in the MVP, or two separate agents if there is enough time.

#### Purpose

This agent proves the migrated code actually ran on AMD and makes the final output easy to understand.

#### What It Measures

Depending on the demo:

```text
runtime
GPU memory usage
tokens/sec
latency
model loading time
success/failure status
```

#### Final Report Output

Example:

```text
ROCmForge Migration Report

Project: simple-cuda-inference
Project Type: PyTorch Inference

Before Migration:
AMD Readiness Score: 38/100
Test Status: Failed

Issues Found:
1. Hardcoded .cuda()
2. NVIDIA Docker image
3. CUDA-specific installation instructions

Fixes Applied:
1. Replaced .cuda() with .to(device)
2. Generated ROCm Dockerfile
3. Added AMD setup instructions

After Migration:
AMD Readiness Score: 82/100
AMD Cloud Test: Passed
Runtime: 8.4 seconds
GPU Memory Used: 6.2 GB

Remaining Risks:
1. Dependency compatibility should be manually reviewed
2. Performance tuning may still be needed
```

---

## 8. Optional Extra Agent: GitHub PR Agent

This is a stretch goal, not required for the MVP.

### What It Would Do

It would:

1. create a branch,
2. apply the migration patch,
3. commit the changes,
4. open a pull request.

Example:

```text
Branch: rocmforge/amd-migration
PR Title: Add ROCm compatibility fixes
```

### Should We Build It?

Not at the start.

For a first hackathon, it is better to first build:

```text
Generate Patch
Apply Patch in Sandbox
Run Test
Show Report
```

Only add GitHub PR creation if the main workflow is already working.

---

## 9. How ROCmForge Uses AMD Resources

This part is very important for the hackathon.

ROCmForge should use AMD resources in three clear ways.

---

### 9.1 AMD Developer Cloud for Running the LLM

The agents can use an open-source code model running on AMD Developer Cloud.

Possible models:

```text
DeepSeek Coder
Qwen Coder
Mistral
Llama
```

The app sends prompts to the AMD-hosted model.

Example flow:

```text
Frontend
→ Backend
→ CrewAI agents
→ Open-source LLM on AMD Developer Cloud
→ Agent outputs
```

This shows the project is not just using an external API.

---

### 9.2 AMD Developer Cloud for Testing Migrated Code

The QA Tester Agent should run the patched code on an AMD Developer Cloud instance.

This is the proof stage.

It shows:

```text
The migrated code actually executed on AMD hardware.
```

The app should capture:

- terminal logs,
- success/failure,
- runtime,
- GPU memory usage.

---

### 9.4 Two distinct AMD Cloud roles

To keep judges (and ourselves) clear on what runs where:

1. **LLM Inference instance** — small, persistent. Hosts **Qwen2.5-Coder-7B-Instruct** via **vLLM** with an OpenAI-compatible HTTP endpoint. All CrewAI agents call this endpoint for reasoning and patch generation.
2. **Sandbox / Benchmark instance** — ephemeral, MI300X-class. The QA Tester agent spins this up on demand to actually run the migrated user code, capture logs, and record runtime + memory. Spun down right after each run to conserve credits.

The Streamlit UI is **deployed separately** (Streamlit Community Cloud) and calls the LLM endpoint over HTTPS. This way the UI is reachable at a public URL (required for submission) while all heavy compute remains on AMD hardware.

---

### 9.3 AMD Developer Cloud for Benchmarking

The Benchmark Agent should create a small performance result.

Example:

```text
Model: Qwen 7B
Platform: AMD Developer Cloud
Runtime: 8.4 seconds
Memory: 6.2 GB
Status: Passed
```

A chart can show:

```text
Before: failed
After: passed
Memory usage: 6.2 GB
Runtime: 8.4 sec
```

---

## 10. What the Local RTX 3060 PC Is For

Your local PC is still useful.

Use it for:

- building the frontend,
- writing the backend,
- testing Python logic,
- building the Streamlit app,
- creating the demo video,
- pushing to GitHub,
- testing small examples locally.

But the final proof should come from AMD Developer Cloud, not the RTX 3060.

---

## 11. Recommended Tech Stack

### Frontend

Use:

```text
Streamlit
```

Reason:

- fastest for beginners,
- easy file upload,
- easy charts,
- easy dashboard,
- easy to deploy.

Alternative:

```text
Next.js
```

Use this only if someone on the team is already comfortable with it.

---

### Backend

Use:

```text
Python
FastAPI optional
```

For the first version, Streamlit can call Python functions directly.

You do not need a separate backend at the start.

---

### Agent Framework

Use:

```text
CrewAI
```

Reason:

- simple role-based agents,
- easier for beginners,
- easier to explain in presentation.

Alternative:

```text
LangGraph
```

LangGraph is powerful but may be harder for a first hackathon.

---

### LLM

**Committed choice: Qwen2.5-Coder-7B-Instruct served via vLLM on AMD Developer Cloud.**

Why this specific pick:

- Coder-tuned model → better patch generation than a generic LLM.
- 7B fits comfortably on a single MI300X with credits to spare.
- The lablab tutorial _"AMD Developer Cloud: Host Your First LLM with vLLM"_ covers exactly this path — proven and documented.
- vLLM exposes an OpenAI-compatible API → CrewAI integrates with no custom adapter.

Do not test multiple models. Lock this in on Day 1.

### Hosting (required for submission)

Submission requires a public **Application URL**. Plan:

- Deploy the Streamlit app to **Streamlit Community Cloud** (free, public URL, GitHub-linked).
- Streamlit app stores only the vLLM endpoint URL + an API key in secrets.
- All heavy work (LLM inference, sandbox testing) stays on AMD Dev Cloud.
- Backup: a Hugging Face Space (Streamlit SDK) if Community Cloud's request timeout is too short for long agent runs.

---

### AMD Execution

Use:

```text
AMD Developer Cloud
ROCm
PyTorch
vLLM if serving an LLM
```

---

### Charts

Use:

```text
Plotly
```

or Streamlit’s built-in charts.

Show:

- readiness score before/after,
- runtime,
- memory usage,
- pass/fail status.

---

## 12. UI Design

The app should feel like a migration dashboard.

Recommended pages/tabs:

```text
1. Input
2. Scan Results
3. Migration Patch
4. AMD Test
5. Benchmark
6. Final Report
```

---

### Page 1: Input

User can choose:

```text
Paste GitHub repo URL
Paste CUDA/PyTorch script
Upload a file
```

Button:

```text
Start Migration
```

---

### Page 2: Scan Results

Show:

```text
Project Type: PyTorch Inference
Files Scanned: 14
Issues Found: 5
AMD Readiness Score: 38/100
```

Show issue cards:

```text
High Risk: Dockerfile uses nvidia/cuda
Medium Risk: app.py uses .cuda()
Medium Risk: requirements.txt includes bitsandbytes
```

---

### Page 3: Migration Patch

Show before/after diff.

Example:

```diff
- model = model.cuda()
+ model = model.to(device)
```

Also show generated files:

```text
Dockerfile.rocm
rocm_setup.md
```

---

### Page 4: AMD Test

Show agent timeline:

```text
Code Analyzer: Complete
ROCm Knowledge Agent: Complete
Migration Engineer: Complete
QA Tester: Running on AMD Cloud
Benchmark Agent: Complete
Report Agent: Complete
```

Show logs:

```text
Cloning repo...
Applying patch...
Installing dependencies...
Running test...
Test passed.
```

---

### Page 5: Benchmark

Show:

```text
Runtime: 8.4 sec
GPU Memory: 6.2 GB
Status: Passed
```

Show simple charts.

---

### Page 6: Final Report

Show a clean report and allow download as:

```text
migration_report.md
migration_report.pdf
```

---

## 13. Demo Strategy

The demo must be reliable.

Do not depend on a random GitHub repo live during the demo.

Use a controlled repo that your team creates.

### Demo Repo

Create a small repo called something like:

```text
cuda-pytorch-demo-broken
```

Put in:

```text
app.py
requirements.txt
Dockerfile
README.md
```

Make sure it contains known CUDA issues:

```python
model.cuda()
tensor.cuda()
```

```dockerfile
FROM nvidia/cuda
```

```txt
bitsandbytes
```

Then ROCmForge scans and fixes this controlled example.

### Demo Flow

1. Paste repo/script.
2. Agents start.
3. Scanner finds CUDA issues.
4. Migration Engineer creates patch.
5. QA Tester runs patched code on AMD.
6. Benchmark chart appears.
7. Final report is generated.

---

## 14. “Killer Feature”: Live Benchmark Diff

The visual highlight should be the **Live Benchmark Diff**.

It should show:

```text
Before Migration
- AMD readiness: 38/100
- Test status: Failed
- Reason: CUDA-specific code

After Migration
- AMD readiness: 82/100
- Test status: Passed
- Runtime: 8.4 sec
- GPU memory: 6.2 GB
```

This is the part judges will remember.

---

## 15. Project Roadmap

### Phase 1: Basic Scanner

Build a Python script that can detect:

```text
.cuda()
torch.cuda
nvidia/cuda
bitsandbytes
flash-attn
CUDA_HOME
nvcc
```

Output issues as JSON.

---

### Phase 2: Basic UI

Build Streamlit dashboard with:

```text
input box
scan button
issue cards
score
```

---

### Phase 3: Patch Generation

Use the LLM to generate:

```text
migration.patch
Dockerfile.rocm
rocm_setup.md
```

Start with simple replacements.

---

### Phase 4: Sandbox Test

Create a temporary folder.

Apply the patch.

Run a small test command.

Capture logs.

---

### Phase 5: AMD Cloud Test

Move the test to AMD Developer Cloud.

Collect:

```text
runtime
memory
logs
status
```

---

### Phase 6: Benchmark Dashboard

Add charts and before/after comparison.

---

### Phase 7: Final Report

Generate a markdown report.

Optional: export PDF.

---

### Phase 8: Polish + Video

Prepare:

```text
GitHub repo
live app
demo video
slides
README
```

---

## 16. Team Split

### Person 1: Frontend + Demo + Presentation

Responsibilities:

- Streamlit UI,
- dashboard layout,
- charts,
- demo flow,
- slides,
- final video.

### Person 2: Agents + Backend

Responsibilities:

- CrewAI setup,
- agent prompts,
- scanner logic,
- patch generation,
- report generation.

### Person 3: AMD Cloud + Testing

Responsibilities:

- AMD Developer Cloud setup,
- ROCm environment,
- LLM/model serving,
- benchmark script,
- collecting logs/results.

---

## 17. File Structure

Suggested repo structure:

```text
rocmforge/
├── app.py
├── agents/
│   ├── scanner_agent.py
│   ├── compatibility_agent.py
│   ├── knowledge_agent.py
│   ├── migration_agent.py
│   ├── qa_agent.py
│   └── report_agent.py
├── core/
│   ├── repo_loader.py
│   ├── pattern_scanner.py
│   ├── patch_utils.py
│   ├── benchmark_runner.py
│   └── scoring.py
├── docs_rag/
│   ├── ingest_docs.py
│   └── retriever.py
├── examples/
│   └── broken_cuda_demo/
├── outputs/
│   ├── migration_report.md
│   ├── migration.patch
│   └── benchmark.json
├── requirements.txt
├── LICENSE              # MIT — required for the public repo
├── .streamlit/
│   └── secrets.toml.example   # vLLM endpoint URL + key (real one in Streamlit Cloud)
└── README.md            # judges read this first; see §27
```

---

## 18. Scoring Logic

The AMD Readiness Score does not need to be perfect.

It only needs to be explainable.

Example:

```text
Start from 100.

Subtract:
- 20 points for NVIDIA Docker base image
- 15 points for hardcoded .cuda()
- 15 points for CUDA-only dependency
- 10 points for CUDA-specific README/setup
- 20 points for test failure
```

Then after migration:

```text
Add points back when fixed.
```

Example:

```text
Before: 38/100
After: 82/100
```

---

## 19. Risks and How to Handle Them

### Risk 1: Random repos are too hard to migrate

Solution:

Support controlled demo repos first.

Say clearly:

> “MVP focuses on common PyTorch inference migration patterns.”

---

### Risk 2: AMD Cloud setup takes time

Solution:

Prepare the AMD instance before the demo.

Do not start setup live.

---

### Risk 3: LLM-generated patch is wrong

Solution:

Show patch suggestions and sandbox testing.

Do not push directly to real repositories.

---

### Risk 4: GitHub PR creation is too much

Solution:

Keep it as a stretch goal.

MVP only generates patch files.

---

### Risk 5: RAG over documentation becomes too complex

Solution:

Start with a small local knowledge base:

```text
ROCm PyTorch notes
vLLM ROCm notes
common CUDA-to-ROCm migration notes
known dependency issues
```

---

## 20. Stretch Goals

Only attempt these after the core demo works.

### Stretch Goal 1: GitHub Pull Request Agent

Automatically creates a branch and pull request.

### Stretch Goal 2: Multi-Model Benchmark

Test Qwen vs Mistral vs DeepSeek Coder on AMD Cloud.

### Stretch Goal 3: Cost Optimizer

Estimate credit usage and warn if the user is wasting GPU time.

### Stretch Goal 4: More Repo Types

Support:

```text
training scripts
FastAPI inference apps
Hugging Face Transformers apps
vLLM serving apps
```

### Stretch Goal 5: Export PDF Report

Generate a polished PDF report for submission or enterprise use.

---

## 21. Final Pitch Script

Use this for your demo or presentation:

> Developers have years of AI and ML code written around NVIDIA/CUDA assumptions. Moving that code to AMD/ROCm can be difficult because the developer has to find hardware-specific code, rewrite it, test it, debug it, and then measure performance.
>
> ROCmForge solves this with a multi-agent workflow. The Code Analyzer scans the repo, the ROCm Knowledge Agent checks AMD guidance, the Migration Engineer writes patches, the QA Tester runs the migrated code on AMD Developer Cloud, and the Benchmark Agent produces a before/after report.
>
> The key difference is that ROCmForge does not just suggest code changes. It proves whether the migrated code actually runs on AMD hardware.

---

## 22. What to Say If Judges Ask “Is This Fully Automatic?”

Answer:

> Not fully yet. Our MVP focuses on common PyTorch inference migration patterns. It safely generates patches, applies them in a sandbox, runs tests on AMD Developer Cloud, and reports the result. Full automatic GitHub PR creation is a planned next step.

This sounds honest and professional.

---

## 23. What to Say If Judges Ask “Why AMD?”

Answer:

> AMD is central to the project. We use AMD Developer Cloud to run the open-source model behind the agents, test the migrated code on AMD hardware, and benchmark the result. The whole product is designed to help more developers adopt AMD/ROCm.

---

## 24. What to Say If Judges Ask “Why Agents?”

Answer:

> Migration is not one simple task. It involves reading the project, understanding hardware-specific problems, checking documentation, rewriting code, testing, debugging, benchmarking, and reporting. We split those responsibilities into specialized agents that coordinate with each other.

---

## 25. MVP Success Criteria

The project is successful if the demo can show:

- a CUDA/PyTorch script or repo being scanned,
- at least 3 detected AMD blockers,
- at least 2 generated patches,
- a safe sandbox test,
- a real AMD Cloud run or benchmark,
- a before/after readiness score,
- a final migration report.

---

## 26. Best Final Version of the Idea

The strongest final description is:

> **ROCmForge is a proof-backed multi-agent migration lab for AMD. It analyzes CUDA-based PyTorch projects, generates ROCm-compatible patches, tests the migrated code on AMD Developer Cloud, benchmarks the result, and produces a clear migration report.**

---

## 27. Submission Checklist

Required submission artifacts (from the official spec):

| Artifact                   | Status / Notes                                                                                                                                |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Project Title              | Draft: `ROCmForge — Proof-Backed AMD Migration Lab`                                                                                           |
| Short Description          | Draft: _Multi-agent system that migrates CUDA PyTorch code to AMD/ROCm, tests it on AMD Developer Cloud, and produces a proof-backed report._ |
| Long Description           | ≥100 words. Lead with the agentic workflow, then AMD resources used, then the killer feature (live before/after diff).                        |
| Technology & Category Tags | `AI Agents`, `Multi-Agent`, `ROCm`, `AMD Developer Cloud`, `vLLM`, `PyTorch`, `Code Migration`, `Hugging Face`                                |
| Cover Image                | 1280×720 PNG. Show the before/after readiness score visually.                                                                                 |
| Video Presentation         | ≤5 min. See §29 for script.                                                                                                                   |
| Slide Presentation         | 8–10 slides: problem → architecture → live demo screenshots → AMD usage → judging-criteria map → team.                                        |
| Public GitHub Repository   | MIT license, README with run instructions, architecture diagram, screenshots.                                                                 |
| Demo Application Platform  | Streamlit Community Cloud                                                                                                                     |
| Application URL            | Set after deploy on Day 5.                                                                                                                    |

---

## 28. How ROCmForge Maps to Judging Criteria

| Criterion                     | How ROCmForge scores                                                                                                                                                                                                 |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Application of Technology** | Qwen2.5-Coder-7B served via vLLM on **AMD MI300X**; six CrewAI agents call it via OpenAI-compatible API; QA agent runs migrated code on a separate AMD instance. End-to-end use of the AMD AI stack — not a wrapper. |
| **Presentation**              | Live before/after AMD-readiness diff; clean Streamlit dashboard at a public URL; tight 5-minute video; slide deck.                                                                                                   |
| **Business Value**            | Migration friction is the #1 blocker for AMD adoption in AI/ML. ROCmForge collapses days of engineer time into minutes — a real onboarding accelerator for AMD's ecosystem.                                          |
| **Originality**               | Self-healing patch loop (QA error → re-prompt Migration agent → re-test); the _"proof-backed"_ framing — it actually executes the migrated code on AMD, not just suggests changes.                                   |

---

## 29. Demo Video Script (5 minutes)

| Time      | Beat                                                                                                                                                                                               |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0:00–0:30 | Problem: CUDA assumptions everywhere, AMD adoption is blocked by migration cost.                                                                                                                   |
| 0:30–1:00 | ROCmForge in one sentence + architecture diagram (six agents, AMD Dev Cloud).                                                                                                                      |
| 1:00–3:30 | Live run on the controlled "broken" demo repo: paste URL → scanner finds 5 CUDA issues → Migration agent generates patches → QA agent runs migrated code on AMD MI300X → benchmark numbers appear. |
| 3:30–4:15 | Self-healing loop: deliberately break the patch, show QA failure → re-prompt → green.                                                                                                              |
| 4:15–4:45 | Before/after readiness card: 38/100 → 82/100.                                                                                                                                                      |
| 4:45–5:00 | Team + AMD partner shoutout (Developer Cloud, ROCm, Hugging Face Optimum-AMD) + repo URL.                                                                                                          |

---

## 30. AMD Developer Cloud Credit Budget ($300 total — $100 × 3 people)

Each teammate gets their own $100 AMD AI Developer Program credit, kept on their own account. We do **not** pool credits into one account — that would put all eggs in one basket. Instead, we split the workloads across accounts so a billing/auth issue on one account never kills the demo.

### Per-account allocation

| Account | Workload | Estimated cost |
|---|---|---|
| **Person A** (primary infra) | Persistent vLLM (Qwen-Coder-7B) instance for ~5 days | ~$60 |
| **Person A** | Buffer / contingency | ~$40 |
| **Person B** (sandbox owner) | AMD MI300X sandbox for QA agent runs (~10 demo runs) | ~$40 |
| **Person B** | Backup vLLM endpoint if A's goes down | ~$30 reserved (only spent if needed) |
| **Person B** | Buffer | ~$30 |
| **Person C** (demo + recording) | Recording-day instance kept warm during video takes | ~$30 |
| **Person C** | Backup vLLM if A and B both fail | ~$30 reserved |
| **Person C** | Buffer | ~$40 |

Total earmarked: ~$130 active spend + ~$170 in reserves.

### Why split across accounts (not pool)

- **Resilience:** If A's vLLM endpoint dies on Day 5, B can spin up the same `vllm.entrypoints.openai.api_server` on B's account in ~10 minutes, hand the new URL+key to C, and Streamlit Cloud secrets get updated. No single point of failure.
- **Parallel work:** B can iterate on agent prompts against A's main endpoint *while* B keeps a small dev instance up on B's own account for testing things that would interrupt the main vLLM (model swaps, restarts, etc.).
- **No coordination overhead:** Nobody has to ask permission to spin something up. Each person manages their own budget.

### Discipline rules (still apply per account)

- Stop instances when not in use — even with $300 total, an idle MI300X overnight is ~$15+ wasted per person.
- Pre-build the migrated-code dependencies as a wheelhouse locally; only `pip install --no-index --find-links wheelhouse/` on cloud where possible.
- Cache LLM responses during dev (use the Demo Mode JSON from Phase 4.5) so UI iteration doesn't re-bill A's vLLM.
- Each person checks their AMD Dev Cloud usage dashboard at start of standup. If anyone is past 70% of their $100, the team rebalances workloads.

---

## 31. Additional Risks (extends §19)

### Risk 6: AMD Cloud queue / region full during demo recording

Pre-record a clean run on Day 5 morning. Keep all logs and outputs cached so the dashboard works even if the cloud blips during the live demo.

### Risk 7: Streamlit Community Cloud request timeout kills long agent runs

Mitigation: stream agent updates progressively (Streamlit `st.status` blocks), keep total wall-clock under ~60s per stage by capping LLM calls and running QA tests asynchronously with cached results for the demo repo.

### Risk 8: Solo / under-staffed execution

If working solo: drop the GitHub PR stretch goal entirely, drop multi-model benchmark, keep Streamlit's stock components (no custom CSS), and reuse cached AMD run logs in the demo instead of live-running.
