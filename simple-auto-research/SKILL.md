---
name: simple-auto-research
description: Autonomous ML research — from topic to PDF paper. Searches literature, finds and reproduces baselines, implements improvements, runs experiments, writes LaTeX paper.
---

# Simple Auto-Research

You are conducting autonomous ML research. The user gives you a topic. You deliver a complete LaTeX paper backed by real experiments. Follow every step below precisely.

## Progress Tracking

At the START of the skill, create tasks for all 6 phases using TaskCreate:
1. "Phase 1: Find best baseline"
2. "Phase 2: Propose method"
3. "Phase 3: Implement"
4. "Phase 4: Formal experiments"
5. "Phase 5: Write paper"
6. "Phase 6: Self-review"

Update each task to `in_progress` when starting it and `completed` when done. This lets the user see your progress.

## Trigger Conditions

Activate this skill when the user says any of:
- "research [topic]"
- "write a paper about [topic]"
- "run auto-research on [topic]"

## Setup

Before any research begins, create the workspace and verify prerequisites.

1. Derive a topic slug from the user's topic (lowercase, hyphens, no spaces). Example: "vision transformer for audio" becomes `vision-transformer-for-audio`.

2. Create the workspace directory and all subdirectories:
   ```bash
   WORKSPACE="research-{topic-slug}"
   mkdir -p "$WORKSPACE"/{tools,papers,repos,code,experiments,figures,paper}
   ```

3. Copy the research tools into the workspace:
   ```bash
   cp ~/.claude/skills/simple-auto-research/research_tools.py "$WORKSPACE/tools/"
   ```

4. Copy the paper template:
   ```bash
   cp ~/.claude/skills/simple-auto-research/templates/paper_template.tex "$WORKSPACE/paper/main.tex"
   ```

5. Create an empty research notebook:
   ```bash
   echo "# Research Notes: {topic}" > "$WORKSPACE/notes.md"
   echo "" >> "$WORKSPACE/notes.md"
   echo "## Decisions Log" >> "$WORKSPACE/notes.md"
   ```

6. Verify Python 3.11+ is available:
   ```bash
   python3 --version
   ```
   If Python is not 3.11+, warn the user and stop.

7. Check if pdflatex is available:
   ```bash
   which pdflatex
   ```
   If not found, warn the user: "pdflatex not found. Paper will be written but PDF compilation will be skipped. Install texlive-full to enable compilation."

8. Create a project-specific virtual environment:
   ```bash
   cd "$WORKSPACE"
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   ```
   All subsequent `python` and `pip` commands use this venv. When installing baseline repo dependencies, use `pip install -r requirements.txt` inside this venv.

9. Detect available GPUs and select which ones to use:
   ```bash
   python3 -c "
   import subprocess, json
   try:
       out = subprocess.check_output(['nvidia-smi', '--query-gpu=index,name,memory.total,memory.used', '--format=csv,noheader'], text=True)
       gpus = []
       for line in out.strip().split('\n'):
           idx, name, total, used = [x.strip() for x in line.split(',')]
           used_mb = int(used.replace(' MiB', ''))
           gpus.append({'index': idx, 'name': name, 'total': total, 'used_mb': used_mb, 'free': used_mb < 1000})
       print(json.dumps(gpus, indent=2))
   except: print('[]')
   "
   ```
   Pick GPUs that are free (used < 1000 MB). Record in notes.md which GPUs are assigned.
   Use these GPU IDs in all `run-experiment --gpu` calls throughout the project.
   If no GPUs are free, warn the user and ask which GPUs to use.

All subsequent commands assume you are inside `$WORKSPACE` or use paths relative to it.

---

## Phase 1: Find the Best Baseline (~1 hr)

This is the MOST CRITICAL phase. A bad baseline means everything downstream fails. Do not rush this.

### Step 1: Broad Literature Survey

Run 3-4 search rounds with different keyword combinations to maximize coverage:

