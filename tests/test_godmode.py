from viral_stitch.engine import quick_fingerprint
from viral_stitch.godmode import DEFAULT_MODEL, _json_from_text, audit_manifest, swarm_consensus


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


def test_quick_fingerprint_detects_identical_media(tmp_path):
    first, second = tmp_path / "one.mp4", tmp_path / "two.mov"
    first.write_bytes(b"same-media" * 100)
    second.write_bytes(first.read_bytes())
    assert quick_fingerprint(first) == quick_fingerprint(second)


def test_hundred_agent_swarm_is_complete_and_deterministic():
    catalog = {"duplicate_groups": [["a.mp4", "copy.mp4"]], "items": [
        {"path": "a.mp4", "name": "holy-cross.mp4", "valid": True, "width": 1920, "height": 1080, "duration": 8, "orientation": "landscape"},
        {"path": "copy.mp4", "name": "holy-cross-copy.mp4", "valid": True, "width": 1920, "height": 1080, "duration": 8, "orientation": "landscape"},
        {"path": "b.mp4", "name": "dog.mp4", "valid": True, "width": 720, "height": 1280, "duration": 8, "orientation": "portrait"},
    ]}
    first = swarm_consensus(catalog, "holy cross landscape", 100)
    assert first == swarm_consensus(catalog, "holy cross landscape", 100)
    assert first["completed_agents"] == 100
    assert first["consensus"][0]["path"] == "a.mp4"
    assert first["duplicate_copies_penalized"] == 1
