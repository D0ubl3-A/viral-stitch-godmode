from viral_stitch.debate import (
    Word,
    _apply_glossary,
    _dedupe_chunk_boundary,
    _sentence_segments,
    _srt_time,
    find_viral_clips,
)


def test_glossary_preserves_approved_names():
    assert _apply_glossary("press craig made the point", {"press craig": "Prez Craig"}) == "Prez Craig made the point"


def test_chunk_boundary_duplicate_is_removed():
    words = [
        Word(0.0, 0.4, "That"),
        Word(0.4, 0.8, "is"),
        Word(0.8, 1.1, "wrong"),
        Word(1.0, 1.3, "wrong"),
    ]
    assert [word.text for word in _dedupe_chunk_boundary(words)] == ["That", "is", "wrong"]


def test_sentence_segments_keep_timestamp_order():
    words = [
        Word(0.0, 0.4, "Why", 0.98),
        Word(0.4, 0.8, "is", 0.97),
        Word(0.8, 1.2, "that?", 0.96),
        Word(1.3, 1.7, "Because", 0.95),
        Word(1.7, 2.2, "facts.", 0.94),
    ]
    segments = _sentence_segments(words)
    assert len(segments) == 2
    assert segments[0]["text"] == "Why is that?"
    assert segments[0]["start"] == 0.0
    assert segments[1]["end"] == 2.2


def test_srt_time_is_millisecond_accurate():
    assert _srt_time(3661.234) == "01:01:01,234"


def test_viral_clips_prefer_conflict_and_payoff():
    words = []
    vocabulary = "wait you said that was always true but the evidence proves that is wrong you just admitted the answer exactly"
    tokens = vocabulary.split()
    for repeat in range(20):
        for index, token in enumerate(tokens):
            start = repeat * 6 + index * 0.3
            words.append(Word(start, start + 0.25, token, 0.98))
    clips = find_viral_clips(words, count=3, min_seconds=25, max_seconds=45)
    assert clips
    assert clips[0].score > 50
    assert any("disagreement" in reason for reason in clips[0].reasons)
