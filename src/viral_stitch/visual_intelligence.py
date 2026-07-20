from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


INAPPROPRIATE_VISUAL_TOPICS = {
    "graphic sexual content", "sexual violence", "graphic gore", "self-harm depiction",
    "child sexual content", "extremist propaganda", "dehumanizing protected-class imagery",
}

AMERICA_POSITIVE = {
    "america first", "support america", "pro america", "american values", "patriot",
    "constitution", "bill of rights", "freedom", "veteran", "support our troops",
}

AMERICA_CRITICAL = {
    "anti america", "against america", "america is evil", "burn the flag",
    "destroy america", "death to america",
}


@dataclass(frozen=True)
class SpeakerTile:
    speaker_id: str
    display_name: str
    x: float
    y: float
    width: float
    height: float
    reference_image: str | None = None


@dataclass(frozen=True)
class SpeakerEvent:
    start: float
    end: float
    speaker_id: str
    confidence: float
    evidence: str


@dataclass(frozen=True)
class VisualBeat:
    start: float
    end: float
    active_speaker: str
    transcript: str
    mode: str
    subject: str
    image_prompt: str
    editorial_purpose: str
    accuracy_gate: str


def load_tile_map(path: Path) -> list[SpeakerTile]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [SpeakerTile(**row) for row in payload["tiles"]]


def detect_active_speaker_events(
    frame_metrics: list[dict[str, Any]],
    tiles: list[SpeakerTile],
    minimum_hold: float = 0.35,
    confidence_floor: float = 0.58,
) -> list[SpeakerEvent]:
    """Convert sampled Bigo tile-border metrics into stable speaker intervals.

    Each frame metric must contain timestamp and one score per speaker_id. Scores should
    combine border luminance, saturation change, animated glow, and mouth-motion energy.
    This function deliberately rejects ambiguous ties rather than inventing a speaker.
    """
    events: list[SpeakerEvent] = []
    current_id: str | None = None
    current_start = 0.0
    current_scores: list[float] = []
    last_time = 0.0
    valid_ids = {tile.speaker_id for tile in tiles}

    for frame in sorted(frame_metrics, key=lambda row: float(row["timestamp"])):
        timestamp = float(frame["timestamp"])
        scores = [(speaker_id, float(frame.get(speaker_id, 0.0))) for speaker_id in valid_ids]
        scores.sort(key=lambda item: (-item[1], item[0]))
        winner, winner_score = scores[0] if scores else (None, 0.0)
        runner_up = scores[1][1] if len(scores) > 1 else 0.0
        margin = winner_score - runner_up
        confident = winner is not None and winner_score >= confidence_floor and margin >= 0.08
        detected = winner if confident else None

        if detected != current_id:
            if current_id is not None and timestamp - current_start >= minimum_hold:
                events.append(SpeakerEvent(
                    start=round(current_start, 3),
                    end=round(timestamp, 3),
                    speaker_id=current_id,
                    confidence=round(sum(current_scores) / max(1, len(current_scores)), 4),
                    evidence="Bigo active-tile glow plus mouth-motion consensus",
                ))
            current_id = detected
            current_start = timestamp
            current_scores = [winner_score] if detected else []
        elif detected is not None:
            current_scores.append(winner_score)
        last_time = timestamp

    if current_id is not None and last_time - current_start >= minimum_hold:
        events.append(SpeakerEvent(
            start=round(current_start, 3),
            end=round(last_time, 3),
            speaker_id=current_id,
            confidence=round(sum(current_scores) / max(1, len(current_scores)), 4),
            evidence="Bigo active-tile glow plus mouth-motion consensus",
        ))
    return events


def speaker_at(events: list[SpeakerEvent], timestamp: float) -> str | None:
    candidates = [event for event in events if event.start <= timestamp <= event.end]
    if not candidates:
        return None
    return max(candidates, key=lambda event: event.confidence).speaker_id


