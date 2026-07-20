from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

RISKY_ALLEGATION_TERMS = {
    "murdered", "raped", "stole", "fraud", "terrorist", "pedophile", "criminal",
    "corrupt", "traitor", "abuser", "groomer", "scammer", "cheated", "rigged",
}
FACTUAL_CLAIM_TERMS = {
    "percent", "study", "statistics", "data", "law", "illegal", "legal", "court",
    "supreme court", "constitution", "election", "crime rate", "research", "proves",
}
HUMILIATION_TERMS = {
    "destroyed", "humiliated", "owned", "obliterated", "ended", "cooked", "exposed",
    "speechless", "had no answer", "admitted defeat", "served on a plate",
}
SETUP_TERMS = {"because", "the issue", "the question", "you said", "your claim", "here's why"}
PAYOFF_TERMS = {"therefore", "that's why", "bottom line", "which means", "the answer is", "exactly"}


@dataclass(frozen=True)
class EvidenceSignal:
    source: str
    speaker_id: str | None
    confidence: float
    timestamp: float
    details: str = ""


@dataclass(frozen=True)
class SpeakerDecision:
    start: float
    end: float
    speaker_id: str | None
    confidence: float
    status: str
    evidence: tuple[str, ...]
    alternatives: tuple[str, ...] = ()


@dataclass(frozen=True)
class TranscriptDispute:
    start: float
    end: float
    pass_one: str
    pass_two: str
    normalized_similarity: float
    named_entities: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class ClaimAssessment:
    start: float
    end: float
    text: str
    claim_type: str
    risk: str
    requires_source: bool
    requires_human_review: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class StoryScore:
    total: float
    setup: float
    conflict: float
    payoff: float
    context_independence: float
    audio_clarity: float
    penalties: tuple[str, ...]


@dataclass(frozen=True)
class PublicationGate:
    allowed: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    audit_hash: str


@dataclass(frozen=True)
class SpeakerIdentity:
    speaker_id: str
    display_name: str
    tile_history: tuple[str, ...] = ()
    voice_embedding_ref: str | None = None
    face_embedding_ref: str | None = None
    reference_image: str | None = None
    moderator: bool = False


