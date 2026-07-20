from viral_stitch.visual_intelligence import (
    SpeakerTile,
    build_visual_beat,
    classify_visual_mode,
    detect_active_speaker_events,
)


def test_active_speaker_requires_stable_margin():
    tiles = [
        SpeakerTile("a", "Alpha", 0, 0, 0.5, 0.5),
        SpeakerTile("b", "Beta", 0.5, 0, 0.5, 0.5),
    ]
    frames = [
        {"timestamp": 0.0, "a": 0.92, "b": 0.21},
        {"timestamp": 0.2, "a": 0.93, "b": 0.22},
        {"timestamp": 0.4, "a": 0.91, "b": 0.20},
        {"timestamp": 0.6, "a": 0.45, "b": 0.43},
        {"timestamp": 0.8, "a": 0.20, "b": 0.92},
        {"timestamp": 1.0, "a": 0.18, "b": 0.94},
        {"timestamp": 1.2, "a": 0.17, "b": 0.91},
    ]
    events = detect_active_speaker_events(frames, tiles, minimum_hold=0.35)
    assert [event.speaker_id for event in events] == ["a", "b"]
    assert events[0].start == 0.0
    assert events[0].end == 0.6


def test_inappropriate_visual_uses_patriotic_fallback_only_when_supported():
    assert classify_visual_mode("I support America and the Constitution", inappropriate=True) == (
        "symbolic-safe", "respectful American flag background"
    )
    assert classify_visual_mode("America is evil and should be destroyed", inappropriate=True) == (
        "symbolic-safe", "neutral world or civic backdrop without patriotic endorsement"
    )
    assert classify_visual_mode("This explicit topic should not be pictured", inappropriate=True) == (
        "symbolic-safe", "neutral debate-stage background with abstract light and no explicit imagery"
    )


def test_visual_prompt_uses_verified_speaker_without_fake_winner_claim():
    beat = build_visual_beat(
        12.0,
        24.5,
        "You said the Constitution does not protect speech, but the First Amendment says otherwise.",
        "alpha",
        "Alpha",
        ["Beta"],
        "alpha-reference.png",
    )
    assert "verified active speaker is Alpha" in beat.image_prompt
    assert "must not falsely declare a winner" in beat.image_prompt
    assert beat.mode == "context-visualization"
