from viral_stitch.production_intelligence import (
    EvidenceSignal,
    classify_claim,
    compare_transcript_passes,
    fuse_speaker_evidence,
    publication_gate,
    render_quality_checks,
    score_clip_story,
    select_visual_policy,
    validate_title,
)


def test_fuses_multiple_speaker_signals():
    signals = [
        EvidenceSignal("tile_glow", "a", 0.90, 5.0),
        EvidenceSignal("audio_energy", "a", 0.88, 5.0),
        EvidenceSignal("voice_embedding", "a", 0.94, 5.0),
        EvidenceSignal("lip_motion", "b", 0.51, 5.0),
    ]
    decision = fuse_speaker_evidence(4.0, 6.0, signals)
    assert decision.status == "verified"
    assert decision.speaker_id == "a"


def test_ambiguous_speaker_is_blocked():
    signals = [
        EvidenceSignal("tile_glow", "a", 0.82, 5.0),
        EvidenceSignal("audio_energy", "b", 0.84, 5.0),
    ]
    decision = fuse_speaker_evidence(4.0, 6.0, signals)
    assert decision.status == "review"
    assert decision.speaker_id is None


def test_two_pass_transcript_dispute():
    one = [{"start": 0, "end": 2, "text": "The court ruled in 2025.", "confidence": 0.95}]
    two = [{"start": 0, "end": 2, "text": "The court ruled in 2015."}]
    disputes = compare_transcript_passes(one, two)
    assert disputes[0].status == "review"


def test_serious_allegation_requires_review():
    claim = classify_claim(0, 4, "That man committed fraud and stole the money.")
    assert claim.risk == "high"
    assert claim.requires_human_review
    assert claim.requires_source


def test_story_score_penalizes_incomplete_clip():
    complete = score_clip_story(
        "You said the law proves this, but that is false. Therefore the answer is no.",
        42, 2,
    )
    incomplete = score_clip_story(
        "But no and then—", 9, 6, crosstalk_ratio=0.5,
        starts_mid_sentence=True, ends_mid_sentence=True,
    )
    assert complete.total > incomplete.total
    assert incomplete.penalties


def test_title_does_not_invent_humiliation():
    valid, reasons = validate_title("He Was DESTROYED", "They disagreed about taxes.")
    assert not valid
    assert reasons


def test_visual_policy_uses_sources_not_generated_evidence():
    claim = classify_claim(0, 4, "The study says crime fell by 20%.")
    policy = select_visual_policy(claim, factual_source_available=True, likeness_verified=True, inappropriate=False)
    assert policy["mode"] == "source-card"
    assert not policy["allow_generated_documentary_scene"]


def test_publication_gate_blocks_failed_qa():
    decision = fuse_speaker_evidence(0, 2, [
        EvidenceSignal("manual_lock", "a", 1.0, 1.0),
        EvidenceSignal("voice_embedding", "a", 1.0, 1.0),
    ])
    disputes = compare_transcript_passes(
        [{"start": 0, "end": 2, "text": "This is correct.", "confidence": 0.99}],
        [{"start": 0, "end": 2, "text": "This is correct."}],
    )
    claim = classify_claim(0, 2, "I think this is correct.")
    checks = render_quality_checks({
        "video_decodes": True,
        "audio_duration": 2,
        "av_offset_ms": 250,
        "peak_dbfs": -1,
        "caption_safe_area": True,
        "caption_overflow_count": 0,
        "speaker_labels_verified": True,
        "generated_visual_disclosure": True,
        "black_frame_ratio": 0,
    })
    gate = publication_gate([decision], disputes, [claim], checks, (True, ()))
    assert not gate.allowed
    assert any("av_sync" in blocker for blocker in gate.blockers)