Round 1 — exact topic keywords:
```bash
python tools/research_tools.py search-papers \
  --query "<core task + method keywords from topic>" \
  --max-results 20 \
  --year-min 2023 \
  --output papers/survey_round1.json
```

Round 2 — broader/alternative terms:
```bash
python tools/research_tools.py search-papers \
  --query "<broader task name + alternative method names>" \
  --max-results 20 \
  --year-min 2023 \
  --output papers/survey_round2.json
```

Round 3 — specific baseline methods:
```bash
python tools/research_tools.py search-papers \
  --query "<well-known baseline method names for this task>" \
  --max-results 20 \
  --year-min 2022 \
  --output papers/survey_round3.json
```

Round 4 — recent surveys:
```bash
python tools/research_tools.py search-papers \
  --query "survey benchmark <task name>" \
  --max-results 15 \
  --year-min 2023 \
  --output papers/survey_round4.json
```

After each round, read the output JSON file. For each paper, check:
- Does it have a clearly stated method with experiment results?
- Does the abstract mention specific datasets and metrics?
- Does it mention code availability or a GitHub link?

Filter down to **3-5 baseline candidates**. Record them in `notes.md`:

```markdown
## Baseline Candidates

### Candidate 1: [Paper Title]
- Year: 2024
- Citation count: 45
- Key result: [main metric and value on main dataset]
- Repo URL: https://github.com/...
- Why promising: clear experiments, public code, recent

### Candidate 2: ...
```

### Step 2: Evaluate Each Candidate

For EACH of the 3-5 candidates, do all of the following:

**a) Read the paper's experiment section carefully.**
Look for these specific details:
- Dataset name and version
- Exact metrics used (name, how computed, how aggregated)
- Number of random seeds or runs
- Training details: optimizer, learning rate, batch size, number of epochs
- Early stopping criteria
- Hardware used (GPU type, training time)

If any of these are vague (e.g., "we train for sufficient epochs", "standard hyperparameters"), mark the candidate as WEAK.

**b) Find the corresponding GitHub repository.**
```bash
python tools/research_tools.py search-repos \
  --query "[paper title] [first author last name]" \
  --max-results 10 \
  --output papers/repos_candidate1.json
```
Read the output JSON. Check:
- Does the repo have a README with install/run instructions?
- When was it last updated? (Stale repos > 2 years old are risky.)
- How many stars? (More stars = more community validation.)
- Are there open issues complaining about reproduction?

**c) Clone the most promising repo.**
```bash
git clone --depth 1 https://github.com/owner/repo repos/candidate1
```

**d) Read the code.**
Read the main training script, model definition, and data loading code. Check:
- Does the code match what the paper describes?
- Are there hardcoded tricks not mentioned in the paper (e.g., special normalization, data augmentation)?
- Is the codebase clean enough to modify?

**e) Check GitHub issues for reproduction problems.**
Search the issues page (if accessible) or look at README for any "known issues" about reproducing results.

**f) Score each candidate** in `notes.md`:
- Experiment clarity: 1-5
- Code quality: 1-5
- Reproduction likelihood: 1-5
- Total score

Pick the candidate with the highest total score.

### Step 3: Reproduce the Baseline (CRITICAL)

This step determines whether you can proceed. Do not skip or shortcut it.

1. Copy the selected baseline repo into the working code directory:
   ```bash
   cp -r repos/candidate1/* code/
   ```

2. Read the README carefully. Install all dependencies:
   ```bash
   cd code && pip install -r requirements.txt
   ```
   If there is a `setup.py` or `pyproject.toml`:
   ```bash
   cd code && pip install -e .
   ```

3. Run the baseline training and evaluation exactly as described in the README or paper:
   ```bash
   cd code && python train.py --dataset <name> --seed 42
   ```
   Adapt the command to match the repo's actual interface.

4. Read the output. Compare reproduced numbers with the paper's reported numbers.

