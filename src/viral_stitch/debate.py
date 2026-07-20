from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_GROQ_MODEL = "whisper-large-v3-turbo"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
HOOK_TERMS = {
    "admit", "admitted", "wrong", "proof", "prove", "lie", "lying", "destroyed",
    "caught", "exposed", "contradiction", "hypocrite", "fact", "evidence", "answer",
    "question", "listen", "wait", "hold on", "you said", "that's not", "no way",
    "exactly", "actually", "never", "always", "everyone", "nobody", "why",
}
CONFLICT_TERMS = {
    "wrong", "false", "lie", "lying", "contradiction", "hypocrite", "ridiculous",
    "nonsense", "debunk", "expose", "admit", "answer the question", "moving the goalpost",
}
RESOLUTION_TERMS = {
    "therefore", "so the point", "that's why", "which means", "the answer is",
    "bottom line", "in conclusion", "you just admitted", "we agree", "exactly",
}


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str
    confidence: float | None = None
    speaker: str | None = None


@dataclass(frozen=True)
class ClipCandidate:
    start: float
    end: float
    title: str
    hook: str
    transcript: str
    score: float
    reasons: tuple[str, ...]
    speakers: tuple[str, ...]


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )


def _tool(name: str, explicit: str | None = None) -> str:
    candidate = explicit or shutil.which(name)
    if not candidate:
        raise FileNotFoundError(f"{name} was not found. Install FFmpeg and ensure {name} is on PATH.")
    return candidate


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _multipart(fields: dict[str, str], file_field: str, file_path: Path, mime: str) -> tuple[bytes, str]:
    boundary = "----viral-stitch-" + hashlib.sha256(os.urandom(32)).hexdigest()[:24]
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode()
    )
    body.extend(f"Content-Type: {mime}\r\n\r\n".encode())
    body.extend(file_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), boundary


def _groq_transcribe(audio_path: Path, model: str, prompt: str, language: str, timeout: int) -> dict[str, Any]:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for debate transcription.")
    fields = {
        "model": model,
        "response_format": "verbose_json",
        "timestamp_granularities[]": "word",
        "language": language,
        "temperature": "0",
        "prompt": prompt,
    }
    body, boundary = _multipart(fields, "file", audio_path, "audio/wav")
    request = urllib.request.Request(
        GROQ_API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
            "User-Agent": "viral-stitch-godmode/1.4",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Groq transcription failed with HTTP {exc.code}: {detail}") from exc


def _extract_audio_chunks(
    source: Path,
    work_dir: Path,
    chunk_seconds: int,
    ffmpeg: str,
) -> list[Path]:
    pattern = work_dir / "audio-%05d.wav"
    _run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        "-f", "segment", "-segment_time", str(chunk_seconds), "-reset_timestamps", "1", str(pattern),
    ])
    chunks = sorted(work_dir.glob("audio-*.wav"))
    if not chunks:
        raise RuntimeError("Audio extraction produced no chunks.")
    return chunks


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9']+", "", value.lower())


def _apply_glossary(text: str, glossary: dict[str, str]) -> str:
    corrected = text
    for wrong, right in sorted(glossary.items(), key=lambda item: len(item[0]), reverse=True):
        corrected = re.sub(rf"(?i)\b{re.escape(wrong)}\b", right, corrected)
    return corrected


def _words_from_response(response: dict[str, Any], offset: float, glossary: dict[str, str]) -> list[Word]:
    output: list[Word] = []
    for item in response.get("words", []):
        text = _apply_glossary(str(item.get("word", "")).strip(), glossary)
        if not text:
            continue
        probability = item.get("probability")
        output.append(Word(
            start=round(offset + float(item.get("start", 0)), 3),
            end=round(offset + float(item.get("end", item.get("start", 0))), 3),
            text=text,
            confidence=float(probability) if probability is not None else None,
        ))
    return output


