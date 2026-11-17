"""AI features (SRS §4.7). All of them use the `LLMClient` chosen in Settings, and fall back to offline
methods when no key is configured or the provider fails, so the live demo never breaks (FR-7.4, NFR-8).

- Teaching feedback for the lecturer (feature 4, D-9)
- Lecture summary for students (Could, FR-7.10)
- Homework review + cross-student comparison (feature 5)
"""
import difflib
import itertools
import re
from collections import Counter

from .llm import LLMClient, OfflineClient

MAX_INPUT_CHARS = 150_000  # protects the demo from a huge upload; reported to the user, never silent


def _clip(text: str) -> tuple[str, str]:
    if len(text) <= MAX_INPUT_CHARS:
        return text, ""
    return text[:MAX_INPUT_CHARS], f"Input was {len(text):,} characters; only the first {MAX_INPUT_CHARS:,} were used."


# ------------------------------------------------------------------ transcripts
TIME_RE = re.compile(r"(\d+):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d+):(\d{2}):(\d{2})[.,](\d{3})")


def parse_transcript(text: str) -> tuple[str, list[tuple[float, float, str]]]:
    """Return (plain text, cues). Cues are (start_s, end_s, text) when the file has WebVTT/SRT timings."""
    cues, plain, current = [], [], None
    for line in text.splitlines():
        line = line.strip()
        m = TIME_RE.search(line)
        if m:
            g = [int(x) for x in m.groups()]
            current = [g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000, g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000, ""]
            cues.append(current)
            continue
        if not line or line == "WEBVTT" or line.isdigit():
            continue
        line = re.sub(r"<[^>]+>", "", line)
        plain.append(line)
        if current is not None:
            current[2] = (current[2] + " " + line).strip()
    return " ".join(plain), [tuple(c) for c in cues]


FILLERS_EN = ["um", "uh", "erm", "you know", "like", "basically", "actually", "kind of", "sort of", "okay so"]
FILLERS_HE = ["אממ", "אה", "כאילו", "בעצם", "יעני", "נגיד", "סתם"]


def speaking_stats(text: str, cues) -> dict:
    """Offline teaching statistics (FR-7.7): pace, filler words, questions, longest stretch without a pause."""
    words = re.findall(r"[\w']+", text.lower())
    lower = " " + " ".join(words) + " "
    fillers = {f: lower.count(f" {f} ") for f in FILLERS_EN + FILLERS_HE}
    fillers = {f: n for f, n in sorted(fillers.items(), key=lambda x: -x[1]) if n}
    stats = {"words": len(words), "questions_asked": text.count("?"), "fillers": fillers,
             "filler_total": sum(fillers.values())}
    if cues:
        duration = cues[-1][1] - cues[0][0]
        stats["minutes"] = round(duration / 60, 1)
        stats["words_per_minute"] = round(len(words) / (duration / 60)) if duration > 0 else None
        longest, run_start = 0.0, cues[0][0]
        for prev, cur in zip(cues, cues[1:]):
            if cur[0] - prev[1] > 3.0:  # a pause of 3+ seconds ends a stretch
                longest, run_start = max(longest, prev[1] - run_start), cur[0]
        stats["longest_stretch_min"] = round(max(longest, cues[-1][1] - run_start) / 60, 1)
    return stats


def _stats_markdown(s: dict) -> str:
    lines = [f"- **Words:** {s['words']:,}"]
    if s.get("minutes"):
        lines.append(f"- **Length:** {s['minutes']} min · **Pace:** {s.get('words_per_minute')} words/min "
                     "(≈120–160 is comfortable)")
        lines.append(f"- **Longest stretch without a pause:** {s['longest_stretch_min']} min")
    lines.append(f"- **Question marks in the transcript:** {s['questions_asked']} (lecturer and students together)")
    top = ", ".join(f"“{f}” ×{n}" for f, n in list(s["fillers"].items())[:6]) or "none found"
    lines.append(f"- **Filler words:** {s['filler_total']} ({top})")
    return "\n".join(lines)