5. **Decision gate:**
   - **Gap < 2%**: Baseline CONFIRMED. Proceed to Step 4.
   - **Gap 2-5%**: Acceptable with caveats. Note the discrepancy in `notes.md` and proceed.
   - **Gap > 5% or code errors**:
     - Spend a MAXIMUM of 15 minutes debugging. Common fixes:
       - Wrong dataset version or split
       - Missing preprocessing step
       - Different random seed
       - Dependency version mismatch
     - If fixed within 15 minutes: re-run and re-check.
     - If NOT fixed: abandon this candidate. Go to the next candidate from Step 2.
     - If ALL candidates fail: go back to Step 1 with broader search queries.

6. Record the reproduction result in `notes.md`:
   ```markdown
   ## Baseline Reproduction

   Selected: [Paper Title]
   Repo: https://github.com/...
   Paper reports: accuracy=0.854, F1=0.821
   We reproduced: accuracy=0.847, F1=0.815
   Gap: accuracy -0.7%, F1 -0.6% — CONFIRMED
   ```

### Step 4: Lock the Experiment Protocol

This is the IMMUTABLE experiment protocol. Once written, it CANNOT be changed for the rest of the research.

Record the following in `notes.md` under a dedicated section:

```markdown
## Experiment Protocol (LOCKED)

### Dataset
- Name: [exact name and version]
- Split method: [e.g., random 80/10/10, k-fold, predefined split]
- Preprocessing: [exact steps]

### Evaluation
- Metrics: [exact metric names and how they are computed]
- Number of seeds/runs: [e.g., 3 seeds: 42, 123, 456]
- Reported as: [mean +/- std]

### Training
- Optimizer: [e.g., Adam]
- Learning rate: [e.g., 1e-3]
- Batch size: [e.g., 32]
- Epochs: [e.g., 200]
- Scheduler: [e.g., ReduceLROnPlateau, patience=10]
- Early stopping: [e.g., patience=20 on val loss]

### Hardware
- GPU: [e.g., NVIDIA A100 40GB]
- Training time per run: [e.g., ~45 min]

### Baseline Numbers (reproduced)
- accuracy: 0.847
- F1: 0.815
```

Every experiment from this point forward MUST use these exact settings. If you discover the settings are wrong, do NOT change them — instead, note the discrepancy and explain it in the paper.

### Step 5: Extract the Full Experiment Blueprint from the Baseline Paper

This is CRITICAL. Your paper's experiment section must mirror the baseline paper's structure.

1. **Download the baseline paper PDF** (from arXiv, Semantic Scholar, or the repo).
   Use WebFetch to read the paper, or download the PDF if available in the repo.

2. **Read the ENTIRE experiment section** of the baseline paper. Record in `notes.md`:

   ```markdown
   ## Baseline Paper Experiment Blueprint

   ### Datasets Used
   - [List ALL datasets the baseline paper evaluates on]
   - You MUST evaluate on the SAME datasets as the baseline paper

   ### Main Results Table Structure
   - Rows: [what methods are compared — list all baseline methods from the paper]
   - Columns: [what metrics are reported]
   - Your main table must follow this exact structure, adding your method as a new row

   ### Ablation Studies in Baseline Paper
   - [List EVERY ablation table/figure in the paper]
   - [e.g., "Table N: effect of hyperparameter X (values tested)"]
   - [e.g., "Figure N: training/convergence curves"]
   - You MUST include analogous ablations for your method

   ### Analysis / Visualization in Baseline Paper
   - [List EVERY analysis figure/table beyond main results and ablations]
   - [e.g., "Figure N: performance vs input length"]
   - [e.g., "Table N: inference speed comparison"]
   - Include analogous analyses where applicable

   ### Other Baselines Compared
   - [List all methods the paper compares against, with their paper references]
   - Your paper should compare against the same baselines (use numbers from the baseline paper for methods you don't reimplement)
   ```

3. **Create an experiment checklist** in `notes.md`:

   ```markdown
   ## Experiment Checklist (from baseline paper)
   [Generate this list by reading the baseline paper. One item per table/figure in their experiment section.]
   - [ ] Main results on [each dataset from the paper] (all metrics)
   - [ ] [Each ablation study from the paper, adapted for your method]
   - [ ] [Each analysis/visualization from the paper]
   - [ ] [Any additional experiment specific to your proposed method]
   ```

   This checklist is your TODO for Phases 3-4. Every item must be checked off before writing the paper.

