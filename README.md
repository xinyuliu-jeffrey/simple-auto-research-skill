# simple-auto-research

[![Claude Code](https://img.shields.io/badge/Claude_Code-Skill-blueviolet?logo=anthropic)](https://claude.ai/code)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero-green)](.)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Claude Code skill that autonomously conducts ML research — from a research topic to a complete LaTeX paper backed by real experiments.

**Give it a topic → it finds the best baseline repo → clones it → reproduces results → modifies the code → runs experiments → writes the paper.**

## Install

**Via [skills.sh](https://skills.sh):**
```bash
npx skills add xinyuliu-jeffrey/simple-auto-research-skill
```

**Manual — Global** (available in all projects):
```bash
git clone https://github.com/xinyuliu-jeffrey/simple-auto-research-skill.git
cp -R simple-auto-research-skill/simple-auto-research "$HOME/.claude/skills/simple-auto-research"
```

**Manual — Project-level** (available in current project only):
```bash
git clone https://github.com/xinyuliu-jeffrey/simple-auto-research-skill.git
cp -R simple-auto-research-skill/simple-auto-research .claude/skills/simple-auto-research
```

In Claude Code, explicitly request this skill:
```
Please use the simple-auto-research skill to research "your topic here"
```

## What It Does

Give Claude Code a research topic. It will:

1. **Survey literature** — search arXiv, Semantic Scholar, OpenAlex for related papers
2. **Find the best baseline** — evaluate candidate repos, clone the best one, reproduce results
3. **Read the baseline paper** — extract the full experiment blueprint (datasets, metrics, ablations)
4. **Propose a method** — identify a gap and design an improvement
5. **Implement** — modify the baseline code directly (read/edit/run, like a human researcher)
6. **Run experiments** — follow the baseline paper's protocol exactly, with GPU pinning and result logging
7. **Write the paper** — LaTeX, tables, figures, citations, compiled PDF
8. **Self-review** — check every claim against experiment data

## Usage

```bash
# Go to any empty directory
mkdir ~/my-research && cd ~/my-research

# Start Claude Code
claude

# Give it a topic
> research "applying KAN to time series forecasting"
```

Claude will create a workspace, run for a few hours, and deliver:
```
research-kan-time-series-forecasting/
├── code/           # Modified baseline code
├── experiments/    # All results (JSON + logs)
├── figures/        # Generated plots
├── paper/
│   ├── main.tex    # Complete paper
│   ├── main.pdf    # Compiled PDF
│   └── references.bib
└── notes.md        # Research decisions log
```

## Example Output

We ran `research "applying TTT (Test-Time Training) to time series forecasting"` and got a complete paper in ~4 hours:

**[TTT-TSF: Test-Time Training for Time Series Forecasting](examples/ttt-time-series-forecasting.pdf)** — Applies TTT layers (learned self-supervised updates at test time) to replace standard linear layers in iTransformer. Evaluated on 7 datasets (ETTh1, ETTh2, ETTm1, ETTm2, Weather, Electricity, Traffic), following the iTransformer paper's exact experimental protocol.

The skill autonomously:
- Surveyed 60+ papers, selected iTransformer as baseline
- Cloned the [Time-Series-Library](https://github.com/thuml/Time-Series-Library) repo
- Reproduced iTransformer baseline numbers
- Implemented TTT-TSF by modifying the codebase
- Ran all 56 experiments (7 datasets x 4 prediction lengths x 2 models) on 2 GPUs in parallel
- Wrote the LaTeX paper with tables, analysis, and compiled PDF

## Requirements

- **Claude Code**
- **Python 3.11+**
- **GPU** (optional but recommended for ML experiments)
- **pdflatex** (optional, for PDF compilation)
- **GITHUB_TOKEN** (optional, for higher GitHub API rate limits)

No pip dependencies — `research_tools.py` uses only Python stdlib.

## Tools Included

`research_tools.py` is a standalone CLI that Claude calls via Bash:

```bash
# Search papers across arXiv, Semantic Scholar, OpenAlex
python tools/research_tools.py search-papers --query "KAN time series" --max-results 20

# Search GitHub for baseline repos
python tools/research_tools.py search-repos --query "time series forecasting" --max-results 10

# Run experiment with GPU pinning and metrics capture
python tools/research_tools.py run-experiment --workdir code/ --cmd "python main.py" --gpu 0,1 --timeout 3600

# Verify BibTeX citations against real APIs
python tools/research_tools.py verify-citations --bib paper/references.bib
```

## How It Works

The key insight: instead of using an LLM pipeline to generate code in a single shot, this skill lets Claude Code **be the researcher** — reading files, making targeted edits, running experiments, seeing errors, and fixing them iteratively. Just like a human would.

### Phase 1: Find the Best Baseline (~1 hr)
- Search literature, evaluate 3-5 candidates
- Clone the best repo, **reproduce its results**
- If reproduction fails, move to the next candidate
- Lock the experiment protocol (datasets, metrics, seeds) from the baseline paper

### Phase 2-3: Propose & Implement (~1-2 hr)
- Identify research gap, propose improvement
- Modify baseline code directly (CC reads/edits files)
- Iterative development: edit → run → see error → fix

### Phase 4: Formal Experiments (~1-2 hr)
- Follow the baseline paper's exact protocol
- Run all datasets, all conditions, all ablations
- Every experiment tracked in `experiments/` as JSON

### Phase 5-6: Write Paper & Self-Review (~1 hr)
- LaTeX paper mirroring baseline paper's experiment structure
- Every claim backed by data from `experiments/`
- Architecture diagram auto-generated (via [`scientific-schematics`](https://github.com/K-Dense-AI/claude-scientific-skills) skill if installed, otherwise TikZ)
- Citation verification against real APIs

## How It Differs from AI Scientist / Other Pipelines

| | simple-auto-research | AI Scientist / Pipelines |
|---|---|---|
| Code modification | CC reads/edits files directly | Single LLM call outputs entire files |
| Baseline selection | Reads paper, reproduces results | Keyword search + heuristic scoring |
| Experiment design | Follows baseline paper's exact protocol | LLM generates protocol (often placeholder) |
| Paper quality | Mirrors baseline paper's structure | Generic template |
| Dependencies | Zero (stdlib only) | Full framework install |

## Tips

- **Be specific**: `"applying KAN to time series forecasting"` > `"improve forecasting"`
- **Name the baseline** if you have one: `"replacing MLP with KAN in PatchTST for time series forecasting"`
- **Set GITHUB_TOKEN** for reliable GitHub search: `export GITHUB_TOKEN=ghp_...`
- **Check progress**: look at `notes.md` and the task list during execution
- **GPU**: CC auto-detects free GPUs via `nvidia-smi`

---

If you find this useful, please give it a star! It helps others discover this skill.

## License

MIT