# ------------------------------------------------------------------ feature 4: teaching feedback (lecturer only)
# The ready-made prompt (SRS FR-7.6, decisions D-17, D-18). Written by the team: it defines what the lecturer
# learns about their own teaching. The report is always in Hebrew (D-18): the instructions are in English, but
# the answer template below is in Hebrew, because small models tend to copy the headings' language.
TEACHING_FEEDBACK_PROMPT = """You receive the transcript of one university lecture that I (the lecturer) gave, \
plus a few statistics measured from it. Give me feedback on my teaching.

**Write the whole report in Hebrew.** Keep quotes from the transcript exactly as they are. \
Use short Markdown with exactly these sections and headings:

### 1. שאלות של סטודנטים
- כמה שאלות שאלו הסטודנטים, ועל כמה מהן עניתי בפועל.
- כמה פעמים דחיתי או קטעתי שאלה של סטודנט כדי להתקדם או בגלל קוצר זמן.

### 2. כללי
- **דוגמאות:** האם היו מספיק דוגמאות?
- **בהירות וסדר:** האם ההרצאה הועברה כראוי ובאופן ברור, בסדר לימודי הגיוני?
- **טעויות מקצועיות:** האם אמרתי משהו שגוי שעליי לתקן בפעם הבאה? צטט בקצרה.

### 3. לשימור (3 נקודות)
### 4. לשיפור (3 נקודות)

### 5. ההתחייבויות שלי — משימות להשלמה
List every promise I made to students during the lecture, for example a question I could not answer and said \
I would get back to them with an answer. Write each one as a task: "☐ …". Write "לא נמצאו" if there are none.

Rules:
- Be brief. No long explanations and no summary of the lecture content.
- Never guess or invent. If something cannot be determined from the transcript, say so. For example, if the \
transcript does not show who is speaking, say that student questions cannot be counted reliably, and do not \
present an estimate as a count.
- If the transcript seems broken, incomplete or too poor to answer these questions, say that clearly instead of \
giving feedback."""


def teaching_feedback(transcript: str, llm: LLMClient) -> dict:
    text, cues = parse_transcript(transcript)
    text, note = _clip(text)
    if not text.strip():
        raise ValueError("The transcript is empty")
    stats = speaking_stats(text, cues)
    stats_md = _stats_markdown(stats)
    if not cues:
        stats_md += "\n- *Pace and pauses need a .vtt/.srt file with timings — this transcript has none.*"
    if not isinstance(llm, OfflineClient):
        try:
            report = llm.complete(TEACHING_FEEDBACK_PROMPT, f"Measured statistics:\n{stats_md}\n\nTranscript:\n{text}")
            return {"engine": llm.name, "stats": stats, "note": note,
                    "report": f"{_model_line(llm.name)}\n\n### Measured\n{stats_md}\n\n### Feedback\n{report}"}
        except Exception as e:  # no internet in class, bad key → still show the measured part
            note = (note + " " if note else "") + f"AI unavailable ({e.__class__.__name__}); measured statistics only."
    engine = OfflineClient().name
    return {"engine": engine, "report": f"{_model_line(engine, note)}\n\n### Measured\n{stats_md}",
            "stats": stats, "note": note}


def _model_line(engine: str, note: str = "") -> str:
    """Every saved AI report says which model produced it (SRS FR-7.6a), so it can be judged later."""
    return f"**Model:** {engine}" + (f" — {note}" if note else "")


# ------------------------------------------------------------------ student summary (Could, FR-7.10)
STOPWORDS = set("""a an the and or but if of to in on at for with from by as is are was were be been being this that these
those it its we you they he she i our your their there here so not no do does did can will would should could have has had
about into than then also just more most very what which who whom how when where why all any each some such only own same
too s t don now um uh like okay ok yeah let going gonna""".split())


