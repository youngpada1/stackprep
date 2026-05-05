"""
Technical Interview & Certification Prep — Anthropic SDK app.

Usage:
    python src/tech_prep.py

Flow:
  1. Choose mode (interview / certification) and number of questions per set.
  2. Paste your CV and job description (or cert outline).
  3. Answer each question:
       - Certification: type the letter(s), e.g. "b" or "a,c"
       - Interview:     type your answer freely
  4. After scoring, flag questions for "Study Later" by number.
  5. At exit (or on demand) a Study Pack is generated with official docs,
     videos and exam-prep resources and saved to study_later/.
"""

from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import anthropic

MODEL = "claude-opus-4-7"

# ──────────────────────────────────────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────────────────────────────────────

def build_system_prompt(set_size: int) -> str:
    return f"""You are an expert technical interviewer and certification coach.

You generate rigorous, adaptive question sets to prepare candidates for technical
interviews and certification exams.

## Modes
- **interview**: open-ended questions calibrated to the seniority level shown in the CV
  and the requirements of the job description.
- **certification**: multiple-choice (single or multi-select) questions mapped to the
  exam domains in the certification outline, weighted by domain percentage.

## Question format

Always number questions Q1, Q2, … Q{set_size} where {set_size} is the requested set size.

Interview mode — open-ended:
Q1. [Conceptual] <question text>

Certification mode — multiple choice:
Q1. [Domain: <domain name>] <question text>
  a) …
  b) …
  c) …
  d) …
ANSWER: <correct letter(s), e.g. "b" or "a,c">

Always include the ANSWER line in certification mode so answers can be scored automatically.

## Scoring (called with tagged answers from the user)

The user will send answers tagged as:
  Q1: <answer>
  Q2: <answer>
  …

Score each answer:
- Correct ✅ / Partial ⚠️ / Incorrect ❌
- Show the model answer with a clear explanation.
- List skill gaps revealed by incorrect answers.
- Give total score N/{set_size}.

## Next set

After scoring, immediately generate the next set of {set_size} questions:
- Higher weight on topics where the user scored < 60 %.
- Slightly harder variants of correctly-answered topics.
- At least 2 new topic areas not covered in the previous set.

Announce: "── Set N complete (score X/{set_size}). Generating Set N+1 ──"

## Study Pack generation

When asked to generate a Study Pack for a list of topics, produce a JSON block
(fenced as ```json … ```) followed by a human-readable markdown section.

The JSON must be an array of objects:
[
  {
    "topic": "<concise topic name>",
    "official_docs": [{"title": "…", "url": "…"}, …],
    "videos": [{"title": "…", "url": "…"}, …],
    "exam_prep": [{"title": "…", "url": "…"}, …],
    "summary": "<2-3 sentence explanation of why this topic matters and what to focus on>"
  },
  …
]

Use only real, publicly accessible URLs. Prefer:
- official_docs: official product docs, RFC, AWS/GCP/Azure docs, language docs
- videos: YouTube (freeCodeCamp, TechWorld with Nana, official vendor channels)
- exam_prep: A Cloud Guru, Udemy, Whizlabs, official exam guides, free practice tests

## Quality rules
- Questions must reflect the LATEST stable docs for every technology.
- No repeated questions within a session.
- Specify dialect/runtime for code/SQL (e.g. PostgreSQL 16, Python 3.12, dbt 1.8).
- For cert prep, cite the exam domain for every question.
"""


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

DIVIDER = "─" * 62
HEAVY   = "═" * 62


def hr(label: str = "") -> None:
    if label:
        print(f"\n{DIVIDER}\n  {label}\n{DIVIDER}")
    else:
        print(f"\n{DIVIDER}")


def banner(text: str) -> None:
    print(f"\n{HEAVY}\n  {text}\n{HEAVY}")


def stream_response(client: anthropic.Anthropic, messages: list[dict],
                    system: str) -> str:
    """Stream the assistant reply to stdout, return the full text."""
    full_text = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=8192,
        system=system,
        thinking={"type": "adaptive"},
        messages=messages,
        cache_control={"type": "ephemeral"},
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            full_text += text
    print()
    return full_text


def get_multiline_input(prompt: str, end_token: str = "END") -> str:
    """Collect multiline input until the user types end_token alone on a line."""
    print(prompt)
    print(f"  (Type END on its own line when done)\n")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().upper() == end_token:
            break
        lines.append(line)
    return "\n".join(lines)


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def choose_int(prompt: str, lo: int, hi: int, default: int) -> int:
    while True:
        raw = ask(prompt)
        if not raw:
            return default
        if raw.isdigit() and lo <= int(raw) <= hi:
            return int(raw)
        print(f"  Please enter a number between {lo} and {hi}.")