---

## Phase 2: Propose Method (~15 min)

Based on the research gap you identified during the literature survey:

1. Write the method proposal in `notes.md`:
   ```markdown
   ## Proposed Method

   ### Core Idea (one sentence)
   [e.g., "Add edge-aware attention to the message passing layer to capture bond-level interactions."]

   ### What Changes from Baseline
   - [Specific change 1: e.g., "Replace module X with proposed module Y"]
   - [Specific change 2: e.g., "Add bond feature encoding in preprocessing"]

   ### Expected Effect
   [e.g., "Expected 1-3% improvement on main metric due to better modeling of X"]

   ### Experiment Plan
   1. baseline — already have numbers from Phase 1
   2. proposed — full method with all changes
   3. ablation_no_edge_attn — proposed minus edge attention
   4. ablation_no_bond_feat — proposed minus bond features
   ```

2. Verify the plan is feasible:
   - Can you implement each change by modifying the existing codebase?
   - Are the ablations well-defined (each removes exactly one component)?
   - Will each experiment run within the time budget of the locked protocol?

---

## Phase 3: Implement (~1-2 hr)

Work directly in the `code/` directory. Use CC's native file read/edit capabilities.

### Development Loop

1. **Make a change.** Edit the relevant source files in `code/` to implement one part of the proposed method.

2. **Run a quick test** to verify nothing is broken:
   ```bash
   cd code && python train.py --dataset <name> --seed 42 --epochs 5
   ```
   Use a small number of epochs (5-10) just to check the code runs without errors.

3. **See error, fix, repeat.** Read the traceback, edit the file, re-run. This is the core development loop. Keep iterating until the code runs cleanly.

4. **Verify baseline is not broken.** Before moving on, run the full baseline configuration (same command as Phase 1 Step 3) and confirm the numbers are within 1% of what you reproduced earlier. If baseline numbers have changed, you introduced a bug — find and fix it.

5. **Run proposed method.** Execute the proposed configuration:
   ```bash
   cd code && python train.py --dataset <name> --seed 42 --method proposed
   ```
   Adapt the command to match how you parameterized the method selection.

6. **Sanity check results.** The proposed method should produce numbers in a reasonable range (not NaN, not 0%, not 100%). If results are nonsensical:
   - Check for gradient explosion/vanishing (look at loss values over epochs)
   - Check data loading (print shapes and sample values)
   - Check the model architecture (print parameter count, verify forward pass)
   - Fix and re-run

7. **Iterate until proposed method produces reasonable results.** "Reasonable" means the method runs to completion and produces metrics in a plausible range — they do not need to beat the baseline yet.

---

## Phase 4: Formal Experiments (~1-2 hr)

Follow the locked experiment protocol from Phase 1 EXACTLY. No deviations.

**IMPORTANT: Follow the Experiment Checklist from Phase 1 Step 5. Every item must be completed.**

### Run Order

Work through the Experiment Checklist systematically. For each experiment:

```bash
python tools/research_tools.py run-experiment \
  --workdir code/ \
  --cmd "<training command adapted from baseline repo>" \
  --gpu <assigned_gpu_id> \
  --timeout 3600 \
  --output-dir experiments/<condition>/<dataset>/seed<N>
```

Run ALL datasets listed in the checklist, ALL seeds, ALL conditions (baseline, proposed, ablations).
The exact commands, datasets, seeds, and hyperparameters come from the locked experiment protocol — not from hardcoded examples.

### After EACH Experiment Completes

Do ALL of the following every time an experiment finishes — not just at the end:

1. **Read the result** immediately:
   ```bash
   cat experiments/<name>/result.json
   ```

2. **Sanity check**: Are metrics reasonable? Did it complete without errors?

