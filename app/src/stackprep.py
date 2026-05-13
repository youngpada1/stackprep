"""
stackprep — Anthropic SDK app.

Usage:
    python src/stackprep.py

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

import httpx

MODEL = "anthropic/claude-sonnet-4.5"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ──────────────────────────────────────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    return """You are an expert technical interviewer and certification coach delivering
questions ONE AT A TIME in an interactive session.

## Session flow

Each turn you will either:
1. Receive "NEXT_QUESTION" — generate exactly ONE new question.
2. Receive the user's answer to the current question — score it immediately.

## Question format

Interview mode — open-ended:
Q. [Conceptual] <question text>

Certification mode — multiple choice:
Q. [Domain: <domain name>] <question text>
  a) …
  b) …
  c) …
  d) …
ANSWER: <correct letter(s)>

Always include the ANSWER line in certification mode.

## Scoring format

When scoring, always respond in this exact structure:

RESULT: ✅ Correct  OR  RESULT: ❌ Incorrect  OR  RESULT: ⚠️ Partial

EXPLANATION:
<clear explanation of why the answer is right or wrong>

CORRECT ANSWER: <the correct answer>

DOCS:
- <Title>: <url>

(Include 1-2 real, publicly accessible doc/resource URLs relevant to this topic.)

If correct or partial, still include the DOCS section with the best reference.

## Adaptive difficulty

Track what the user gets wrong and make subsequent questions harder on those topics.
Never repeat the same question in a session.

## Study Pack generation

When asked to generate a Study Pack, produce a JSON block (```json … ```) then markdown.
JSON schema per topic: {{"topic","official_docs":[{{"title","url"}}],"videos":[{{"title","url"}}],"exam_prep":[{{"title","url"}}],"summary"}}
Use only real, publicly accessible URLs.
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


def stream_response(api_key: str, messages: list[dict], system: str) -> str:
    """Stream the assistant reply to stdout, return the full text."""
    full_text = ""
    payload = {
        "model": MODEL,
        "max_tokens": 32000,
        "stream": True,
        "messages": [{"role": "system", "content": system}] + messages,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/flavsferr/stackprep",
        "X-Title": "stackprep",
    }
    with httpx.stream("POST", OPENROUTER_URL, json=payload, headers=headers, timeout=120) as r:
        if r.status_code >= 400:
            body = r.read()
            print(f"\nERROR {r.status_code}: {body.decode()}")
            r.raise_for_status()
        for line in r.iter_lines():
            if line.startswith("data: ") and line != "data: [DONE]":
                chunk = json.loads(line[6:])
                text = chunk["choices"][0]["delta"].get("content") or ""
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