def classify_visual_mode(transcript: str, inappropriate: bool = False) -> tuple[str, str]:
    lower = transcript.lower()
    if inappropriate:
        if any(term in lower for term in AMERICA_POSITIVE):
            return "symbolic-safe", "respectful American flag background"
        if any(term in lower for term in AMERICA_CRITICAL):
            return "symbolic-safe", "neutral world or civic backdrop without patriotic endorsement"
        return "symbolic-safe", "neutral debate-stage background with abstract light and no explicit imagery"

    if any(term in lower for term in ("constitution", "first amendment", "second amendment", "supreme court")):
        return "context-visualization", "cinematic American constitutional and courthouse imagery"
    if any(term in lower for term in ("war", "military", "veteran", "troops", "america", "united states")):
        return "context-visualization", "accurate American civic or military context appropriate to the exact statement"
    if any(term in lower for term in ("bible", "god", "jesus", "church", "religion", "faith")):
        return "context-visualization", "respectful symbolic faith imagery matching the exact discussed concept"
    if any(term in lower for term in ("money", "economy", "tax", "inflation", "jobs", "business")):
        return "context-visualization", "clear economic or everyday cost-of-living visualization"
    if any(term in lower for term in ("crime", "police", "law", "court", "jail")):
        return "context-visualization", "non-graphic legal, courtroom, police-light, or city context"
    return "speaker-dominant", "active speaker and opponent reaction composition"


def build_visual_beat(
    start: float,
    end: float,
    transcript: str,
    active_speaker: str,
    speaker_name: str,
    opponent_names: list[str],
    reference_image: str | None,
    inappropriate: bool = False,
) -> VisualBeat:
    mode, subject = classify_visual_mode(transcript, inappropriate=inappropriate)
    opponents = ", ".join(opponent_names) if opponent_names else "the opposing panelists"
    prompt = (
        "Create a production-ready vertical debate visual for a viral short. "
        f"Timestamp {start:.3f}-{end:.3f}. The verified active speaker is {speaker_name}; "
        "their Bigo tile is lit during this interval. Keep their likeness consistent with the supplied "
        f"reference image ({reference_image or 'reference required before generation'}). "
        f"Show {speaker_name} delivering the point with confidence while {opponents} appear only as accurate, "
        "non-humiliating reaction context. Do not invent expressions, gestures, quotes, admissions, or events. "
        f"Visual mode: {mode}. Supporting subject: {subject}. Transcript context: {transcript}. "
        "Use a high-retention debate composition: immediate focal face, clear challenger-versus-response structure, "
        "mobile readability, strong depth, and room for verified captions. The point may feel decisive or like the "
        "speaker served the rebuttal cleanly, but the image must not falsely declare a winner or fabricate misconduct."
    )
    return VisualBeat(
        start=round(start, 3),
        end=round(end, 3),
        active_speaker=active_speaker,
        transcript=transcript,
        mode=mode,
        subject=subject,
        image_prompt=prompt,
        editorial_purpose="Make the argument visually immediate, memorable, and shareable without changing its meaning.",
        accuracy_gate="Generate only after speaker timestamp, transcript, names, reference image, and context are approved.",
    )


def export_visual_plan(path: Path, beats: list[VisualBeat], events: list[SpeakerEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1,
        "speaker_events": [asdict(event) for event in events],
        "visual_beats": [asdict(beat) for beat in beats],
        "rules": {
            "active_speaker": "Use the lit Bigo tile and timestamp evidence; reject ambiguous frames.",
            "context": "Visualize the actual discussed concept when suitable.",
            "fallback": "For inappropriate explicit visualization, use symbolic-safe patriotic or neutral context based on the speaker's actual stance.",
            "debate_framing": "Emphasize decisive rebuttals and reactions, but never fabricate a winner, quote, admission, or humiliation.",
            "image_generation": "Call image_gen with approved panelist reference images for every generated likeness.",
        },
    }, indent=2, ensure_ascii=False), encoding="utf-8")