3. **If failed**: Read stderr, go back to Phase 3 to fix code, re-run. Never change protocol.

4. **Update the Experiment Checklist** in `notes.md` — mark the completed item with `[x]` and record the numbers:
   ```markdown
   - [x] Main results on Dataset1: metric1=X.XXX (baseline), metric1=X.XXX (proposed)
   - [ ] Main results on Dataset2 (running...)
   - [ ] Ablation: [component name]
   ```

5. **Update the results table** in `notes.md` with the new numbers. Keep a running table that grows as experiments complete.

6. **Check what's left**: Re-read the checklist. What hasn't been run yet? Start the next experiment.

This loop ensures you always know where you are, what numbers you have, and what's missing — even if experiments take hours.

### Collect Results

After ALL runs complete, finalize the results table in `notes.md`:

```markdown
## Formal Experiment Results

| Method    | Seed 42 | Seed 123 | Seed 456 | Mean   | Std   |
|-----------|---------|----------|----------|--------|-------|
| Baseline  | 0.847   | 0.851    | 0.843    | 0.847  | 0.004 |
| Proposed  | 0.862   | 0.858    | 0.865    | 0.862  | 0.004 |
| Ablation1 | 0.853   | 0.849    | 0.855    | 0.852  | 0.003 |
| Ablation2 | 0.856   | 0.854    | 0.859    | 0.856  | 0.003 |
```

### Generate Figures

Write a matplotlib script to produce publication-quality figures. Save to `figures/`:

```bash
cd code && python -c "
import matplotlib.pyplot as plt
import json

# Load results from experiments/ directory
# ... read each result.json ...

# Bar chart comparing methods
methods = ['Baseline', 'Proposed', 'Ablation1', 'Ablation2']
means = [0.847, 0.862, 0.852, 0.856]
stds = [0.004, 0.004, 0.003, 0.003]

fig, ax = plt.subplots(figsize=(8, 5))
ax.bar(methods, means, yerr=stds, capsize=5, color=['#4C72B0', '#DD8452', '#55A868', '#C44E52'])
ax.set_ylabel('Accuracy')
ax.set_title('Method Comparison')
plt.tight_layout()
plt.savefig('../figures/method_comparison.pdf', dpi=300)
plt.savefig('../figures/method_comparison.png', dpi=300)
print('Figures saved.')
"
```

Adapt the script to use actual data from `experiments/*/result.json`. Always save both PDF and PNG versions.

---

## Phase 5: Write Paper (~1 hr)

### Prepare

1. **Re-read notes.md FIRST.** Before writing anything, re-read the entire `notes.md` file, especially:
   - "Baseline Paper Experiment Blueprint" — what tables and figures the baseline paper has
   - "Experiment Checklist" — every experiment you ran
   - "Experiment Protocol (LOCKED)" — the exact settings
   - "Proposed Method" — what you changed and why

   Your paper's experiment section MUST mirror the baseline paper's structure. For every table/figure in the baseline paper's experiment section, you must have an analogous table/figure.

2. **Re-read all experiment results.** List every result file:
   ```bash
   find experiments/ -name "*.json" -o -name "*.log" | sort
   ```
   Read each one. Build a mental map of: which conditions, which datasets, which metrics, what numbers.

3. The template is already at `paper/main.tex` (copied during Setup).

4. Create the bibliography file:
   ```bash
   touch paper/references.bib
   ```
   Populate it with BibTeX entries for: the baseline paper, papers from the literature survey that you cite, and any method papers your approach builds on.

5. Copy figures into the paper directory:
   ```bash
   cp figures/*.pdf paper/
   ```

### Architecture Diagram (optional)

After writing the Method section, generate a main architecture figure:
- If the `scientific-schematics` skill is available: invoke it with a description based on your Method section to generate a publication-quality diagram. Save to `paper/figures/architecture.pdf`.
- If not available: write a TikZ diagram directly in LaTeX, or skip the figure.
- Reference it in the Method section with `\includegraphics`.

### Writing Order

Write sections in this specific order. This order is intentional — write what you know best first.