@dataclass
class DebateAudit:
    source_video: str
    transcript_passes: int
    speaker_decisions: list[SpeakerDecision] = field(default_factory=list)
    disputes: list[TranscriptDispute] = field(default_factory=list)
    claims: list[ClaimAssessment] = field(default_factory=list)
    generated_visuals_disclosed: bool = True
    render_checks: dict[str, bool] = field(default_factory=dict)

    def write(self, path: Path) -> None:
        payload = asdict(self)
        payload["schema_version"] = 2
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def normalize_text(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def token_similarity(a: str, b: str) -> float:
    left, right = normalize_text(a).split(), normalize_text(b).split()
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    left_set, right_set = set(left), set(right)
    jaccard = len(left_set & right_set) / max(1, len(left_set | right_set))
    positional = sum(1 for x, y in zip(left, right) if x == y) / max(len(left), len(right))
    return round(0.65 * jaccard + 0.35 * positional, 4)


def fuse_speaker_evidence(
    start: float,
    end: float,
    signals: Iterable[EvidenceSignal],
    weights: dict[str, float] | None = None,
    minimum_confidence: float = 0.68,
    ambiguity_margin: float = 0.10,
) -> SpeakerDecision:
    """Fuse tile glow, audio energy, voice identity, lip motion, and continuity.

    Ambiguous intervals remain unresolved; the function never invents attribution.
    """
    weights = weights or {
        "voice_embedding": 1.35,
        "audio_energy": 1.05,
        "lip_motion": 1.00,
        "tile_glow": 0.85,
        "continuity": 0.65,
        "manual_lock": 3.00,
    }
    scores: dict[str, float] = {}
    evidence: dict[str, list[str]] = {}
    total_weight = 0.0
    for signal in signals:
        if signal.speaker_id is None or not (start <= signal.timestamp <= end):
            continue
        weight = weights.get(signal.source, 0.5)
        contribution = clamp(signal.confidence) * weight
        scores[signal.speaker_id] = scores.get(signal.speaker_id, 0.0) + contribution
        evidence.setdefault(signal.speaker_id, []).append(
            f"{signal.source}:{signal.confidence:.2f}{' (' + signal.details + ')' if signal.details else ''}"
        )
        total_weight += weight
    if not scores or total_weight <= 0:
        return SpeakerDecision(start, end, None, 0.0, "review", ("no usable speaker evidence",))

    ranked = sorted(scores.items(), key=lambda row: (-row[1], row[0]))
    winner, winner_score = ranked[0]
    runner_score = ranked[1][1] if len(ranked) > 1 else 0.0
    confidence = clamp(winner_score / max(total_weight, winner_score))
    margin = clamp((winner_score - runner_score) / max(winner_score, 0.001))
    alternatives = tuple(name for name, _ in ranked[1:3])
    if confidence < minimum_confidence or margin < ambiguity_margin:
        return SpeakerDecision(
            start, end, None, round(confidence, 4), "review",
            tuple(evidence.get(winner, ())) + (f"ambiguity margin:{margin:.2f}",), alternatives,
        )
    return SpeakerDecision(
        start, end, winner, round(confidence, 4), "verified",
        tuple(evidence.get(winner, ())) + (f"winner margin:{margin:.2f}",), alternatives,
    )


def compare_transcript_passes(
    segments_one: list[dict[str, Any]],
    segments_two: list[dict[str, Any]],
    similarity_floor: float = 0.88,
) -> list[TranscriptDispute]:
    disputes: list[TranscriptDispute] = []
    for first in segments_one:
        overlapping = [
            second for second in segments_two
            if float(second["end"]) >= float(first["start"]) and float(second["start"]) <= float(first["end"])
        ]
        second_text = " ".join(str(row.get("text", "")) for row in overlapping).strip()
        similarity = token_similarity(str(first.get("text", "")), second_text)
        entities = tuple(sorted(set(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", str(first.get("text", ""))))))
        low_confidence = float(first.get("confidence") or 1.0) < 0.84
        status = "review" if similarity < similarity_floor or low_confidence else "verified"
        disputes.append(TranscriptDispute(
            start=float(first["start"]), end=float(first["end"]),
            pass_one=str(first.get("text", "")), pass_two=second_text,
            normalized_similarity=similarity, named_entities=entities, status=status,
        ))
    return disputes


def classify_claim(start: float, end: float, text: str) -> ClaimAssessment:
    lower = text.lower()
    reasons: list[str] = []
    allegation = any(term in lower for term in RISKY_ALLEGATION_TERMS)
    factual = any(term in lower for term in FACTUAL_CLAIM_TERMS) or bool(re.search(r"\b\d+(?:\.\d+)?%\b", text))
    personal = bool(re.search(r"\b(i saw|i experienced|in my experience|what happened to me)\b", lower))
    prediction = bool(re.search(r"\b(will|going to|probably|likely|predict)\b", lower))

    if allegation:
        claim_type, risk = "serious allegation", "high"
        reasons.append("potentially defamatory or reputation-damaging allegation")
    elif factual:
        claim_type, risk = "factual assertion", "medium"
        reasons.append("externally verifiable factual claim")
    elif personal:
        claim_type, risk = "personal experience", "medium"
        reasons.append("personal account should be attributed, not presented as independently verified fact")
    elif prediction:
        claim_type, risk = "prediction", "low"
        reasons.append("future-looking statement")
    else:
        claim_type, risk = "opinion", "low"
        reasons.append("primarily evaluative or rhetorical statement")

    return ClaimAssessment(
        start=start, end=end, text=text, claim_type=claim_type, risk=risk,
        requires_source=factual or allegation,
        requires_human_review=allegation,
        reasons=tuple(reasons),
    )


def score_clip_story(
    transcript: str,
    duration: float,
    speaker_count: int,
    crosstalk_ratio: float = 0.0,
    silence_ratio: float = 0.0,
    starts_mid_sentence: bool = False,
    ends_mid_sentence: bool = False,
) -> StoryScore:
    lower = transcript.lower()
    setup = min(1.0, 0.25 + 0.18 * sum(term in lower[:300] for term in SETUP_TERMS))
    conflict = min(1.0, 0.2 + 0.12 * len(re.findall(r"\b(wrong|false|but|however|answer|contradiction|no)\b", lower)))
    payoff = min(1.0, 0.15 + 0.18 * sum(term in lower[-350:] for term in PAYOFF_TERMS))
    context_independence = 1.0
    audio_clarity = clamp(1.0 - crosstalk_ratio * 0.8 - silence_ratio * 0.6)
    penalties: list[str] = []

    if starts_mid_sentence:
        context_independence -= 0.28
        penalties.append("starts mid-sentence")
    if ends_mid_sentence:
        payoff -= 0.30
        penalties.append("ends before response or payoff")
    if speaker_count > 4:
        context_independence -= min(0.35, (speaker_count - 4) * 0.08)
        penalties.append("too many speakers for a self-contained short")
    if duration < 15:
        penalties.append("too brief for complete debate context")
        context_independence -= 0.18
    if duration > 95:
        penalties.append("too long for short-form retention")
        context_independence -= 0.12
    if crosstalk_ratio > 0.25:
        penalties.append("heavy crosstalk")
    if silence_ratio > 0.15:
        penalties.append("excess dead air")

    setup, conflict, payoff, context_independence = map(clamp, (setup, conflict, payoff, context_independence))
    total = 100 * (0.20 * setup + 0.25 * conflict + 0.25 * payoff + 0.18 * context_independence + 0.12 * audio_clarity)
    total -= 3.0 * len(penalties)
    return StoryScore(
        total=round(max(0.0, total), 2), setup=round(setup, 3), conflict=round(conflict, 3),
        payoff=round(payoff, 3), context_independence=round(context_independence, 3),
        audio_clarity=round(audio_clarity, 3), penalties=tuple(penalties),
    )


def validate_title(title: str, transcript: str, human_approved: bool = False) -> tuple[bool, tuple[str, ...]]:
    lower_title = title.lower()
    reasons: list[str] = []
    for term in HUMILIATION_TERMS:
        if term in lower_title and term not in transcript.lower() and not human_approved:
            reasons.append(f"unsupported humiliation framing: {term}")
    quoted = re.findall(r'["“](.+?)["”]', title)
    normalized_transcript = normalize_text(transcript)
    for quote in quoted:
        if normalize_text(quote) not in normalized_transcript:
            reasons.append("title contains a quote not found verbatim in the locked transcript")
    return not reasons, tuple(reasons)


def select_visual_policy(
    claim: ClaimAssessment,
    factual_source_available: bool,
    likeness_verified: bool,
    inappropriate: bool,
) -> dict[str, Any]:
    if claim.risk == "high":
        return {
            "mode": "speaker-dominant",
            "allow_generated_documentary_scene": False,
            "disclosure_required": True,
            "reason": "serious allegation: preserve source panel and avoid dramatizing an unverified event",
        }
    if inappropriate:
        return {
            "mode": "symbolic-safe",
            "allow_generated_documentary_scene": False,
            "disclosure_required": True,
            "reason": "explicit or inappropriate subject requires non-literal symbolic treatment",
        }
    if claim.requires_source and factual_source_available:
        return {
            "mode": "source-card",
            "allow_generated_documentary_scene": False,
            "disclosure_required": False,
            "reason": "use the real source, document, map, or statistic instead of generated evidence",
        }
    return {
        "mode": "context-illustration" if likeness_verified else "abstract-context",
        "allow_generated_documentary_scene": False,
        "disclosure_required": True,
        "reason": "generated imagery is illustrative only and must not resemble documentary evidence",
    }


def long_form_edit_plan(segments: list[dict[str, Any]], chapter_target_seconds: int = 420) -> dict[str, Any]:
    chapters: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    chapter_start = 0.0
    for segment in segments:
        if not current:
            chapter_start = float(segment["start"])
        current.append(segment)
        elapsed = float(segment["end"]) - chapter_start
        if elapsed >= chapter_target_seconds or str(segment.get("text", "")).rstrip().endswith((".", "?", "!")) and elapsed >= chapter_target_seconds * 0.72:
            text = " ".join(str(row.get("text", "")) for row in current)
            chapters.append({
                "start": round(chapter_start, 3),
                "end": round(float(current[-1]["end"]), 3),
                "working_title": " ".join(text.split()[:10]) or "Debate chapter",
                "required_edits": [
                    "remove dead air and repeated points",
                    "normalize loudness and reduce abrupt level changes",
                    "stabilize speaker layout and preserve source context",
                    "add verified speaker labels and caption-safe margins",
                    "insert sourced claim cards only where evidence is available",
                    "add a visual reset or recap without changing the argument",
                ],
            })
            current = []
    if current:
        text = " ".join(str(row.get("text", "")) for row in current)
        chapters.append({
            "start": round(chapter_start, 3), "end": round(float(current[-1]["end"]), 3),
            "working_title": " ".join(text.split()[:10]) or "Debate chapter",
            "required_edits": ["finish on a complete response", "normalize audio", "preserve verified captions"],
        })
    return {
        "chapters": chapters,
        "global_rules": {
            "dead_air": "remove pauses longer than editorially useful while preserving meaning",
            "repetition": "compress repeated claims but never splice words into a new sentence",
            "audio": "target consistent dialogue loudness and prevent clipping",
            "captions": "respect mobile safe areas and speaker labels",
            "sources": "distinguish speaker claims from independently verified facts",
        },
    }


def render_quality_checks(metrics: dict[str, Any]) -> dict[str, bool]:
    return {
        "video_decodes": bool(metrics.get("video_decodes", False)),
        "audio_present": float(metrics.get("audio_duration", 0)) > 0,
        "av_sync": abs(float(metrics.get("av_offset_ms", 9999))) <= 80,
        "no_clipping": float(metrics.get("peak_dbfs", 1.0)) <= -0.1,
        "caption_safe_area": bool(metrics.get("caption_safe_area", False)),
        "caption_overflow_free": int(metrics.get("caption_overflow_count", 1)) == 0,
        "speaker_labels_verified": bool(metrics.get("speaker_labels_verified", False)),
        "generated_visual_disclosure": bool(metrics.get("generated_visual_disclosure", False)),
        "black_frame_rate_ok": float(metrics.get("black_frame_ratio", 1.0)) < 0.01,
    }


def publication_gate(
    decisions: list[SpeakerDecision],
    disputes: list[TranscriptDispute],
    claims: list[ClaimAssessment],
    render_checks: dict[str, bool],
    title_validation: tuple[bool, tuple[str, ...]],
) -> PublicationGate:
    blockers: list[str] = []
    warnings: list[str] = []
    if any(decision.status != "verified" for decision in decisions):
        blockers.append("one or more speaker intervals are unresolved")
    if any(dispute.status != "verified" for dispute in disputes):
        blockers.append("two-pass transcript disagreement requires source-audio review")
    if any(claim.requires_human_review for claim in claims):
        blockers.append("serious allegation requires human editorial review")
    failed_checks = sorted(name for name, passed in render_checks.items() if not passed)
    if failed_checks:
        blockers.append("render QA failed: " + ", ".join(failed_checks))
    if not title_validation[0]:
        blockers.extend(title_validation[1])
    if any(claim.requires_source and not claim.requires_human_review for claim in claims):
        warnings.append("factual claims should be labeled as speaker claims unless supporting sources are attached")

    digest_payload = json.dumps({
        "decisions": [asdict(row) for row in decisions],
        "disputes": [asdict(row) for row in disputes],
        "claims": [asdict(row) for row in claims],
        "render_checks": render_checks,
        "title": title_validation,
    }, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return PublicationGate(
        allowed=not blockers,
        blockers=tuple(blockers), warnings=tuple(warnings),
        audit_hash=hashlib.sha256(digest_payload).hexdigest(),
    )


def platform_export_spec(platform: str) -> dict[str, Any]:
    specs = {
        "youtube_shorts": {"aspect": "9:16", "max_seconds": 180, "caption_safe_bottom": 0.20},
        "tiktok": {"aspect": "9:16", "max_seconds": 600, "caption_safe_bottom": 0.24},
        "instagram_reels": {"aspect": "9:16", "max_seconds": 180, "caption_safe_bottom": 0.22},
        "youtube_long": {"aspect": "16:9", "max_seconds": None, "caption_safe_bottom": 0.12},
    }
    if platform not in specs:
        raise ValueError(f"Unsupported platform: {platform}")
    return specs[platform]