# ──────────────────────────────────────────────────────────────────────────────
# Answer collection
# ──────────────────────────────────────────────────────────────────────────────

def collect_cert_answers(n: int) -> dict[int, str]:
    """Multi-select answer collection for certification mode."""
    hr("Your answers")
    print("  For each question enter the letter(s), e.g.  b   or   a,c")
    print("  Press Enter to skip a question.\n")
    answers: dict[int, str] = {}
    for i in range(1, n + 1):
        raw = ask(f"  Q{i}: ").strip().lower().replace(" ", "")
        answers[i] = raw if raw else "(skipped)"
    return answers


def collect_interview_answers(n: int) -> dict[int, str]:
    """Free-text answer collection for interview mode."""
    hr("Your answers")
    print("  Answer each question. Type END after each answer.\n")
    answers: dict[int, str] = {}
    for i in range(1, n + 1):
        print(f"  Q{i}:")
        lines: list[str] = []
        while True:
            try:
                line = input("    ")
            except EOFError:
                break
            if line.strip().upper() == "END":
                break
            lines.append(line)
        answers[i] = "\n".join(lines) if lines else "(skipped)"
    return answers


def format_answers_for_claude(answers: dict[int, str]) -> str:
    lines = [f"Q{i}: {ans}" for i, ans in sorted(answers.items())]
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Study Later
# ──────────────────────────────────────────────────────────────────────────────

def pick_study_questions(n: int) -> list[int]:
    """Ask which question numbers to flag for study later."""
    hr("Study Later")
    print("  Which questions do you want to study later?")
    print(f"  Enter question numbers separated by commas (1–{n}), or press Enter to skip.\n")
    raw = ask("  Flag: ")
    if not raw:
        return []
    nums: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= n:
            nums.append(int(part))
    return sorted(set(nums))


def extract_questions_from_text(text: str, indices: list[int]) -> list[str]:
    """Pull question text for the selected indices from the assistant's output."""
    # Match lines like "Q3." or "Q3:"
    pattern = re.compile(r"^Q(\d+)[\.:](.+)$", re.MULTILINE)
    found: dict[int, str] = {}
    for m in pattern.finditer(text):
        num = int(m.group(1))
        found[num] = m.group(2).strip()
    return [f"Q{i}: {found[i]}" for i in indices if i in found]


