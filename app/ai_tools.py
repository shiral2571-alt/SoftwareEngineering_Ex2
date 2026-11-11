"""Features 4 and 5: lecture summary and homework review.

Both go through the `LLMClient` interface. With ANTHROPIC_API_KEY set, Claude is used; without it an
offline fallback answers (classic extractive summary / text statistics), so the live demo never fails.
"""
import difflib
import itertools
import os
import re
from abc import ABC, abstractmethod
from collections import Counter

CLAUDE_MODEL = "claude-opus-5-5"
MAX_INPUT_CHARS = 150_000  # protects the demo from a huge upload; reported to the user, never silent


class LLMClient(ABC):
    name = "LLM"

    @abstractmethod
    def complete(self, system: str, prompt: str) -> str: ...


class ClaudeClient(LLMClient):
    name = f"Claude ({CLAUDE_MODEL})"

    def __init__(self):
        import anthropic  # imported lazily: the app still runs if the package is missing
        self.client = anthropic.Anthropic()

    def complete(self, system: str, prompt: str) -> str:
        response = self.client.beta.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low"},          # short, routine task
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",                       # if a safety classifier declines, retry on another model
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("The model declined this request")
        return "".join(b.text for b in response.content if b.type == "text").strip()


class OfflineClient(LLMClient):
    """No network, no key. Used as a fallback; it cannot really 'understand' text."""
    name = "Offline fallback (no API key)"

    def complete(self, system: str, prompt: str) -> str:
        raise NotImplementedError("Offline client has no free-text generation")


def default_llm() -> LLMClient:
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return ClaudeClient()
        except Exception:
            pass
    return OfflineClient()


def _clip(text: str) -> tuple[str, str]:
    if len(text) <= MAX_INPUT_CHARS:
        return text, ""
    return text[:MAX_INPUT_CHARS], f"Note: input was {len(text):,} characters; only the first {MAX_INPUT_CHARS:,} were used."


# ---------------- Feature 4: lecture summary ----------------

STOPWORDS = set("""a an the and or but if of to in on at for with from by as is are was were be been being this that these
those it its we you they he she i our your their there here so not no do does did can will would should could have has had
about into than then also just more most very what which who whom how when where why all any each some such only own same
too s t don now um uh like okay ok yeah let going gonna""".split())


def split_transcript(text: str) -> str:
    """Strip WebVTT/SRT timing lines so plain sentences remain."""
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or line.isdigit() or "-->" in line:
            continue
        lines.append(re.sub(r"<[^>]+>", "", line))
    return " ".join(lines)


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


def summarize_lecture(transcript: str, llm: LLMClient) -> dict:
    text, note = _clip(split_transcript(transcript))
    if not text.strip():
        raise ValueError("The transcript is empty")
    if not isinstance(llm, OfflineClient):
        try:
            summary = llm.complete(
                "You summarize university lecture transcripts for students who missed the class. "
                "Write in the language of the transcript. Use short Markdown: a 2-sentence overview, "
                "then 'Key points' (bullets), then 'Terms to know' (bullets), then 'Open questions'.",
                f"Lecture transcript:\n\n{text}")
            return {"engine": llm.name, "summary": summary, "note": note}
        except Exception as e:  # network down in class → still show something
            note = (note + " " if note else "") + f"Claude unavailable ({e.__class__.__name__}); offline summary shown."
    bullets = extractive_summary(text)
    keywords = [w for w, _ in Counter(w for w in re.findall(r"[a-zA-Z֐-׿']+", text.lower())
                                      if w not in STOPWORDS and len(w) > 3).most_common(8)]
    summary = "**Key sentences**\n" + "\n".join(f"- {b}" for b in bullets) + \
              "\n\n**Keywords:** " + ", ".join(keywords)
    return {"engine": OfflineClient.name, "summary": summary, "note": note}


# ---------------- Feature 5: homework review ----------------

def _normalize(code: str) -> str:
    code = re.sub(r"#.*|//.*", "", code)          # drop comments
    return re.sub(r"\s+", " ", code).strip().lower()


def similarity_matrix(submissions: dict[str, str]) -> list[dict]:
    """Pairwise similarity (0–100%) after removing comments and whitespace. Deterministic, no LLM."""
    norm = {k: _normalize(v) for k, v in submissions.items()}
    pairs = []
    for a, b in itertools.combinations(sorted(norm), 2):
        ratio = difflib.SequenceMatcher(None, norm[a], norm[b], autojunk=False).ratio()
        pairs.append({"a": a, "b": b, "similarity": round(ratio * 100)})
    return sorted(pairs, key=lambda p: p["similarity"], reverse=True)


SUSPICIOUS_SIMILARITY = 85  # % — flagged for the lecturer to look at, never an automatic verdict


def review_homework(submissions: dict[str, str], assignment: str, llm: LLMClient) -> dict:
    if len(submissions) < 1:
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
                note += f"Claude unavailable ({e.__class__.__name__}); offline review shown. "
        lines = content.splitlines()
        comments = sum(1 for l in lines if l.strip().startswith(("#", "//")))
        funcs = len(re.findall(r"\bdef |\bfunction |\bclass ", content))
        reviews[name] = (f"- {len(lines)} lines, {len(content.split())} words\n"
                         f"- {funcs} functions/classes, {comments} comment lines\n"
                         f"- (Set ANTHROPIC_API_KEY for a written review.)")
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
    return {"engine": llm.name if use_llm else OfflineClient.name, "reviews": reviews, "pairs": pairs,
            "comparison": comparison, "flag_threshold": SUSPICIOUS_SIMILARITY, "note": note.strip()}
