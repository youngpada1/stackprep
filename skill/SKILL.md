# Technical Interview & Certification Prep

This skill generates adaptive technical test sets for interview and certification preparation.

It reads the user's CV and a job description (or certification outline), infers the required technical depth and domain, generates a configurable set of questions, scores answers interactively, and automatically creates the next set when the user finishes the current one.

## Activation

Activate this skill when the user:
- Pastes a job description or certification exam outline
- Asks to prepare for a technical interview
- Asks to prepare for a certification (AWS, GCP, Terraform, dbt, Snowflake, Kubernetes, etc.)
- Says "start a new test", "next set", or "continue prep"

## How to run a session

### 1. Gather context (first turn only)

Ask the user to provide **all three**:
1. Their CV / resume (paste or describe key experience)
2. Either:
   - A job description (for interview prep)
   - A certification name + exam guide / outline (for cert prep)
3. How many questions per set (default 10, range 5–30)

If any item is missing, ask for it before generating questions.

### 2. Analyse context

Extract:
- **Technical domains** (e.g. data engineering, cloud infra, ML ops, backend)
- **Seniority level** from CV experience (junior / mid / senior / staff)
- **Skill gaps** — things the JD/cert requires that the CV doesn't strongly show
- **Mode**: `interview` or `certification`

### 3. Generate a test set

Produce **N questions** per set (N = user's chosen count, default 10). Mix:

| Type | Interview % | Cert % |
|---|---|---|
| Conceptual / theory | 30 % | 40 % |
| Scenario / system design | 30 % | 20 % |
| Code / SQL / config snippet | 30 % | 30 % |
| Gotcha / edge case | 10 % | 10 % |

Calibrate difficulty to the seniority level:
- **Junior**: fundamentals, syntax, basic design patterns
- **Mid**: trade-offs, debugging, moderate system design
- **Senior**: architecture decisions, performance, team/org considerations
- **Staff**: org-wide impact, technical strategy, ambiguous problem solving

For **certification** mode, map questions directly to exam domains from the outline (weight by domain percentage if available).

**Interview mode** — open-ended, no options:
```
Q1. [Conceptual] <question text>
```

**Certification mode** — multiple-choice (single or multi-select):
```
Q1. [Domain: <domain name>] <question text>
  a) …
  b) …
  c) …
  d) …
ANSWER: <correct letter(s), e.g. "b" or "a,c">
```

Always include the `ANSWER:` line in certification mode.

### 4. Wait for answers

After presenting the questions, wait. The user will answer interactively:
- **Certification**: the user types one or more letter(s), e.g. `b` or `a,c`
- **Interview**: the user types a free-text answer

### 5. Score and explain

When the user submits answers:
- Mark each correct ✅ / partial ⚠️ / incorrect ❌
- Show the **model answer** with a clear explanation (why it's right, why wrong answers are wrong)
- Highlight **skill gaps** revealed by incorrect answers
- Give an overall score (e.g. 7/10)

### 6. Study Later flag

After scoring, ask the user if they want to flag any questions for "Study Later":
- User enters question numbers separated by commas (e.g. `3,7`) or presses Enter to skip
- Accumulate flagged questions across sets

When generating a Study Pack for flagged items, produce:
1. A `json` code block with this exact schema:
```json
[
  {
    "topic": "<concise topic name>",
    "official_docs": [{"title": "…", "url": "…"}],
    "videos": [{"title": "…", "url": "…"}],
    "exam_prep": [{"title": "…", "url": "…"}],
    "summary": "<2-3 sentence explanation of why this topic matters and what to focus on>"
  }
]
```
2. A human-readable markdown summary of the same resources

Resource preferences:
- `official_docs`: official product docs, RFC, AWS/GCP/Azure docs, language docs
- `videos`: YouTube (freeCodeCamp, TechWorld with Nana, official vendor channels)
- `exam_prep`: A Cloud Guru, Udemy, Whizlabs, official exam guides, free practice tests

Use only real, publicly accessible URLs.

### 7. Auto-generate next set

Immediately after scoring, generate **Set N+1** with:
- Higher weight on topics where the user scored < 60 %
- Slightly harder variants of questions they got right
- At least 2 new topic areas not covered in Set N

Announce: "── Set N complete (score X/{N}). Generating Set N+1 ──"

Repeat indefinitely until the user says "stop", "exit", or "I'm done".

### 8. Session summary (on exit)

When the user exits, produce a **Study Plan**:
- Topics mastered (≥ 80 % correct across sets)
- Topics to review (50–79 %)
- Topics to focus on (< 50 %)
- 3–5 concrete study resources or actions per weak area

## Quality rules

- Questions must be accurate and match the latest stable documentation for the relevant technology (e.g. current AWS service features, current dbt syntax, current Kubernetes API).
- Avoid outdated APIs, deprecated flags, or obsolete patterns.
- Do not repeat identical questions across sets in the same session.
- For SQL/code snippets, always specify the dialect or runtime (e.g. PostgreSQL 16, Python 3.12, dbt Core 1.8).
- For certification prep, always cite the exam domain the question maps to.
