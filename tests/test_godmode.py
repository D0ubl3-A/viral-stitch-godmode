from viral_stitch.godmode import DEFAULT_MODEL, _json_from_text, audit_manifest


def test_json_fence_parser():
    assert _json_from_text('```json\n{"ok": true}\n```') == {"ok": True}


def test_default_runtime_is_gpt_5_6():
    assert DEFAULT_MODEL == "gpt-5.6"


def test_repeated_window_is_flagged():
    manifest = {"checkpoints": [{"shots": [
        {"source": "a.mp4", "source_start": 1, "duration": 2, "label": "one"},
        {"source": "a.mp4", "source_start": 2, "duration": 2, "label": "two"},
    ]}]}
    report = audit_manifest(manifest)
    assert any(issue["type"] == "repeated_source_window" for issue in report["issues"])


def test_forbidden_source_fails():
    manifest = {"forbidden_patterns": ["dog"], "checkpoints": [{"shots": [{"source": "dog.mp4", "source_start": 0, "duration": 1}]}]}
    assert audit_manifest(manifest)["status"] == "fail"