def _dedupe_chunk_boundary(words: list[Word]) -> list[Word]:
    deduped: list[Word] = []
    for word in words:
        if deduped:
            previous = deduped[-1]
            same = _normalize_token(previous.text) == _normalize_token(word.text)
            overlaps = word.start <= previous.end + 0.25
            if same and overlaps:
                continue
        deduped.append(word)
    return deduped


def _sentence_segments(words: list[Word], max_seconds: float = 7.0, max_words: int = 18) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    current: list[Word] = []
    terminal = re.compile(r"[.!?][\"']?$")
    for word in words:
        current.append(word)
        duration = current[-1].end - current[0].start
        should_close = bool(terminal.search(word.text)) or len(current) >= max_words or duration >= max_seconds
        if should_close:
            segments.append(_segment_payload(current))
            current = []
    if current:
        segments.append(_segment_payload(current))
    return segments


def _segment_payload(words: list[Word]) -> dict[str, Any]:
    confidences = [word.confidence for word in words if word.confidence is not None]
    return {
        "start": words[0].start,
        "end": words[-1].end,
        "text": _join_words(word.text for word in words),
        "confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
        "speaker": words[0].speaker,
    }


def _join_words(words: Iterable[str]) -> str:
    text = " ".join(words)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([\[(])\s+", r"\1", text)
    return text.strip()


def _srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _write_srt(path: Path, segments: list[dict[str, Any]]) -> None:
    blocks = []
    for index, segment in enumerate(segments, 1):
        blocks.append(
            f"{index}\n{_srt_time(float(segment['start']))} --> {_srt_time(float(segment['end']))}\n"
            f"{segment['text']}\n"
        )
    path.write_text("\n".join(blocks), encoding="utf-8")


def _window_text(words: list[Word], start: float, end: float) -> str:
    return _join_words(word.text for word in words if word.end >= start and word.start <= end)


def _term_count(text: str, terms: set[str]) -> int:
    lower = text.lower()
    return sum(lower.count(term) for term in terms)


def _score_candidate(words: list[Word], start: float, end: float) -> ClipCandidate:
    text = _window_text(words, start, end)
    duration = end - start
    hook_zone = _window_text(words, start, min(end, start + 4.0))
    hook_hits = _term_count(hook_zone, HOOK_TERMS)
    conflict_hits = _term_count(text, CONFLICT_TERMS)
    resolution_hits = _term_count(_window_text(words, max(start, end - 9), end), RESOLUTION_TERMS)
    question_hits = text.count("?") + len(re.findall(r"\b(why|how|what|who|when|where|do you|did you)\b", text, re.I))
    quote_back = len(re.findall(r"\b(you said|your point|your claim|you just)\b", text, re.I))
    numbers = len(re.findall(r"\b\d+(?:\.\d+)?%?\b", text))
    density = len(text.split()) / max(duration, 1)
    confidence_values = [w.confidence for w in words if start <= w.start <= end and w.confidence is not None]
    confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.9
    score = (
        18 * min(hook_hits, 3)
        + 10 * min(conflict_hits, 5)
        + 12 * min(resolution_hits, 3)
        + 5 * min(question_hits, 4)
        + 8 * min(quote_back, 3)
        + 3 * min(numbers, 4)
        + 8 * min(density / 3.0, 1.0)
        + 15 * confidence
    )
    if 22 <= duration <= 65:
        score += 12
    elif duration < 15 or duration > 90:
        score -= 12
    reasons = []
    if hook_hits: reasons.append("strong opening hook")
    if conflict_hits: reasons.append("clear disagreement")
    if resolution_hits: reasons.append("payoff or admission")
    if quote_back: reasons.append("direct quote-back")
    if numbers: reasons.append("specific factual claim")
    if confidence < 0.82: reasons.append("requires caption review")
    title = _title_from_text(text)
    return ClipCandidate(
        start=round(start, 3), end=round(end, 3), title=title,
        hook=hook_zone[:220], transcript=text, score=round(score, 3),
        reasons=tuple(reasons), speakers=tuple(),
    )


def _title_from_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" .,!?:;\"")
    words = cleaned.split()
    if len(words) > 11:
        cleaned = " ".join(words[:11]) + "…"
    return cleaned or "Bigo Debate Highlight"


def _overlap(a: ClipCandidate, b: ClipCandidate) -> float:
    intersection = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    return intersection / max(0.001, min(a.end - a.start, b.end - b.start))


def find_viral_clips(words: list[Word], count: int, min_seconds: int, max_seconds: int) -> list[ClipCandidate]:
    if not words:
        return []
    total = words[-1].end
    candidates: list[ClipCandidate] = []
    stride = 8.0
    start = 0.0
    while start + min_seconds <= total:
        for duration in range(min_seconds, max_seconds + 1, 10):
            end = min(total, start + duration)
            if end - start >= min_seconds:
                candidates.append(_score_candidate(words, start, end))
        start += stride
    candidates.sort(key=lambda item: (-item.score, item.start))
    selected: list[ClipCandidate] = []
    for candidate in candidates:
        if any(_overlap(candidate, existing) > 0.55 for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) >= count:
            break
    return sorted(selected, key=lambda item: item.start)


def _long_form_chapters(words: list[Word], target_minutes: int, max_chapters: int = 12) -> list[dict[str, Any]]:
    if not words:
        return []
    total = words[-1].end
    target = min(total, target_minutes * 60)
    chapter_length = max(180.0, target / max(1, max_chapters))
    chapters = []
    cursor = 0.0
    while cursor < target:
        end = min(target, cursor + chapter_length)
        text = _window_text(words, cursor, min(end, cursor + 45))
        chapters.append({
            "start": round(cursor, 3),
            "end": round(end, 3),
            "title": _title_from_text(text),
            "summary_source": text[:600],
        })
        cursor = end
    return chapters


def command_debate(args: argparse.Namespace) -> int:
    source = Path(args.input).expanduser().resolve()
    if not source.exists() or source.suffix.lower() not in VIDEO_EXTENSIONS:
        raise FileNotFoundError(f"Unsupported or missing input video: {source}")
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    ffmpeg = _tool("ffmpeg", args.ffmpeg)
    glossary: dict[str, str] = {}
    if args.glossary:
        glossary = _read_json(Path(args.glossary))
    names = [value.strip() for value in args.panelist if value.strip()]
    prompt = (
        "This is a fast, overlapping Bigo Live panel debate. Transcribe verbatim. "
        "Do not sanitize grammar, invent words, or replace names. Preserve contractions, numbers, "
        "political and religious terminology, slang, and interruptions. Known panelists: "
        + (", ".join(names) if names else "unknown")
        + ". Preferred spellings: " + ", ".join(glossary.values())
    )
    all_words: list[Word] = []
    responses: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="viral-stitch-debate-") as temporary:
        work = Path(temporary)
        chunks = _extract_audio_chunks(source, work, args.chunk_seconds, ffmpeg)
        for index, chunk in enumerate(chunks):
            response = _groq_transcribe(chunk, args.groq_model, prompt, args.language, args.timeout)
            responses.append(response)
            all_words.extend(_words_from_response(response, index * args.chunk_seconds, glossary))
    all_words = _dedupe_chunk_boundary(all_words)
    segments = _sentence_segments(all_words)
    clips = find_viral_clips(all_words, args.short_count, args.short_min, args.short_max)
    chapters = _long_form_chapters(all_words, args.long_minutes)
    low_confidence = [segment for segment in segments if segment.get("confidence") is not None and segment["confidence"] < args.review_threshold]
    transcript_payload = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "provider": "groq",
        "model": args.groq_model,
        "language": args.language,
        "panelists": names,
        "word_count": len(all_words),
        "duration": all_words[-1].end if all_words else 0,
        "words": [word.__dict__ for word in all_words],
        "segments": segments,
        "caption_qc": {
            "review_threshold": args.review_threshold,
            "low_confidence_segment_count": len(low_confidence),
            "low_confidence_segments": low_confidence,
            "glossary_applied": glossary,
            "rule": "Do not render or publish captions until every flagged segment is reviewed against source audio.",
        },
    }
    _write_json(output / "transcript.json", transcript_payload)
    _write_srt(output / "captions-review.srt", segments)
    short_payload = []
    for number, clip in enumerate(clips, 1):
        short_payload.append({
            "id": f"short-{number:02d}",
            **clip.__dict__,
            "aspect_ratio": "9:16",
            "caption_source": "word_timestamps",
            "render_status": "blocked" if low_confidence else "ready",
            "thumbnail": {
                "skill": "image-generation",
                "tool": "image_gen",
                "required": True,
                "prompt": (
                    "Create a one-of-a-kind irresistible YouTube Shorts debate thumbnail using only accurate "
                    "visual claims from this clip. Large expressive panel faces, Bigo panel energy, clean separation, "
                    f"high contrast, no fabricated quote text. Clip title: {clip.title}. Hook: {clip.hook}"
                ),
            },
            "promotion": {
                "youtube_title": clip.title,
                "description_hook": clip.hook,
                "hashtags": ["#BigoLive", "#Debate", "#ViralShorts", "#PanelDebate"],
                "accuracy_rule": "Never place a quotation in title, thumbnail, description, or captions unless it exists verbatim in transcript.json.",
            },
        })
    _write_json(output / "viral-shorts-plan.json", short_payload)
    long_payload = {
        "title": _title_from_text(_window_text(all_words, 0, min(60, all_words[-1].end if all_words else 0))),
        "target_minutes": args.long_minutes,
        "chapters": chapters,
        "caption_source": "word_timestamps",
        "render_status": "blocked" if low_confidence else "ready",
        "thumbnail": {
            "skill": "image-generation",
            "tool": "image_gen",
            "required": True,
            "prompt": "Generate an original high-CTR YouTube debate thumbnail with accurate panelist likenesses supplied by the user, a clear conflict composition, no fake quotes, and mobile-readable text limited to 2-4 words.",
        },
        "promotion": {
            "description_requirements": [
                "State that this is an edited Bigo panel debate.",
                "Include chapter timestamps generated from the approved transcript.",
                "Do not imply a speaker admitted, lost, lied, or was exposed unless the exact transcript supports it.",
                "Use names and spellings from the approved glossary only.",
            ],
            "hashtags": ["#BigoLive", "#Debate", "#LongForm", "#PanelDiscussion"],
        },
    }
    _write_json(output / "viral-long-plan.json", long_payload)
    _write_json(output / "raw-groq-responses.json", responses)
    manifest = {
        "status": "caption_review_required" if low_confidence else "ready_for_render",
        "outputs": {
            "transcript": str(output / "transcript.json"),
            "captions": str(output / "captions-review.srt"),
            "shorts_plan": str(output / "viral-shorts-plan.json"),
            "long_plan": str(output / "viral-long-plan.json"),
        },
        "short_count": len(short_payload),
        "flagged_caption_segments": len(low_confidence),
        "next_step": "Correct flagged words, lock transcript, call image-generation skill for each selected thumbnail, then render with deterministic FFmpeg templates.",
    }
    _write_json(output / "debate-run.json", manifest)
    print(json.dumps(manifest, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="viral-stitch debate", description="Turn 1-2 hour Bigo panel debates into accurate viral shorts and long-form plans.")
    root.add_argument("--input", required=True)
    root.add_argument("--output", required=True)
    root.add_argument("--panelist", action="append", default=[])
    root.add_argument("--glossary", help="JSON object mapping common misrecognitions to approved spellings")
    root.add_argument("--groq-model", default=DEFAULT_GROQ_MODEL)
    root.add_argument("--language", default="en")
    root.add_argument("--chunk-seconds", type=int, default=900)
    root.add_argument("--short-count", type=int, default=20)
    root.add_argument("--short-min", type=int, default=25)
    root.add_argument("--short-max", type=int, default=75)
    root.add_argument("--long-minutes", type=int, default=30)
    root.add_argument("--review-threshold", type=float, default=0.82)
    root.add_argument("--timeout", type=int, default=300)
    root.add_argument("--ffmpeg")
    root.set_defaults(func=command_debate)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.func(args))
