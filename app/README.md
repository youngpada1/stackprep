# tech-prep

Adaptive technical interview & certification preparation powered by Claude Opus 4.7.

Paste your CV and a job description (or certification exam guide) once. The app analyses your level, generates a question set, scores your answers interactively, then automatically creates the next set — harder on your weak areas — until you exit.

## Quick start

```bash
# Install
pip install -e .

# Set your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run
tech-prep
# or: python src/tech_prep.py
```

## What it does

1. **Choose mode** — technical interview or certification exam
2. **Set question count** — 5–30 per set (default 10)
3. **Paste your CV** and a job description (interview) or certification outline (cert)
4. **Answer questions interactively**:
   - Certification: type letter(s) per question, e.g. `b` or `a,c`
   - Interview: type your answer, end with `END` on its own line
5. **Get scored** — each answer marked ✅ / ⚠️ / ❌ with explanations
6. **Flag questions** for "Study Later" by number (e.g. `3,7`)
7. **Next set auto-generates** — weighted toward your weak areas
8. Repeat until you choose `[X] Exit`
9. **Study Plan** — mastered vs. needs review vs. focus areas
10. **Study Pack** — official docs, YouTube videos, and exam prep links saved to `study_later/YYYY-MM-DD/`

## Interactive session flow

```
══════════════════════════════════════════════════════════════
  Technical Interview & Certification Prep
══════════════════════════════════════════════════════════════

What are you preparing for?
  1. Technical interview
  2. Certification exam
Enter 1 or 2 [1]: 2

How many questions per set? [5–30, default 10]: 5

📄 Paste your CV / resume:
  (Type END on its own line when done)
... paste your CV here ...
END

📋 Paste the certification name + exam outline / domain list:
  (Type END on its own line when done)
... paste exam outline here ...
END

──────────────────────────────────────────────────────────────
  Generating Set 1 …
──────────────────────────────────────────────────────────────
... questions stream here ...

──────────────────────────────────────────────────────────────
  Options
──────────────────────────────────────────────────────────────
  [A] Answer the questions
  [S] Save a Study Pack now (flagged topics so far)
  [X] Exit and get Study Plan

  Your choice [A]: A

──────────────────────────────────────────────────────────────
  Your answers
──────────────────────────────────────────────────────────────
  For each question enter the letter(s), e.g.  b   or   a,c
  Press Enter to skip a question.

  Q1: b
  Q2: a,c
  Q3: d
  ...

──────────────────────────────────────────────────────────────
  Scoring …
──────────────────────────────────────────────────────────────
... scoring and next set stream here ...

──────────────────────────────────────────────────────────────
  Study Later
──────────────────────────────────────────────────────────────
  Which questions do you want to study later?
  Enter question numbers separated by commas (1–5), or press Enter to skip.

  Flag: 2,4
  📌 Flagged 2 question(s) for later. Total flagged: 2.
  Save Study Pack now? [y/N]: y
  ✅ Study Pack saved → study_later/2026-05-04/certification_AWS_143022.md
```

## Modes

| Mode | Question style | Answer input | Use case |
|------|---------------|--------------|----------|
| Interview | Open-ended, scenario-based | Free text (type `END` to finish) | Technical job interviews |
| Certification | Multiple-choice, domain-mapped | Letter(s): `b` or `a,c` | AWS, GCP, Terraform, Snowflake, dbt, K8s, … |

## Study Pack output

Saved to `study_later/YYYY-MM-DD/<label>_<timestamp>.md` and `.json`.

Each topic entry contains:
- **official_docs** — product docs, RFCs, AWS/GCP/Azure docs
- **videos** — YouTube tutorials (freeCodeCamp, TechWorld with Nana, official channels)
- **exam_prep** — A Cloud Guru, Udemy, Whizlabs, official exam guides, free practice tests
- **summary** — why the topic matters and what to focus on

## Requirements

- Python 3.11+
- `anthropic >= 0.49.0`
- `ANTHROPIC_API_KEY` set in your environment