def extractive_summary(text: str, max_sentences: int = 5) -> list[str]:
    """Classic frequency-based extractive summary (Luhn-style): keep the sentences with the most important words."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 5]
    words = [w for w in re.findall(r"[a-zA-Z֐-׿']+", text.lower()) if w not in STOPWORDS and len(w) > 2]
    if not sentences or not words:
        return sentences[:max_sentences]
    freq = Counter(words)
    top = max(freq.values())

    def score(s: str) -> float:
        ws = [w for w in re.findall(r"[a-zA-Z֐-׿']+", s.lower()) if w in freq]
        return sum(freq[w] / top for w in ws) / (len(s.split()) ** 0.5)

    best = sorted(sorted(range(len(sentences)), key=lambda i: score(sentences[i]), reverse=True)[:max_sentences])
    return [sentences[i] for i in best]


def student_summary(transcript: str, llm: LLMClient) -> dict:
    text, _ = parse_transcript(transcript)
    text, note = _clip(text)
    if not text.strip():
        raise ValueError("The transcript is empty")
    if not isinstance(llm, OfflineClient):
        try:
            summary = llm.complete(
                "Summarize this university lecture transcript for students who missed the class, in the language "
                "of the transcript. Short Markdown: a 2-sentence overview, 'Key points' (bullets), 'Terms to know'.",
                text)
            return {"engine": llm.name, "report": f"{_model_line(llm.name)}\n\n{summary}", "note": note}
        except Exception as e:
            note = (note + " " if note else "") + f"AI unavailable ({e.__class__.__name__}); offline summary shown."
    engine = OfflineClient().name
    report = f"{_model_line(engine, note)}\n\n**Key sentences**\n" + "\n".join(f"- {b}" for b in extractive_summary(text))
    return {"engine": engine, "report": report, "note": note}


# ------------------------------------------------------------------ feature 5: homework review
def _normalize(code: str) -> str:
    code = re.sub(r"#.*|//.*", "", code)          # drop comments
    return re.sub(r"\s+", " ", code).strip().lower()


def similarity_matrix(submissions: dict[str, str]) -> list[dict]:
    """Pairwise similarity (0–100%) after removing comments and whitespace. Deterministic, no LLM (FR-7.14)."""
    norm = {k: _normalize(v) for k, v in submissions.items()}
    pairs = []
    for a, b in itertools.combinations(sorted(norm), 2):
        ratio = difflib.SequenceMatcher(None, norm[a], norm[b], autojunk=False).ratio()
        pairs.append({"a": a, "b": b, "similarity": round(ratio * 100)})
    return sorted(pairs, key=lambda p: p["similarity"], reverse=True)


SUSPICIOUS_SIMILARITY = 85  # % — flagged for the lecturer to look at, never an automatic verdict


def review_homework(submissions: dict[str, str], assignment: str, llm: LLMClient) -> dict:
    if not submissions:
        raise ValueError("Upload at least one submission")
    pairs = similarity_matrix(submissions)
    reviews, note = {}, ""
    use_llm = not isinstance(llm, OfflineClient)
    for name, content in sorted(submissions.items()):
        content, clip_note = _clip(content)
        if clip_note:
            note += f"{name}: {clip_note} "
        if use_llm:
            try:
                reviews[name] = llm.complete(
                    "You are a teaching assistant reviewing one student's homework. Be specific and kind. "
                    "Markdown, max 120 words: 'Strengths', 'To improve', and a suggested grade out of 100 "
                    "with one line of justification. The lecturer makes the final decision.",
                    f"Assignment:\n{assignment or '(not given)'}\n\nSubmission ({name}):\n{content}")
                continue
            except Exception as e:
                use_llm = False
                note += f"AI unavailable ({e.__class__.__name__}); offline review shown. "
        lines = content.splitlines()
        comments = sum(1 for l in lines if l.strip().startswith(("#", "//")))
        funcs = len(re.findall(r"\bdef |\bfunction |\bclass ", content))
        reviews[name] = (f"- {len(lines)} lines, {len(content.split())} words\n"
                         f"- {funcs} functions/classes, {comments} comment lines\n"
                         f"- (Add an API key in Settings for a written review.)")
    comparison = ""
    if use_llm and len(submissions) > 1:
        try:
            overview = "\n\n".join(f"### {n}\n{_clip(c)[0][:4000]}" for n, c in sorted(submissions.items()))
            comparison = llm.complete(
                "Compare several students' solutions to the same assignment for the lecturer. Markdown, max 150 words: "
                "common mistakes, the strongest approach, and who may need help. Do not accuse anyone of copying.",
                f"Assignment:\n{assignment or '(not given)'}\n\n{overview}")
        except Exception:
            comparison = ""
    return {"engine": llm.name if use_llm else OfflineClient().name, "reviews": reviews, "pairs": pairs,
            "comparison": comparison, "flag_threshold": SUSPICIOUS_SIMILARITY, "note": note.strip()}