**1. Experiments Section (write first — you have all the data)**

- Create a main results table using booktabs style:
  ```latex
  \begin{table}[t]
  \centering
  \caption{Main results on [Dataset]. Mean $\pm$ std over [N] seeds.}
  \label{tab:main}
  \begin{tabular}{lcc}
  \toprule
  Method & Accuracy & F1 \\
  \midrule
  Baseline~\citep{baseline2024} & 0.847 $\pm$ 0.004 & 0.815 $\pm$ 0.005 \\
  Proposed (ours)                & \textbf{0.862 $\pm$ 0.004} & \textbf{0.831 $\pm$ 0.004} \\
  \bottomrule
  \end{tabular}
  \end{table}
  ```

- Add an ablation table with the same format.

- Reference figures: `\includegraphics[width=\linewidth]{method_comparison.pdf}`

- CRITICAL: Every number in a table MUST match the numbers in `experiments/*/result.json`. Cross-check each cell.

**2. Method Section (write second — you implemented it)**

- Describe the method clearly with mathematical notation where appropriate.
- Explain what changes from the baseline and why.
- Include an architecture figure if relevant.

**3. Introduction + Related Work (write third)**

- Introduction: motivate the problem, state the gap, summarize your contribution.
- Related Work: organize by themes (not chronologically). Cite papers from your literature survey.

**4. Abstract + Conclusion (write last)**

- Abstract: one paragraph summarizing problem, method, key result (with numbers).
- Conclusion: restate contribution, acknowledge limitations, suggest future work.

### Verify Citations

Before compiling, verify all citations:
```bash
python tools/research_tools.py verify-citations \
  --bib paper/references.bib \
  --output paper/citation_report.json
```
Read `paper/citation_report.json`. Fix any entries flagged as unverified — correct the BibTeX or remove the citation.

### Compile the Paper

```bash
cd paper && pdflatex main.tex && bibtex main && pdflatex main.tex && pdflatex main.tex
```

If pdflatex is not available (detected during Setup), skip compilation and inform the user:
"Paper source is complete at paper/main.tex. Install texlive to compile the PDF."

If compilation produces errors:
- Read the `.log` file to find the error.
- Fix the LaTeX source.
- Re-compile.
- Repeat until compilation succeeds with no errors (warnings are acceptable).

---

## Phase 6: Self-Review (~15 min)

Re-read the entire paper as if you are a critical peer reviewer. Go through this checklist item by item:

- [ ] **Every claim is backed by experiment data.** Search for any sentence that makes a claim (e.g., "our method improves...") and verify it points to a specific table or figure with matching numbers.

- [ ] **Table numbers exactly match `experiments/` JSON files.** Open each `experiments/*/result.json` and cross-reference every number in every table cell.

- [ ] **Baseline numbers are within 2% of the original paper.** Compare the baseline row in your tables with the numbers recorded in `notes.md` from the original paper.

- [ ] **All citations are verified.** Check that `paper/citation_report.json` shows all citations as verified.

- [ ] **Figures have proper captions and axis labels.** Every figure must have a descriptive caption. Every axis must be labeled with units.

- [ ] **Abstract accurately summarizes contributions.** The abstract should mention: the problem, the method name, the key improvement, and the main result number.

- [ ] **No placeholder text remaining.** Search for `[`, `TODO`, `FIXME`, `XXX`, `placeholder` in `paper/main.tex`. Remove or replace all of them.

- [ ] **References are complete.** Every `\citep` or `\cite` in the text has a corresponding entry in `references.bib`.

For each issue found:
1. Fix the issue in the source file.
2. Re-compile the PDF (if pdflatex is available).

After all issues are resolved, record the final status in `notes.md`:

```markdown
## Self-Review Complete

- All checklist items passed
- Final PDF: paper/main.pdf
- Total experiments run: [N]
- Key result: [method] achieves [metric]=[value] vs baseline [value] (+[improvement])
```

---

## Key Principles

Follow these principles throughout the entire research process. They are non-negotiable.

