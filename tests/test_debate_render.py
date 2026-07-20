from viral_stitch.debate_render import _clip_segments, _srt_time


def test_clip_segments_rebases_word_timestamps():
    words = [
        {"start": 10.0, "end": 10.4, "text": "You"},
        {"start": 10.4, "end": 10.8, "text": "said"},
        {"start": 10.8, "end": 11.2, "text": "that."},
    ]
    segments = _clip_segments(words, 10.0, 12.0)
    assert segments[0]["start"] == 0.0
    assert round(segments[0]["end"], 3) == 1.2
    assert segments[0]["text"] == "You said that."


def test_render_srt_time():
    assert _srt_time(65.5) == "00:01:05,500"
