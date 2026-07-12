from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


VIDEO_EXTENSIONS = {
    ".3gp", ".avi", ".flv", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4",
    ".mpeg", ".mpg", ".mts", ".ogv", ".ts", ".vob", ".webm", ".wmv",
}
DEFAULT_FFMPEG = Path(r"D:\Downloads\ffmpeg\ffmpeg-8.1-essentials_build\bin\ffmpeg.exe")
DEFAULT_FFPROBE = Path(r"D:\Downloads\ffmpeg\ffmpeg-8.1-essentials_build\bin\ffprobe.exe")
NULL_SINK = "NUL" if os.name == "nt" else "/dev/null"


def locate_tool(name: str, explicit: str | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    found = shutil.which(name)
    if found:
        candidates.append(Path(found))
    candidates.append(DEFAULT_FFMPEG if name.startswith("ffmpeg") else DEFAULT_FFPROBE)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(f"Could not locate {name}; pass an explicit tool path")


def printable(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def run_text(command: list[str], capture: bool = False) -> str:
    print(printable(command), flush=True)
    result = subprocess.run(command, check=True, text=True, capture_output=capture)
    return (result.stdout or "") + (result.stderr or "")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolved(value: str, base: Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def slug(text: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return clean[:48] or "checkpoint"


def quick_fingerprint(path: Path, sample_size: int = 1_048_576) -> str:
    """Identify duplicate media without reading multi-gigabyte files in full."""
    size = path.stat().st_size
    digest = hashlib.sha256()
    digest.update(str(size).encode("ascii"))
    with path.open("rb") as stream:
        digest.update(stream.read(sample_size))
        if size > sample_size:
            stream.seek(max(0, size - sample_size))
            digest.update(stream.read(sample_size))
    return digest.hexdigest()


def probe(path: Path, ffprobe: Path) -> dict[str, Any]:
    raw = run_text([
        str(ffprobe), "-v", "error", "-show_entries",
        "format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,duration,"
        "nb_frames,r_frame_rate,avg_frame_rate,pix_fmt,sample_rate,channels,disposition",
        "-of", "json", str(path),
    ], capture=True)
    data = json.loads(raw)
    data["path"] = str(path)
    return data


def first_video(probe_data: dict[str, Any]) -> dict[str, Any] | None:
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") != "video":
            continue
        if stream.get("disposition", {}).get("attached_pic") == 1:
            continue
        return stream
    return None


def first_audio(probe_data: dict[str, Any]) -> dict[str, Any] | None:
    return next((s for s in probe_data.get("streams", []) if s.get("codec_type") == "audio"), None)


def stream_duration(probe_data: dict[str, Any], stream: dict[str, Any] | None) -> float:
    if stream:
        value = stream.get("duration")
        if value not in (None, "N/A"):
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return float(probe_data.get("format", {}).get("duration", 0.0) or 0.0)


def parse_rate(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    numerator, denominator = value.split("/", 1)
    return float(numerator) / float(denominator)


def duration_tolerance(stream: dict[str, Any] | None) -> float:
    fps = parse_rate(stream.get("avg_frame_rate") if stream else None)
    return max(0.12, 2.0 / fps) if fps else 0.12


def cached_video_is_valid(
    path: Path,
    ffprobe: Path,
    expected: float,
    minimum_size: int,
    allow_frame_padding: bool = False,
) -> bool:
    if not path.exists() or path.stat().st_size <= minimum_size:
        return False
    try:
        media = probe(path, ffprobe)
        video = first_video(media)
        actual = stream_duration(media, video)
        tolerance = duration_tolerance(video)
        if allow_frame_padding:
            return bool(video and expected - tolerance <= actual <= expected + 1.0)
        return bool(video and abs(actual - expected) <= tolerance)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.SubprocessError):
        return False


def require_video_duration(
    path: Path,
    ffprobe: Path,
    expected: float,
    label: str,
    allow_frame_padding: bool = False,
) -> float:
    media = probe(path, ffprobe)
    video = first_video(media)
    actual = stream_duration(media, video)
    tolerance = duration_tolerance(video)
    valid = (
        expected - tolerance <= actual <= expected + 1.0
        if allow_frame_padding
        else abs(actual - expected) <= tolerance
    )
    if not video or not valid:
        raise RuntimeError(
            f"{label} video duration {actual:.3f}s; expected {expected:.3f}s (+/- {tolerance:.3f}s)"
        )
    return actual


def loudness_measure(ffmpeg: Path, audio: Path, duration: float, target: float, peak: float) -> dict[str, str]:
    raw = run_text([
        str(ffmpeg), "-hide_banner", "-nostats", "-i", str(audio),
        "-map", "0:a:0", "-t", f"{duration:.6f}",
        "-af", f"loudnorm=I={target}:TP={peak}:LRA=11:print_format=json",
        "-f", "null", NULL_SINK,
    ], capture=True)
    matches = re.findall(r'\{\s*"input_i".*?\}', raw, flags=re.DOTALL)
    if not matches:
        raise RuntimeError("Could not parse loudness analysis")
    return json.loads(matches[-1])


def command_inventory(args: argparse.Namespace) -> int:
    ffprobe = locate_tool("ffprobe", args.ffprobe)
    excluded = [re.compile(pattern, re.IGNORECASE) for pattern in args.exclude]
    cutoff = datetime.now() - timedelta(minutes=args.since_minutes) if args.since_minutes else None
    records: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for root_value in args.roots:
        root = Path(root_value).resolve()
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            path = path.resolve()
            if path in seen:
                continue
            seen.add(path)
            stat = path.stat()
            if cutoff and datetime.fromtimestamp(stat.st_mtime) < cutoff:
                continue
            blocked = next((pattern.pattern for pattern in excluded if pattern.search(str(path))), None)
            try:
                media = probe(path, ffprobe)
                video = first_video(media)
                duration = float(media.get("format", {}).get("duration", 0.0) or 0.0)
                valid = bool(video and duration > 0.05 and stat.st_size > 16_384)
                width = int(video.get("width", 0)) if video else 0
                height = int(video.get("height", 0)) if video else 0
                orientation = "portrait" if height > width else "landscape"
                records.append({
                    "path": str(path),
                    "name": path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "duration": duration,
                    "width": width,
                    "height": height,
                    "orientation": orientation,
                    "codec": video.get("codec_name") if video else None,
                    "fps": parse_rate(video.get("avg_frame_rate") if video else None),
                    "fingerprint": quick_fingerprint(path),
                    "excluded": blocked,
                    "valid": valid and blocked is None,
                })
            except Exception as exc:  # Keep inventory useful when one source is corrupt.
                records.append({"path": str(path), "valid": False, "error": str(exc), "excluded": blocked})
    records.sort(key=lambda item: (not item.get("valid", False), item.get("path", "")))
    fingerprints: dict[str, list[str]] = {}
    for row in records:
        if row.get("valid") and row.get("fingerprint"):
            fingerprints.setdefault(row["fingerprint"], []).append(row["path"])
    format_counts: dict[str, int] = {}
    orientation_counts: dict[str, int] = {}
    for row in records:
        if not row.get("valid"):
            continue
        extension = Path(row["path"]).suffix.lower()
        format_counts[extension] = format_counts.get(extension, 0) + 1
        orientation = row.get("orientation", "unknown")
        orientation_counts[orientation] = orientation_counts.get(orientation, 0) + 1
    payload = {
        "created": datetime.now().isoformat(),
        "roots": [str(Path(root).resolve()) for root in args.roots],
        "valid_count": sum(1 for row in records if row.get("valid")),
        "excluded_count": sum(1 for row in records if row.get("excluded")),
        "total_duration": round(sum(float(row.get("duration", 0)) for row in records if row.get("valid")), 3),
        "total_bytes": sum(int(row.get("size", 0)) for row in records if row.get("valid")),
        "format_counts": dict(sorted(format_counts.items())),
        "orientation_counts": dict(sorted(orientation_counts.items())),
        "duplicate_groups": [paths for paths in fingerprints.values() if len(paths) > 1],
        "items": records,
    }
    write_json(Path(args.output).resolve(), payload)
    print(f"INVENTORY={Path(args.output).resolve()}")
    print(f"VALID={payload['valid_count']} EXCLUDED={payload['excluded_count']}")
    return 0


def decode_audio(ffmpeg: Path, audio: Path, sample_rate: int = 22050) -> tuple[Any, int]:
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Audio beat analysis requires numpy") from exc
    command = [
        str(ffmpeg), "-v", "error", "-i", str(audio), "-map", "0:a:0",
        "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1",
    ]
    print(printable(command), flush=True)
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return np.frombuffer(result.stdout, dtype=np.float32), sample_rate


def detect_beats(samples: Any, sample_rate: int) -> dict[str, Any]:
    import numpy as np

    frame_size = 2048
    hop = 512
    if len(samples) < frame_size * 4:
        raise RuntimeError("Audio is too short for beat analysis")
    window = np.hanning(frame_size).astype(np.float32)
    frame_count = 1 + (len(samples) - frame_size) // hop
    onset = np.zeros(frame_count, dtype=np.float64)
    previous: Any = None
    for index in range(frame_count):
        start = index * hop
        spectrum = np.abs(np.fft.rfft(samples[start : start + frame_size] * window))
        spectrum = np.log1p(spectrum)
        if previous is not None:
            onset[index] = np.maximum(spectrum - previous, 0.0).sum()
        previous = spectrum
    onset = np.maximum(onset - np.median(onset), 0.0)
    onset = np.convolve(onset, np.array([0.2, 0.6, 0.2]), mode="same")
    scale = np.percentile(onset, 95) or 1.0
    onset /= scale

    bpm_candidates = np.arange(70.0, 171.0, 0.25)
    scores = []
    for bpm in bpm_candidates:
        lag = max(1, int(round((60.0 / bpm) * sample_rate / hop)))
        scores.append(float(np.dot(onset[:-lag], onset[lag:])))
    scores_array = np.asarray(scores)
    best = int(np.argmax(scores_array))
    bpm = float(bpm_candidates[best])
    lag = max(1, int(round((60.0 / bpm) * sample_rate / hop)))
    phase_scores = np.array([onset[phase::lag].sum() for phase in range(lag)])
    phase = int(np.argmax(phase_scores))
    beat_frames = np.arange(phase, frame_count, lag)
    beat_times = beat_frames * hop / sample_rate
    duration = len(samples) / sample_rate
    beat_times = beat_times[beat_times <= duration]
    median_score = float(np.median(scores_array)) or 1.0
    confidence = float(scores_array[best] / median_score)
    peak_indices = np.where(
        (onset[1:-1] > onset[:-2]) & (onset[1:-1] >= onset[2:]) & (onset[1:-1] > 0.55)
    )[0] + 1
    return {
        "duration": round(duration, 6),
        "sample_rate": sample_rate,
        "estimated_bpm": round(bpm, 3),
        "beat_period": round(60.0 / bpm, 6),
        "confidence": round(confidence, 3),
        "beats": [round(float(value), 3) for value in beat_times],
        "four_beat_cuts": [round(float(value), 3) for value in beat_times[::4]],
        "onset_peaks": [round(float(value * hop / sample_rate), 3) for value in peak_indices],
        "timing_basis": "spectral-flux beat estimate; verify against lyrics and waveform",
    }


def command_analyze_audio(args: argparse.Namespace) -> int:
    ffmpeg = locate_tool("ffmpeg", args.ffmpeg)
    audio = Path(args.audio).resolve()
    samples, rate = decode_audio(ffmpeg, audio)
    payload = detect_beats(samples, rate)
    measured = loudness_measure(ffmpeg, audio, payload["duration"], -14.0, -1.5)
    payload["source_loudness"] = measured
    payload["audio"] = str(audio)
    write_json(Path(args.output).resolve(), payload)
    print(f"ANALYSIS={Path(args.output).resolve()}")
    print(f"BPM={payload['estimated_bpm']} CONFIDENCE={payload['confidence']}")
    return 0


def load_manifest(path: Path) -> tuple[dict[str, Any], Path]:
    path = path.resolve()
    manifest = read_json(path)
    return manifest, path.parent


def manifest_paths(manifest: dict[str, Any], base: Path) -> dict[str, Path]:
    result = {
        "audio": resolved(manifest["audio"], base),
        "output": resolved(manifest["output"], base),
        "work_dir": resolved(manifest["work_dir"], base),
    }
    if manifest.get("proof_output"):
        result["proof_output"] = resolved(manifest["proof_output"], base)
    return result


def source_path(shot: dict[str, Any], base: Path) -> Path:
    return resolved(shot["source"], base)


def validate_manifest_data(
    manifest: dict[str, Any], base: Path, ffprobe: Path
) -> tuple[dict[Path, dict[str, Any]], dict[str, Any]]:
    required = ("audio", "output", "work_dir", "checkpoints")
    missing = [name for name in required if name not in manifest]
    if missing:
        raise RuntimeError(f"Manifest missing fields: {', '.join(missing)}")
    checkpoints = manifest["checkpoints"]
    if not checkpoints:
        raise RuntimeError("Manifest has no checkpoints")
    transition = float(manifest.get("transition_duration", 0.20))
    forbidden = [re.compile(pattern, re.IGNORECASE) for pattern in manifest.get("forbidden_patterns", [])]
    all_sources = sorted(
        {source_path(shot, base) for checkpoint in checkpoints for shot in checkpoint.get("shots", [])},
        key=str,
    )
    metadata = {path: probe(path, ffprobe) for path in all_sources}
    previous_end: float | None = None
    total_shots = 0
    for index, checkpoint in enumerate(checkpoints):
        for field in ("name", "start", "end", "shots"):
            if field not in checkpoint:
                raise RuntimeError(f"Checkpoint {index + 1} missing {field}")
        start = float(checkpoint["start"])
        end = float(checkpoint["end"])
        if end <= start:
            raise RuntimeError(f"Checkpoint {checkpoint['name']} has invalid range")
        if previous_end is not None and abs(start - previous_end) > 0.05:
            raise RuntimeError(f"Checkpoint {checkpoint['name']} is not contiguous with the prior checkpoint")
        previous_end = end
        expected = end - start + (transition if index < len(checkpoints) - 1 else 0.0)
        actual = sum(float(shot["duration"]) for shot in checkpoint["shots"])
        if abs(actual - expected) > 0.004:
            raise RuntimeError(
                f"{checkpoint['name']} shot total {actual:.3f}s; expected {expected:.3f}s"
            )
        for shot in checkpoint["shots"]:
            total_shots += 1
            path = source_path(shot, base)
            if not path.exists():
                raise FileNotFoundError(path)
            matched = next((pattern.pattern for pattern in forbidden if pattern.search(str(path))), None)
            if matched:
                raise RuntimeError(f"Forbidden source matched {matched}: {path}")
            media = metadata[path]
            video = first_video(media)
            duration = float(media.get("format", {}).get("duration", 0.0) or 0.0)
            if not video or duration <= 0.05:
                raise RuntimeError(f"Missing usable video stream: {path}")
            speed = float(shot.get("speed", 1.0))
            if speed <= 0.0:
                raise RuntimeError(f"Shot {shot.get('label', path.name)} has invalid speed {speed}")
            source_end = float(shot["source_start"]) + float(shot["duration"]) * speed
            if source_end > duration + 0.08:
                raise RuntimeError(
                    f"Shot {shot.get('label', path.name)} needs {source_end:.2f}s; source has {duration:.2f}s"
                )
    paths = manifest_paths(manifest, base)
    if not paths["audio"].exists():
        raise FileNotFoundError(paths["audio"])
    summary = {
        "checkpoints": len(checkpoints),
        "shots": total_shots,
        "sources": len(all_sources),
        "duration": float(checkpoints[-1]["end"]),
        "transition_duration": transition,
        "forbidden_patterns": [pattern.pattern for pattern in forbidden],
    }
    return metadata, summary


def command_validate_manifest(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve()
    manifest, base = load_manifest(manifest_path)
    ffprobe = locate_tool("ffprobe", args.ffprobe or manifest.get("ffprobe"))
    _, summary = validate_manifest_data(manifest, base, ffprobe)
    print(json.dumps(summary, indent=2))
    print("VALID=true")
    return 0


def beat_aligned_chunks(
    duration: float,
    global_start: float,
    maximum: float,
    beats: list[float],
) -> list[float]:
    if duration <= maximum:
        return [duration]
    minimum = min(1.25, maximum * 0.45)
    global_end = global_start + duration
    cuts = [global_start]
    cursor = global_start
    while global_end - cursor > maximum:
        candidates = [
            beat for beat in beats
            if cursor + minimum <= beat <= cursor + maximum + 0.08
            and global_end - beat >= minimum
        ]
        cut = candidates[-1] if candidates else min(cursor + maximum, global_end - minimum)
        if cut <= cursor + 0.05:
            break
        cuts.append(cut)
        cursor = cut
    cuts.append(global_end)
    return [cuts[index + 1] - cuts[index] for index in range(len(cuts) - 1)]


def expand_shots(
    checkpoint: dict[str, Any],
    manifest: dict[str, Any],
    base: Path,
    beats: list[float],
) -> list[dict[str, Any]]:
    enabled = bool(manifest.get("auto_microcuts", True))
    maximum = float(manifest.get("max_shot_duration", 2.8))
    zoom_pattern = [1.00, 1.075, 1.025, 1.10]
    result: list[dict[str, Any]] = []
    timeline_cursor = float(checkpoint["start"])
    for shot in checkpoint["shots"]:
        duration = float(shot["duration"])
        start = float(shot["source_start"])
        speed = float(shot.get("speed", 1.0))
        allow = enabled and shot.get("microcut", True) and duration > maximum
        chunks = beat_aligned_chunks(duration, timeline_cursor, maximum, beats) if allow else [duration]
        count = len(chunks)
        consumed = 0.0
        for index, chunk in enumerate(chunks):
            if index == count - 1:
                chunk = duration - consumed
            base_zoom = float(shot.get("zoom", 1.0))
            zoom = min(1.80, max(1.0, base_zoom * zoom_pattern[index % len(zoom_pattern)]))
            result.append({
                "label": f"{shot.get('label', Path(shot['source']).stem)} {index + 1}/{count}",
                "source": source_path(shot, base),
                "source_start": start + consumed * speed,
                "duration": chunk,
                "speed": speed,
                "zoom": zoom,
            })
            consumed += chunk
        timeline_cursor += duration
    return result


def hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def encode_args(manifest: dict[str, Any], intermediate: bool = False) -> list[str]:
    crf = int(manifest.get("crf", 18)) - (1 if intermediate else 0)
    fps = int(manifest.get("fps", 30))
    return [
        "-an", "-c:v", "libx264", "-preset", str(manifest.get("preset", "veryfast")),
        "-crf", str(max(12, crf)), "-profile:v", "high", "-level:v", "4.2",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-g", str(fps * 2),
        "-keyint_min", str(fps * 2), "-sc_threshold", "0",
        "-video_track_timescale", "90000", "-movflags", "+faststart",
    ]


def shot_filter(
    input_index: int,
    shot: dict[str, Any],
    media: dict[str, Any],
    width: int,
    height: int,
    fps: int,
) -> tuple[list[str], str]:
    video = first_video(media)
    if not video:
        raise RuntimeError(f"No video stream: {shot['source']}")
    source_width = int(video["width"])
    source_height = int(video["height"])
    zoom = float(shot.get("zoom", 1.0))
    duration = float(shot["duration"])
    speed = float(shot.get("speed", 1.0))
    source_duration = duration * speed
    zoom_width = int(math.ceil(width * zoom / 2.0) * 2)
    zoom_height = int(math.ceil(height * zoom / 2.0) * 2)
    input_args = [
        "-ss", f"{float(shot['source_start']):.3f}",
        "-t", f"{source_duration + 0.25:.3f}",
        "-i", str(shot["source"]),
    ]
    base = (
        f"[{input_index}:v]trim=duration={source_duration:.3f},"
        f"setpts=(PTS-STARTPTS)/{speed:.8f},trim=duration={duration:.3f},fps={fps},setsar=1"
    )
    grade = "eq=contrast=1.055:saturation=1.08:gamma=1.015,unsharp=5:5:0.25:5:5:0"
    if source_width / source_height >= 1.28:
        graph = (
            f"{base},scale={zoom_width}:{zoom_height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,{grade},format=yuv420p[v{input_index}]"
        )
    else:
        graph = (
            f"{base},split=2[bg{input_index}a][fg{input_index}a];"
            f"[bg{input_index}a]scale=480:270:force_original_aspect_ratio=increase,"
            f"crop=480:270,boxblur=18:2,scale={width}:{height},"
            f"eq=brightness=-0.20:saturation=0.84[bg{input_index}];"
            f"[fg{input_index}a]scale={width}:{height}:force_original_aspect_ratio=decrease[fg{input_index}];"
            f"[bg{input_index}][fg{input_index}]overlay=(W-w)/2:(H-h)/2:shortest=1,setsar=1"
        )
        if zoom > 1.001:
            graph += f",scale={zoom_width}:{zoom_height},crop={width}:{height}"
        graph += f",setsar=1,{grade},format=yuv420p[v{input_index}]"
    return input_args, graph


def scene_fingerprint(
    checkpoint: dict[str, Any], shots: list[dict[str, Any]], manifest: dict[str, Any]
) -> str:
    sources = []
    for shot in shots:
        stat = Path(shot["source"]).stat()
        sources.append({"path": str(shot["source"]), "size": stat.st_size, "mtime": stat.st_mtime_ns})
    return hash_payload({
        "checkpoint": checkpoint,
        "shots": shots,
        "sources": sources,
        "render": {
            "width": manifest.get("width", 1920),
            "height": manifest.get("height", 1080),
            "fps": manifest.get("fps", 30),
            "crf": manifest.get("crf", 18),
            "auto_microcuts": manifest.get("auto_microcuts", True),
            "max_shot_duration": manifest.get("max_shot_duration", 2.8),
        },
    })


def render_scene(
    ffmpeg: Path,
    ffprobe: Path,
    work: Path,
    index: int,
    checkpoint: dict[str, Any],
    shots: list[dict[str, Any]],
    metadata: dict[Path, dict[str, Any]],
    manifest: dict[str, Any],
    global_count: int,
) -> Path:
    fingerprint = scene_fingerprint(checkpoint, shots, manifest)
    target = work / "scenes" / f"{index + 1:02d}-{slug(checkpoint['name'])}-{fingerprint}.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    expected_duration = sum(float(shot["duration"]) for shot in shots)
    if cached_video_is_valid(target, ffprobe, expected_duration, 100_000, allow_frame_padding=True):
        print(f"REUSE={target}")
        return target
    if target.exists():
        print(f"INVALIDATE={target}")
        target.unlink()
    width = int(manifest.get("width", 1920))
    height = int(manifest.get("height", 1080))
    fps = int(manifest.get("fps", 30))
    command = [str(ffmpeg), "-hide_banner", "-y"]
    filters: list[str] = []
    for shot_index, shot in enumerate(shots):
        input_args, graph = shot_filter(shot_index, shot, metadata[Path(shot["source"])], width, height, fps)
        command.extend(input_args)
        filters.append(graph)
    joined = "".join(f"[v{i}]" for i in range(len(shots)))
    filters.append(f"{joined}concat=n={len(shots)}:v=1:a=0[scene0]")
    output_label = "scene0"
    if index == 0:
        filters.append("[scene0]fade=t=in:st=0:d=0.25[scene1]")
        output_label = "scene1"
    if index == global_count - 1:
        scene_duration = sum(float(shot["duration"]) for shot in shots)
        filters.append(f"[{output_label}]fade=t=out:st={scene_duration - 1.2:.3f}:d=1.2[scene2]")
        output_label = "scene2"
    command.extend([
        "-filter_complex", ";".join(filters), "-map", f"[{output_label}]",
        *encode_args(manifest, intermediate=True), str(target),
    ])
    run_text(command)
    require_video_duration(
        target, ffprobe, expected_duration, f"Checkpoint {checkpoint['name']}", allow_frame_padding=True
    )
    return target


def render_body(
    ffmpeg: Path,
    ffprobe: Path,
    work: Path,
    mode: str,
    index: int,
    scene: Path,
    start: float,
    end: float,
    manifest: dict[str, Any],
) -> Path:
    fingerprint = hash_payload({"scene": scene.name, "start": start, "end": end, "crf": manifest.get("crf", 18)})
    target = work / mode / f"body-{index + 1:02d}-{fingerprint}.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    expected_duration = end - start
    if cached_video_is_valid(target, ffprobe, expected_duration, 50_000):
        return target
    if target.exists():
        print(f"INVALIDATE={target}")
        target.unlink()
    run_text([
        str(ffmpeg), "-hide_banner", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
        "-i", str(scene), "-vf", f"setpts=PTS-STARTPTS,fps={int(manifest.get('fps', 30))},format=yuv420p",
        *encode_args(manifest), str(target),
    ])
    require_video_duration(target, ffprobe, expected_duration, f"Checkpoint body {index + 1}")
    return target


def render_transition(
    ffmpeg: Path,
    ffprobe: Path,
    work: Path,
    mode: str,
    index: int,
    left_scene: Path,
    right_scene: Path,
    left_duration: float,
    transition_name: str,
    duration: float,
    manifest: dict[str, Any],
) -> Path:
    fingerprint = hash_payload({
        "left": left_scene.name, "right": right_scene.name,
        "transition": transition_name, "duration": duration,
    })
    target = work / mode / f"transition-{index + 1:02d}-{fingerprint}.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    if cached_video_is_valid(target, ffprobe, duration, 20_000):
        return target
    if target.exists():
        print(f"INVALIDATE={target}")
        target.unlink()
    run_text([
        str(ffmpeg), "-hide_banner", "-y",
        "-ss", f"{left_duration - duration:.3f}", "-t", f"{duration:.3f}", "-i", str(left_scene),
        "-ss", "0", "-t", f"{duration:.3f}", "-i", str(right_scene),
        "-filter_complex",
        f"[0:v]setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];"
        f"[a][b]xfade=transition={transition_name}:duration={duration:.3f}:offset=0,"
        f"fps={int(manifest.get('fps', 30))},format=yuv420p[v]",
        "-map", "[v]", "-t", f"{duration:.3f}", *encode_args(manifest), str(target),
    ])
    require_video_duration(target, ffprobe, duration, f"Transition {index + 1}")
    return target


def mux_audio(
    ffmpeg: Path,
    silent: Path,
    audio: Path,
    output: Path,
    duration: float,
    manifest: dict[str, Any],
) -> dict[str, str]:
    target = float(manifest.get("target_lufs", -14.0))
    peak = float(manifest.get("true_peak", -1.5))
    measured = loudness_measure(ffmpeg, audio, duration, target, peak)
    loudnorm = (
        f"loudnorm=I={target}:TP={peak}:LRA=11:"
        f"measured_I={measured['input_i']}:measured_LRA={measured['input_lra']}:"
        f"measured_TP={measured['input_tp']}:measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true:print_format=summary"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    run_text([
        str(ffmpeg), "-hide_banner", "-y", "-i", str(silent), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
        "-af", f"{loudnorm},afade=t=out:st={max(0.0, duration - 1.5):.3f}:d=1.5",
        "-t", f"{duration:.6f}", "-movflags", "+faststart",
        "-metadata", f"title={manifest.get('project', 'Viral Stitch')}",
        "-metadata", "comment=Rendered by Viral Stitch with checkpoint timing and proof-first QC",
        str(output),
    ])
    return measured


def command_render(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve()
    manifest, base = load_manifest(manifest_path)
    ffmpeg = locate_tool("ffmpeg", args.ffmpeg or manifest.get("ffmpeg"))
    ffprobe = locate_tool("ffprobe", args.ffprobe or manifest.get("ffprobe"))
    metadata, validation = validate_manifest_data(manifest, base, ffprobe)
    paths = manifest_paths(manifest, base)
    checkpoints = manifest["checkpoints"]
    selected_count = min(len(checkpoints), args.proof_checkpoints or len(checkpoints))
    selected = checkpoints[:selected_count]
    mode = f"proof-{selected_count}" if selected_count < len(checkpoints) else "full"
    work = paths["work_dir"]
    work.mkdir(parents=True, exist_ok=True)
    beat_times: list[float] = []
    if manifest.get("audio_analysis"):
        analysis = read_json(resolved(manifest["audio_analysis"], base))
        beat_times = [float(value) for value in analysis.get("beats", [])]
    expanded = [expand_shots(checkpoint, manifest, base, beat_times) for checkpoint in selected]
    scenes = [
        render_scene(ffmpeg, ffprobe, work, index, checkpoint, expanded[index], metadata, manifest, len(checkpoints))
        for index, checkpoint in enumerate(selected)
    ]
    transition_duration = float(manifest.get("transition_duration", 0.20))
    sequence: list[Path] = []
    for index, checkpoint in enumerate(selected):
        scene_duration = sum(float(shot["duration"]) for shot in expanded[index])
        body_start = 0.0 if index == 0 else transition_duration
        body_end = scene_duration - (transition_duration if index < len(checkpoints) - 1 else 0.0)
        sequence.append(render_body(ffmpeg, ffprobe, work, mode, index, scenes[index], body_start, body_end, manifest))
        if index < len(selected) - 1:
            sequence.append(render_transition(
                ffmpeg, ffprobe, work, mode, index, scenes[index], scenes[index + 1], scene_duration,
                checkpoint.get("transition", "dissolve"), transition_duration, manifest,
            ))
    concat_file = work / mode / "concat.txt"
    concat_file.parent.mkdir(parents=True, exist_ok=True)
    concat_file.write_text(
        "".join(f"file '{str(path).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n" for path in sequence),
        encoding="utf-8",
    )
    silent = work / mode / "silent.mp4"
    run_text([
        str(ffmpeg), "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", "-movflags", "+faststart", str(silent),
    ])
    duration = float(selected[-1]["end"])
    silent_duration = require_video_duration(
        silent, ffprobe, duration, "Assembled silent master", allow_frame_padding=True
    )
    output = paths.get("proof_output") if selected_count < len(checkpoints) else paths["output"]
    if output is None:
        output = paths["output"].with_name(paths["output"].stem + "-proof" + paths["output"].suffix)
    measured = mux_audio(ffmpeg, silent, paths["audio"], output, duration, manifest)
    output_media = probe(output, ffprobe)
    output_video = first_video(output_media)
    output_audio = first_audio(output_media)
    output_video_duration = stream_duration(output_media, output_video)
    output_audio_duration = stream_duration(output_media, output_audio)
    tolerance = duration_tolerance(output_video)
    if (
        not output_video or not output_audio
        or abs(output_video_duration - duration) > tolerance
        or abs(output_audio_duration - duration) > tolerance
    ):
        raise RuntimeError(
            "Muxed output duration mismatch: "
            f"video={output_video_duration:.3f}s audio={output_audio_duration:.3f}s expected={duration:.3f}s"
        )
    report = {
        "status": "proof" if selected_count < len(checkpoints) else "rendered-needs-qc",
        "manifest": str(manifest_path),
        "output": str(output),
        "duration": duration,
        "checkpoints": selected_count,
        "source_shots": sum(len(checkpoint["shots"]) for checkpoint in selected),
        "rendered_microshots": sum(len(shots) for shots in expanded),
        "validation": validation,
        "audio_first_pass": measured,
        "stream_durations": {
            "silent_video": silent_duration,
            "output_video": output_video_duration,
            "output_audio": output_audio_duration,
        },
        "cache_mode": "content-hashed",
        "beat_aligned_microcuts": bool(beat_times),
    }
    report_path = work / mode / "render-report.json"
    write_json(report_path, report)
    print(f"OUTPUT={output}")
    print(f"REPORT={report_path}")
    return 0


def make_sheet(
    ffmpeg: Path,
    video: Path,
    output: Path,
    filter_graph: str,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run_text([
        str(ffmpeg), "-loglevel", "error", "-y", "-i", str(video),
        "-vf", filter_graph, "-frames:v", "1", "-pix_fmt", "yuvj420p",
        "-q:v", "2", "-update", "1", str(output),
    ])
    if not output.exists() or output.stat().st_size < 1_024:
        raise RuntimeError(f"QC sheet was not created: {output}")


def select_expression(frames: list[int]) -> str:
    return "+".join(f"eq(n,{frame})" for frame in frames)


def command_qc(args: argparse.Namespace) -> int:
    video = Path(args.video).resolve()
    manifest_path = Path(args.manifest).resolve()
    manifest, base = load_manifest(manifest_path)
    ffmpeg = locate_tool("ffmpeg", args.ffmpeg or manifest.get("ffmpeg"))
    ffprobe = locate_tool("ffprobe", args.ffprobe or manifest.get("ffprobe"))
    media = probe(video, ffprobe)
    video_stream = first_video(media)
    audio_stream = first_audio(media)
    duration = float(media.get("format", {}).get("duration", 0.0) or 0.0)
    video_duration = stream_duration(media, video_stream)
    audio_duration = stream_duration(media, audio_stream)
    expected_duration = float(manifest["checkpoints"][-1]["end"])
    visual_duration = min(value for value in (duration, video_duration) if value > 0.0)
    fps = parse_rate(video_stream.get("avg_frame_rate") if video_stream else None) or float(manifest.get("fps", 30))
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    contact = output_dir / "contact-sheet.jpg"
    make_sheet(
        ffmpeg, video, contact,
        f"fps={20.0 / visual_duration:.9f},scale=320:180,tile=5x4:nb_frames=20:padding=4:margin=4:color=black",
    )
    checkpoints = [
        checkpoint for checkpoint in manifest["checkpoints"]
        if (float(checkpoint["start"]) + float(checkpoint["end"])) / 2.0 < visual_duration - 0.05
    ]
    midpoint_frames = [int(round(((float(cp["start"]) + min(float(cp["end"]), visual_duration)) / 2.0) * fps)) for cp in checkpoints]
    midpoint = output_dir / "checkpoint-midpoints.jpg"
    midpoint_rows = max(1, math.ceil(len(midpoint_frames) / 4))
    make_sheet(
        ffmpeg, video, midpoint,
        f"select='{select_expression(midpoint_frames)}',setpts=N/FRAME_RATE/TB,scale=480:270,"
        f"tile=4x{midpoint_rows}:nb_frames={len(midpoint_frames)}:padding=4:margin=4:color=black",
    )
    boundary_times = [float(cp["end"]) for cp in checkpoints[:-1] if float(cp["end"]) < visual_duration - 0.05]
    boundary_frames = [
        int(round(max(0.0, time + delta) * fps))
        for time in boundary_times for delta in (-0.15, 0.15)
    ]
    boundaries = output_dir / "checkpoint-boundaries.jpg"
    if boundary_frames:
        boundary_rows = max(1, math.ceil(len(boundary_frames) / 6))
        make_sheet(
            ffmpeg, video, boundaries,
            f"select='{select_expression(boundary_frames)}',setpts=N/FRAME_RATE/TB,scale=320:180,"
            f"tile=6x{boundary_rows}:nb_frames={len(boundary_frames)}:padding=4:margin=4:color=black",
        )
    ending_times = [max(0.0, visual_duration - offset) for offset in (6.0, 4.0, 2.0, 1.0, 0.5, 0.12)]
    ending_frames = [int(round(time * fps)) for time in ending_times]
    ending = output_dir / "ending.jpg"
    make_sheet(
        ffmpeg, video, ending,
        f"select='{select_expression(ending_frames)}',setpts=N/FRAME_RATE/TB,scale=480:270,"
        "tile=3x2:nb_frames=6:padding=4:margin=4:color=black",
    )

    target_lufs = float(manifest.get("target_lufs", -14.0))
    target_peak = float(manifest.get("true_peak", -1.5))
    scan = run_text([
        str(ffmpeg), "-hide_banner", "-nostats", "-i", str(video),
        "-map", "0:v:0", "-map", "0:a:0",
        "-vf", "blackdetect=d=0.35:pix_th=0.10:pic_th=0.98,freezedetect=noise=-60dB:d=2",
        "-af", f"loudnorm=I={target_lufs}:TP={target_peak}:LRA=11:print_format=json",
        "-f", "null", NULL_SINK,
    ], capture=True)
    loudness_matches = re.findall(r'\{\s*"input_i".*?\}', scan, flags=re.DOTALL)
    loudness = json.loads(loudness_matches[-1]) if loudness_matches else {}
    black_events = [line.strip() for line in scan.splitlines() if "black_start:" in line]
    freeze_events = [line.strip() for line in scan.splitlines() if "freeze_start:" in line or "freeze_duration:" in line]
    tolerance = duration_tolerance(video_stream)
    duration_pass = bool(
        video_duration > 0.0 and audio_duration > 0.0
        and abs(duration - expected_duration) <= tolerance
        and abs(video_duration - expected_duration) <= tolerance
        and abs(audio_duration - expected_duration) <= tolerance
    )
    stream_pass = bool(
        video_stream and audio_stream
        and video_stream.get("codec_name") == "h264"
        and video_stream.get("pix_fmt") == "yuv420p"
        and audio_stream.get("codec_name") == "aac"
        and int(audio_stream.get("sample_rate", 0)) == 48000
        and int(audio_stream.get("channels", 0)) == 2
    )
    loudness_pass = bool(
        loudness
        and abs(float(loudness["input_i"]) - target_lufs) <= 0.6
        and float(loudness["input_tp"]) <= target_peak + 0.15
    )
    report = {
        "status": "technical-pass-needs-visual-review" if stream_pass and duration_pass and loudness_pass and not black_events and not freeze_events else "needs-revision",
        "video": str(video),
        "manifest": str(manifest_path),
        "duration": duration,
        "video_duration": video_duration,
        "audio_duration": audio_duration,
        "expected_duration": expected_duration,
        "streams": {"video": video_stream, "audio": audio_stream},
        "loudness": loudness,
        "black_events": black_events,
        "freeze_events": freeze_events,
        "stream_pass": stream_pass,
        "duration_pass": duration_pass,
        "loudness_pass": loudness_pass,
        "visual_review_required": True,
        "artifacts": {
            "contact_sheet": str(contact),
            "checkpoint_midpoints": str(midpoint),
            "checkpoint_boundaries": str(boundaries) if boundary_frames else None,
            "ending": str(ending),
        },
    }
    report_path = output_dir / "qc-report.json"
    write_json(report_path, report)
    print(f"QC_REPORT={report_path}")
    print(f"STATUS={report['status']}")
    return 0 if report["status"] != "needs-revision" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic checkpoint-driven music video assembly")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser("inventory")
    inventory.add_argument("--roots", nargs="+", required=True)
    inventory.add_argument("--output", required=True)
    inventory.add_argument("--exclude", action="append", default=[])
    inventory.add_argument("--since-minutes", type=float)
    inventory.add_argument("--ffprobe")
    inventory.set_defaults(func=command_inventory)

    analyze = subparsers.add_parser("analyze-audio")
    analyze.add_argument("--audio", required=True)
    analyze.add_argument("--output", required=True)
    analyze.add_argument("--ffmpeg")
    analyze.set_defaults(func=command_analyze_audio)

    validate = subparsers.add_parser("validate-manifest")
    validate.add_argument("--manifest", required=True)
    validate.add_argument("--ffprobe")
    validate.set_defaults(func=command_validate_manifest)

    render = subparsers.add_parser("render")
    render.add_argument("--manifest", required=True)
    render.add_argument("--proof-checkpoints", type=int)
    render.add_argument("--ffmpeg")
    render.add_argument("--ffprobe")
    render.set_defaults(func=command_render)

    qc = subparsers.add_parser("qc")
    qc.add_argument("--video", required=True)
    qc.add_argument("--manifest", required=True)
    qc.add_argument("--output-dir", required=True)
    qc.add_argument("--ffmpeg")
    qc.add_argument("--ffprobe")
    qc.set_defaults(func=command_qc)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"COMMAND_FAILED={exc.returncode}", file=sys.stderr)
        raise