def generate_study_pack(api_key: str,
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
    raw = stream_response(api_key, messages, system)

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

def generate_study_plan(api_key: str, messages: list[dict],
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
    stream_response(api_key, messages, system)


# ──────────────────────────────────────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────────────────────────────────────

CV_CACHE_PATH = Path(__file__).parent.parent / ".cv_cache.txt"
JD_CACHE_PATH = Path(__file__).parent.parent / ".jd_cache.txt"


def load_cached_cv() -> str | None:
    if CV_CACHE_PATH.exists():
        return CV_CACHE_PATH.read_text(encoding="utf-8").strip() or None
    return None


def save_cv_cache(cv: str) -> None:
    CV_CACHE_PATH.write_text(cv, encoding="utf-8")


def load_cached_jd() -> str | None:
    if JD_CACHE_PATH.exists():
        return JD_CACHE_PATH.read_text(encoding="utf-8").strip() or None
    return None


def save_jd_cache(jd: str) -> None:
    JD_CACHE_PATH.write_text(jd, encoding="utf-8")


def setup() -> tuple[str, str, str, int]:
    """Interactive setup. Returns (mode, cv, context, num_questions)."""
    banner("stackprep")

    print("\nWhat are you preparing for?")
    print("  1. Technical interview")
    print("  2. Certification exam")
    mode_choice = ask("Enter 1 or 2 [1]: ") or "1"
    mode = "certification" if mode_choice == "2" else "interview"

    num_q = choose_int(
        "How many questions per set? [5–30, default 10]: ",
        lo=5, hi=30, default=10,
    )

    cached_cv = load_cached_cv()
    if cached_cv:
        preview = cached_cv[:120].replace("\n", " ")
        print(f"\n📄 Last CV on file: {preview}…")
        reuse = ask("  Use this CV? [Y/n]: ").lower()
        if reuse in ("", "y"):
            cv = cached_cv
        else:
            cv = get_multiline_input("\n📄 Paste your CV / resume:")
            if not cv.strip():
                print("ERROR: CV is required.")
                sys.exit(1)
            save_cv_cache(cv.strip())
    else:
        cv = get_multiline_input("\n📄 Paste your CV / resume:")
        if not cv.strip():
            print("ERROR: CV is required.")
            sys.exit(1)
        save_cv_cache(cv.strip())

    cached_jd = load_cached_jd()
    label = "certification outline" if mode == "certification" else "job description"
    prompt = "\n📋 Paste the certification name + exam outline / domain list:" if mode == "certification" else "\n📋 Paste the job description:"

    if cached_jd:
        preview = cached_jd[:120].replace("\n", " ")
        print(f"\n📋 Last {label} on file: {preview}…")
        reuse = ask(f"  Use this {label}? [Y/n]: ").lower()
        if reuse in ("", "y"):
            context = cached_jd
        else:
            context = get_multiline_input(prompt)
            if not context.strip():
                print(f"ERROR: {label.capitalize()} is required.")
                sys.exit(1)
            save_jd_cache(context.strip())
    else:
        context = get_multiline_input(prompt)
        if not context.strip():
            print(f"ERROR: {label.capitalize()} is required.")
            sys.exit(1)
        save_jd_cache(context.strip())

    print("\n🛠  Extra stacks / topics to focus on (e.g. Terraform, AWS S3, dbt)?")
    print("  Press Enter to skip, or type comma-separated topics:")
    extra_raw = ask("  Topics: ").strip()
    extra_stacks = [t.strip() for t in extra_raw.split(",") if t.strip()] if extra_raw else []

    return mode, cv.strip(), context.strip(), num_q, extra_stacks


def build_initial_message(cv: str, context: str, mode: str, extra_stacks: list[str]) -> str:
    label = "Certification outline" if mode == "certification" else "Job description"
    extra = ""
    if extra_stacks:
        extra = f"\n\n--- Extra stacks / topics to include ---\n{', '.join(extra_stacks)}"
    return textwrap.dedent(f"""
        Analyse the CV and {label.lower()} below. Give a 3-line analysis
        (seniority level, key domains, top skill gaps), then wait — I will ask
        for questions one at a time by sending NEXT_QUESTION.

        --- CV ---
        {cv}

        --- {label} ---
        {context}{extra}

        Mode: {mode}
    """).strip()


# ──────────────────────────────────────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────────────────────────────────────

def run() -> None:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY is not set.")
        sys.exit(1)

    mode, cv, context, num_q, extra_stacks = setup()

    system = build_system_prompt()

    first_word = context.split()[0] if context else "session"
    session_label = f"{mode}_{first_word}"

    messages: list[dict] = []
    all_flagged: list[str] = []
    q_num = 0
    score = {"correct": 0, "total": 0}

    # ── Analyse CV + context ───────────────────────────────────────────────────
    messages.append({"role": "user", "content": build_initial_message(cv, context, mode, extra_stacks)})
    hr("Analysing your profile …")
    analysis = stream_response(api_key, messages, system)
    messages.append({"role": "assistant", "content": analysis})

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:
        hr("Options")
        print("  [A] Next question")
        print("  [S] Save Study Pack (flagged topics so far)")
        print("  [X] Exit and get Study Plan")
        choice = ask("\n  Your choice [A]: ").upper() or "A"

        if choice == "X":
            if all_flagged:
                generate_study_pack(api_key, all_flagged, session_label, system)
            generate_study_plan(api_key, messages, system)
            banner(f"Session complete — {score['correct']}/{score['total']} correct. Good luck!")
            break

        if choice == "S":
            generate_study_pack(api_key, all_flagged, session_label, system)
            all_flagged = []
            continue

        # ── Generate one question ──────────────────────────────────────────────
        q_num += 1
        messages.append({"role": "user", "content": "NEXT_QUESTION"})
        hr(f"Question {q_num}")
        question_text = stream_response(api_key, messages, system)
        messages.append({"role": "assistant", "content": question_text})

        # ── Collect answer ─────────────────────────────────────────────────────
        if mode == "certification":
            answer = ask("\n  Your answer (letter(s), e.g. b or a,c): ").strip().lower()
        else:
            print("\n  Your answer (type END on its own line when done):")
            lines: list[str] = []
            while True:
                try:
                    line = input("    ")
                except EOFError:
                    break
                if line.strip().upper() == "END":
                    break
                lines.append(line)
            answer = "\n".join(lines)

        if not answer:
            answer = "(skipped)"

        # ── Score ──────────────────────────────────────────────────────────────
        messages.append({"role": "user", "content": f"My answer: {answer}"})
        hr("Result")
        result_text = stream_response(api_key, messages, system)
        messages.append({"role": "assistant", "content": result_text})

        score["total"] += 1
        if "RESULT: ✅" in result_text:
            score["correct"] += 1
        elif "RESULT: ❌" in result_text:
            flag = ask("\n  Flag this topic for Study Later? [y/N]: ").lower()
            if flag == "y":
                all_flagged.append(f"Q{q_num}: {question_text[:200]}")
                print(f"  📌 Flagged. Total flagged: {len(all_flagged)}.")
                save_now = ask("  Save Study Pack now? [y/N]: ").lower()
                if save_now == "y":
                    generate_study_pack(api_key, all_flagged, session_label, system)
                    all_flagged = []

        print(f"\n  Score so far: {score['correct']}/{score['total']}")


if __name__ == "__main__":
    run()
