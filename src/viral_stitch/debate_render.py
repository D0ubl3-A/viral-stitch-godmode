from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _tool(name: str, explicit: str | None = None) -> str:
    value = explicit or shutil.which(name)
    if not value:
        raise FileNotFoundError(f"{name} was not found on PATH")
    return value


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _join_words(words: list[str]) -> str:
    text = " ".join(words)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def _clip_segments(words: list[dict[str, Any]], start: float, end: float, max_words: int = 8) -> list[dict[str, Any]]:
    selected = [word for word in words if float(word["end"]) >= start and float(word["start"]) <= end]
    segments: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for word in selected:
        current.append(word)
        duration = float(current[-1]["end"]) - float(current[0]["start"])
        if len(current) >= max_words or duration >= 2.8 or re.search(r"[.!?]$", str(word["text"])):
            segments.append({
                "start": max(0.0, float(current[0]["start"]) - start),
                "end": min(end - start, float(current[-1]["end"]) - start),
                "text": _join_words([str(item["text"]) for item in current]),
            })
            current = []
    if current:
        segments.append({
            "start": max(0.0, float(current[0]["start"]) - start),
            "end": min(end - start, float(current[-1]["end"]) - start),
            "text": _join_words([str(item["text"]) for item in current]),
        })
    return segments


def _write_srt(path: Path, segments: list[dict[str, Any]]) -> None:
    blocks = []
    for index, segment in enumerate(segments, 1):
        blocks.append(
            f"{index}\n{_srt_time(float(segment['start']))} --> {_srt_time(float(segment['end']))}\n{segment['text']}\n"
        )
    path.write_text("\n".join(blocks), encoding="utf-8")


def _ffmpeg_escape(path: Path) -> str:
    value = str(path.resolve()).replace("\\", "/")
    value = value.replace(":", "\\:").replace("'", "\\'")
    return value


def _short_filter(captions: Path) -> str:
    subtitle = _ffmpeg_escape(captions)
    return (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        f"subtitles='{subtitle}':force_style='FontName=Arial,FontSize=18,Bold=1,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,"
        "Shadow=1,Alignment=2,MarginV=180'"
    )


def _long_filter(captions: Path) -> str:
    subtitle = _ffmpeg_escape(captions)
    return (
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
        f"subtitles='{subtitle}':force_style='FontName=Arial,FontSize=20,Bold=1,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,"
        "Shadow=1,Alignment=2,MarginV=70'"
    )


def render_short(
    ffmpeg: str,
    source: Path,
    words: list[dict[str, Any]],
    clip: dict[str, Any],
    output_dir: Path,
    crf: int,
    preset: str,
) -> Path:
    clip_id = str(clip["id"])
    start = float(clip["start"])
    end = float(clip["end"])
    caption_path = output_dir / f"{clip_id}.srt"
    output_path = output_dir / f"{clip_id}.mp4"
    _write_srt(caption_path, _clip_segments(words, start, end))
    _run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(source),
        "-vf", _short_filter(caption_path),
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-movflags", "+faststart", "-pix_fmt", "yuv420p", str(output_path),
    ])
    return output_path


def render_long(
    ffmpeg: str,
    source: Path,
    words: list[dict[str, Any]],
    long_plan: dict[str, Any],
    output_dir: Path,
    crf: int,
    preset: str,
) -> Path:
    chapters = list(long_plan.get("chapters", []))
    if not chapters:
        raise RuntimeError("Long plan contains no chapters")
    start = float(chapters[0]["start"])
    end = float(chapters[-1]["end"])
    caption_path = output_dir / "long-form.srt"
    output_path = output_dir / "long-form.mp4"
    _write_srt(caption_path, _clip_segments(words, start, end, max_words=11))
    _run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(source),
        "-vf", _long_filter(caption_path),
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-movflags", "+faststart", "-pix_fmt", "yuv420p", str(output_path),
    ])
    return output_path


def command_render(args: argparse.Namespace) -> int:
    source = Path(args.input).expanduser().resolve()
    plan_dir = Path(args.plan_dir).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    ffmpeg = _tool("ffmpeg", args.ffmpeg)

    transcript = _read(plan_dir / "transcript.json")
    run = _read(plan_dir / "debate-run.json")
    if run.get("status") != "ready_for_render" and not args.allow_unreviewed:
        raise RuntimeError(
            "Caption review is not complete. Correct flagged transcript segments and mark debate-run.json "
            "as ready_for_render, or pass --allow-unreviewed only for a private proof render."
        )
    words = list(transcript.get("words", []))
    shorts = _read(plan_dir / "viral-shorts-plan.json")
    long_plan = _read(plan_dir / "viral-long-plan.json")

    rendered_shorts = []
    shorts_dir = output / "shorts"
    shorts_dir.mkdir(parents=True, exist_ok=True)
    for clip in shorts:
        rendered_shorts.append(str(render_short(ffmpeg, source, words, clip, shorts_dir, args.crf, args.preset)))

    rendered_long = None
    if not args.shorts_only:
        long_dir = output / "long"
        long_dir.mkdir(parents=True, exist_ok=True)
        rendered_long = str(render_long(ffmpeg, source, words, long_plan, long_dir, args.crf, args.preset))

    payload = {
        "source": str(source),
        "plan_dir": str(plan_dir),
        "shorts": rendered_shorts,
        "long_form": rendered_long,
        "caption_status": run.get("status"),
        "proof_only": bool(args.allow_unreviewed and run.get("status") != "ready_for_render"),
    }
    (output / "render-results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="viral-stitch debate-render")
    root.add_argument("--input", required=True)
    root.add_argument("--plan-dir", required=True)
    root.add_argument("--output", required=True)
    root.add_argument("--shorts-only", action="store_true")
    root.add_argument("--allow-unreviewed", action="store_true")
    root.add_argument("--crf", type=int, default=19)
    root.add_argument("--preset", default="medium")
    root.add_argument("--ffmpeg")
    root.set_defaults(func=command_render)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.func(args))
