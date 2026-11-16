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
    lines.append(f"- **Questions asked:** {s['questions_asked']}")
    top = ", ".join(f"“{f}” ×{n}" for f, n in list(s["fillers"].items())[:6]) or "none found"
    lines.append(f"- **Filler words:** {s['filler_total']} ({top})")
    return "\n".join(lines)


# ------------------------------------------------------------------ feature 4: teaching feedback (lecturer only)
# TODO(you + partner): the ready-made prompt (SRS FR-7.6, open issue OI-3). This is the heart of feature 4 —
# it decides what the lecturer actually learns about their teaching. The draft below works; make it yours:
#   - Which aspects matter most to a lecturer? (clarity, pace, examples, engagement, structure, language?)
#   - How short is "short"? The lecturer said long reports are not read.
#   - Tone: a colleague's honest notes, or a gentle coach?
#   - Should it quote exact moments ("at 00:23 you said…") so feedback is concrete?
TEACHING_FEEDBACK_PROMPT = """You are an experienced teaching coach. You receive the transcript of one university \
lecture and statistics measured from it. Write SHORT feedback for the lecturer (max 200 words, Markdown), \
in the language of the transcript:
1. **What worked** — 2 bullets.
2. **What to improve** — 3 bullets, each concrete and actionable (pace, clarity, examples, filler words, \
long monologues without a question to the class).
3. **One thing to try next lecture.**
Be specific and kind. Do not summarize the lecture content."""


def teaching_feedback(transcript: str, llm: LLMClient) -> dict:
    text, cues = parse_transcript(transcript)
    text, note = _clip(text)
    if not text.strip():
        raise ValueError("The transcript is empty")
    stats = speaking_stats(text, cues)
    stats_md = _stats_markdown(stats)
    if not isinstance(llm, OfflineClient):
        try:
            report = llm.complete(TEACHING_FEEDBACK_PROMPT, f"Measured statistics:\n{stats_md}\n\nTranscript:\n{text}")
            return {"engine": llm.name, "report": f"### Measured\n{stats_md}\n\n### Feedback\n{report}",
                    "stats": stats, "note": note}
        except Exception as e:  # no internet in class, bad key → still show the measured part
            note = (note + " " if note else "") + f"AI unavailable ({e.__class__.__name__}); measured statistics only."
    return {"engine": OfflineClient().name, "report": f"### Measured\n{stats_md}", "stats": stats, "note": note}


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
            return {"engine": llm.name, "report": summary, "note": note}
        except Exception as e:
            note = (note + " " if note else "") + f"AI unavailable ({e.__class__.__name__}); offline summary shown."
    report = "**Key sentences**\n" + "\n".join(f"- {b}" for b in extractive_summary(text))
    return {"engine": OfflineClient().name, "report": report, "note": note}


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