def save_study_pack(topics_json: list[dict], raw_md: str, session_label: str) -> Path:
    """Save the study pack JSON + markdown to study_later/<date>/."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_dir = Path("study_later") / date_str
    out_dir.mkdir(parents=True, exist_ok=True)

    # Sanitise session label for filenames
    safe = re.sub(r"[^a-z0-9_-]", "_", session_label.lower())[:40]
    ts = datetime.now().strftime("%H%M%S")

    md_path = out_dir / f"{safe}_{ts}.md"
    json_path = out_dir / f"{safe}_{ts}.json"

    md_path.write_text(raw_md, encoding="utf-8")
    json_path.write_text(json.dumps(topics_json, indent=2, ensure_ascii=False),
                         encoding="utf-8")

    return md_path


def generate_study_pack(client: anthropic.Anthropic,
                        flagged_items: list[str],
                        session_label: str,
                        system: str) -> None:
    """Ask Claude to find resources for each flagged topic, save to disk."""
    if not flagged_items:
        print("  No questions flagged — nothing to save.")
        return

    hr("Generating Study Pack")
    print("  Searching for official docs, videos, and exam prep resources …\n")

    topic_list = "\n".join(f"- {item}" for item in flagged_items)
    prompt = (
        "Generate a Study Pack for the following topics/questions that the user "
        "flagged for later review. Search for the best resources available in 2026.\n\n"
        f"{topic_list}\n\n"
        "Return the JSON block first (```json … ```) then the human-readable "
        "markdown summary."
    )

    messages = [{"role": "user", "content": prompt}]
    raw = stream_response(client, messages, system)

    # Extract JSON
    json_match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    topics_json: list[dict] = []
    if json_match:
        try:
            topics_json = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    saved_path = save_study_pack(topics_json, raw, session_label)
    print(f"\n  ✅ Study Pack saved → {saved_path}")


# ──────────────────────────────────────────────────────────────────────────────
# Session summary / study plan
# ──────────────────────────────────────────────────────────────────────────────

def generate_study_plan(client: anthropic.Anthropic, messages: list[dict],
                        system: str) -> None:
    hr("Final Study Plan")
    messages.append({
        "role": "user",
        "content": (
            "I'm done for today. Please give me a final Study Plan:\n"
            "- Topics mastered (≥ 80 % correct across all sets)\n"
            "- Topics to review (50–79 %)\n"
            "- Topics to focus on (< 50 %)\n"
            "- 3–5 concrete study actions per weak area."
        ),
    })
    stream_response(client, messages, system)


# ──────────────────────────────────────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────────────────────────────────────

def setup() -> tuple[str, str, str, int]:
    """Interactive setup. Returns (mode, cv, context, num_questions)."""
    banner("Technical Interview & Certification Prep")

    print("\nWhat are you preparing for?")
    print("  1. Technical interview")
    print("  2. Certification exam")
    mode_choice = ask("Enter 1 or 2 [1]: ") or "1"
    mode = "certification" if mode_choice == "2" else "interview"

    num_q = choose_int(
        "How many questions per set? [5–30, default 10]: ",
        lo=5, hi=30, default=10,
    )

    cv = get_multiline_input("\n📄 Paste your CV / resume:")
    if not cv.strip():
        print("ERROR: CV is required.")
        sys.exit(1)

    if mode == "certification":
        context = get_multiline_input(
            "\n📋 Paste the certification name + exam outline / domain list:"
        )
    else:
        context = get_multiline_input("\n📋 Paste the job description:")

    if not context.strip():
        print("ERROR: Job description / certification outline is required.")
        sys.exit(1)

    return mode, cv.strip(), context.strip(), num_q


def build_initial_message(cv: str, context: str, mode: str, num_q: int) -> str:
    label = "Certification outline" if mode == "certification" else "Job description"
    return textwrap.dedent(f"""
        Analyse the CV and {label.lower()} below.
        Generate **Set 1** of exactly {num_q} questions calibrated to the candidate's level.

        --- CV ---
        {cv}

        --- {label} ---
        {context}

        Mode: {mode}
        Questions per set: {num_q}

        Begin with a 3-line analysis (seniority level, key domains, top skill gaps),
        then present the {num_q} questions.
    """).strip()


# ──────────────────────────────────────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────────────────────────────────────

def run() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY is not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    mode, cv, context, num_q = setup()

    system = build_system_prompt(num_q)

    # Derive a short session label for filenames
    first_word = context.split()[0] if context else "session"
    session_label = f"{mode}_{first_word}"

    messages: list[dict] = []
    all_flagged: list[str] = []   # accumulated "study later" items across sets
    set_num = 1

    # ── First set ──────────────────────────────────────────────────────────────
    messages.append({"role": "user", "content": build_initial_message(cv, context, mode, num_q)})
    hr(f"Generating Set {set_num} …")
    last_assistant_text = stream_response(client, messages, system)
    messages.append({"role": "assistant", "content": last_assistant_text})

    # ── Loop ──────────────────────────────────────────────────────────────────
    while True:
        hr("Options")
        print("  [A] Answer the questions")
        print("  [S] Save a Study Pack now (flagged topics so far)")
        print("  [X] Exit and get Study Plan")
        choice = ask("\n  Your choice [A]: ").upper() or "A"

        if choice == "X":
            # Save any outstanding flagged topics before exiting
            if all_flagged:
                generate_study_pack(client, all_flagged, session_label, system)
            generate_study_plan(client, messages, system)
            banner("Session complete — good luck! 🚀")
            break

        if choice == "S":
            generate_study_pack(client, all_flagged, session_label, system)
            all_flagged = []   # reset after saving
            continue

        # ── Collect answers ────────────────────────────────────────────────────
        if mode == "certification":
            answers = collect_cert_answers(num_q)
        else:
            answers = collect_interview_answers(num_q)

        answer_text = format_answers_for_claude(answers)
        messages.append({"role": "user", "content": answer_text})

        # ── Score + next set ───────────────────────────────────────────────────
        hr("Scoring …")
        last_assistant_text = stream_response(client, messages, system)
        messages.append({"role": "assistant", "content": last_assistant_text})
        set_num += 1

        # ── Study Later ────────────────────────────────────────────────────────
        flagged_indices = pick_study_questions(num_q)
        if flagged_indices:
            # Pull question text from the previous set (two messages back)
            prev_set_text = messages[-4]["content"] if len(messages) >= 4 else ""
            items = extract_questions_from_text(prev_set_text, flagged_indices)
            if not items:
                # Fallback: just note the numbers
                items = [f"Question {i} from Set {set_num - 1}" for i in flagged_indices]
            all_flagged.extend(items)
            print(f"\n  📌 Flagged {len(items)} question(s) for later. "
                  f"Total flagged: {len(all_flagged)}.")

            save_now = ask("  Save Study Pack now? [y/N]: ").lower()
            if save_now == "y":
                generate_study_pack(client, all_flagged, session_label, system)
                all_flagged = []


if __name__ == "__main__":
    run()