1. **Reproducibility first.** If the baseline cannot be reproduced within 2% of reported numbers, do not use it. Move on to the next candidate. A paper built on unreproducible baselines is worthless.

2. **Protocol is immutable.** Once the experiment protocol is locked in Phase 1 Step 4, NEVER change the dataset, metrics, seeds, learning rate, batch size, or any other setting. If results are bad, fix the code — not the protocol. The only exception: you may ADD new experiment conditions (extra ablations), but you may never modify existing ones.

3. **Evidence over claims.** Every sentence in the paper that makes a factual claim must be backed by a specific number from `experiments/`. No hand-waving. No "we observe improvements" without citing the exact improvement.

4. **notes.md is the source of truth.** Every decision — which baseline to use, why a candidate was rejected, what the reproduced numbers are, what the experiment protocol is — must be recorded in `notes.md`. If it is not in `notes.md`, it did not happen.

5. **Fail fast on bad baselines.** Do not spend more than 15 minutes debugging a baseline that will not reproduce. There are other papers with code. Move on. Time spent fighting a bad codebase is time not spent on actual research.

6. **CC decides everything.** Seeds, epochs, hyperparameters, method details — all of these are decided by reading the baseline paper and understanding the domain. Nothing is hardcoded in advance. CC reads the paper, understands the protocol, and follows it exactly.

---

## Tool Reference

All tools are invoked via `python tools/research_tools.py <command>`.

### search-papers

Search arXiv, Semantic Scholar, and OpenAlex for academic papers. Deduplicates results across sources.

```bash
python tools/research_tools.py search-papers \
  --query "your search query" \
  --max-results 20 \
  --year-min 2023 \
  --output papers/results.json
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--query`, `-q` | yes | — | Search query string |
| `--max-results`, `-n` | no | 20 | Max results per API source |
| `--year-min` | no | none | Exclude papers before this year |
| `--output`, `-o` | no | stdout | Output JSON file path |

Output JSON fields per paper: `title`, `authors`, `year`, `abstract`, `citation_count`, `arxiv_id`, `doi`, `url`, `source`.

### search-repos

Search GitHub for repositories matching a query. Sorted by stars descending.

```bash
python tools/research_tools.py search-repos \
  --query "paper title author name" \
  --max-results 10 \
  --output papers/repos.json
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--query`, `-q` | yes | — | Search query string |
| `--max-results`, `-n` | no | 10 | Max number of results |
| `--github-token` | no | none | GitHub token for higher rate limits |
| `--output`, `-o` | no | stdout | Output JSON file path |

Output JSON fields per repo: `owner`, `name`, `url`, `stars`, `pushed_at`, `description`, `language`, `size_kb`.

### run-experiment

Run a command in a working directory with GPU pinning. Records stdout, stderr, elapsed time, and return code.

```bash
python tools/research_tools.py run-experiment \
  --workdir code/ \
  --cmd "python train.py --seed 42" \
  --gpu 0 \
  --timeout 3600 \
  --output-dir experiments/run_name
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--workdir` | yes | — | Working directory for the command |
| `--cmd` | yes | — | Command to execute |
| `--gpu` | no | none | GPU IDs to set via CUDA_VISIBLE_DEVICES |
| `--timeout` | no | 3600 | Max seconds before killing the process |
| `--output-dir` | yes | — | Directory for result.json, stdout.log, stderr.log |

Output files: `result.json` (with `returncode`, `elapsed_sec`, `cmd`), `stdout.log`, `stderr.log`.

### verify-citations

Check each BibTeX entry against arXiv, Semantic Scholar, and CrossRef APIs. Reports verified and suspicious entries.

```bash
python tools/research_tools.py verify-citations \
  --bib paper/references.bib \
  --output paper/citation_report.json
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--bib` | yes | — | Path to BibTeX file |
| `--output`, `-o` | no | stdout | Output JSON report path |

Output JSON: list of entries with `key`, `title`, `status` (verified/suspicious/not_found), `matched_source`.
