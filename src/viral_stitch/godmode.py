from __future__ import annotations

import argparse
import json
import os
import re
import random
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .engine import locate_tool, read_json, write_json


DEFAULT_MODEL = "gpt-5.6"
DEFAULT_FALLBACK = "claude-opus-4-8"


def _json_from_text(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def _anthropic(prompt: str, model: str, fallback: str | None, max_tokens: int) -> dict[str, Any]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is required for --provider anthropic")

    def request(chosen: str) -> dict[str, Any]:
        payload = json.dumps({
            "model": chosen,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            method="POST",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Anthropic HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc

    result = request(model)
    used = model
    if result.get("stop_reason") == "refusal" and fallback:
        result, used = request(fallback), fallback
    blocks = result.get("content", [])
    text = "\n".join(block.get("text", "") for block in blocks if block.get("type") == "text")
    if not text:
        raise RuntimeError(f"Anthropic returned no text (stop_reason={result.get('stop_reason')})")
    return {"provider": "anthropic", "requested_model": model, "used_model": used, "plan": _json_from_text(text)}


def _openai(prompt: str, model: str, max_tokens: int) -> dict[str, Any]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for --provider openai; use --provider deterministic for local-only planning")
    payload = json.dumps({
        "model": model,
        "instructions": "You are the reasoning runtime for Viral Stitch's proprietary editorial model. Return valid JSON only. Never invent media paths or alter canonical audio timing.",
        "input": prompt,
        "max_output_tokens": max_tokens,
        "reasoning": {"effort": "high"},
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=payload,
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
    if result.get("status") != "completed":
        details = result.get("incomplete_details") or result.get("error") or "unknown reason"
        raise RuntimeError(f"OpenAI response did not complete: {details}. Increase --max-tokens or reduce catalog size.")
    texts = []
    for item in result.get("output", []):
        for block in item.get("content", []):
            if block.get("type") == "output_text":
                texts.append(block.get("text", ""))
    if not texts and result.get("output_text"):
        texts.append(result["output_text"])
    if not texts:
        raise RuntimeError(f"OpenAI returned no output text (status={result.get('status')})")
    return {"provider": "openai", "requested_model": model, "used_model": result.get("model", model), "response_id": result.get("id"), "plan": _json_from_text("\n".join(texts))}


def _deterministic_plan(catalog: dict[str, Any], brief: str) -> dict[str, Any]:
    words = set(re.findall(r"[a-z0-9]+", brief.lower()))
    scored = []
    for item in catalog.get("items", []):
        if not item.get("valid"):
            continue
        name_words = set(re.findall(r"[a-z0-9]+", item.get("name", "").lower()))
        score = len(words & name_words) * 5 + (2 if item.get("orientation") == "landscape" else 0)
        scored.append({"score": score, **item})
    scored.sort(key=lambda row: (-row["score"], row.get("name", "")))
    return {
        "provider": "deterministic",
        "requested_model": None,
        "used_model": None,
        "plan": {
            "summary": "Viral Stitch deterministic relevance ranking; use swarm-plan for multi-role scene consensus.",
            "recommended_assets": scored[:20],
            "rules": ["preserve canonical audio", "no repeated source windows", "proof before full render", "literal lyric actions require protected shots"],
        },
    }


SWARM_ROLES = (
    "semantic_relevance", "lyric_literal", "beat_energy", "technical_quality",
    "visual_diversity", "format_fit", "duration_fit", "uniqueness",
    "continuity", "editorial_risk",
)


def swarm_consensus(catalog: dict[str, Any], brief: str, agents: int = 100) -> dict[str, Any]:
    if agents < 1 or agents > 10_000:
        raise ValueError("agents must be between 1 and 10000")
    words = set(re.findall(r"[a-z0-9]+", brief.lower()))
    wants_portrait = bool(re.search(r"\b(vertical|portrait|shorts?|9:16)\b", brief, re.I))
    duplicate_paths = {path for group in catalog.get("duplicate_groups", []) for path in group[1:]}
    rows = [row for row in catalog.get("items", []) if row.get("valid")]
    aggregates: dict[str, dict[str, Any]] = {}
    role_counts = {role: 0 for role in SWARM_ROLES}
    for agent_id in range(agents):
        role = SWARM_ROLES[agent_id % len(SWARM_ROLES)]
        role_counts[role] += 1
        rng = random.Random(f"viral-stitch:{agent_id}:{brief}")
        ranked = []
        for row in rows:
            path = str(row.get("path", ""))
            name_words = set(re.findall(r"[a-z0-9]+", str(row.get("name", "")).lower()))
            relevance = len(words & name_words) / max(1, len(words))
            pixels = int(row.get("width", 0)) * int(row.get("height", 0))
            quality = min(1.0, pixels / 2_073_600) if pixels else 0.0
            duration = float(row.get("duration", 0) or 0)
            duration_fit = 1.0 if 1.0 <= duration <= 60.0 else 0.25
            orientation_fit = 1.0 if (row.get("orientation") == "portrait") == wants_portrait else 0.35
            unique = 0.0 if path in duplicate_paths else 1.0
            factors = [relevance, relevance, duration_fit, quality, unique, orientation_fit, duration_fit, unique, quality, unique]
            focus = factors[agent_id % len(factors)]
            score = 0.46 * focus + 0.22 * relevance + 0.12 * quality + 0.08 * duration_fit + 0.08 * orientation_fit + 0.04 * unique
            score += rng.uniform(-0.025, 0.025)
            ranked.append((score, path, row))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        for rank, (score, path, row) in enumerate(ranked[: min(12, len(ranked))]):
            record = aggregates.setdefault(path, {"item": row, "votes": 0, "score_total": 0.0, "rank_points": 0})
            record["votes"] += 1
            record["score_total"] += score
            record["rank_points"] += 12 - rank
    consensus = []
    for record in aggregates.values():
        consensus.append({
            **record["item"],
            "swarm_votes": record["votes"],
            "vote_share": round(record["votes"] / agents, 4),
            "consensus_score": round(record["score_total"] / record["votes"], 6),
            "rank_points": record["rank_points"],
        })
    consensus.sort(key=lambda row: (-row["swarm_votes"], -row["rank_points"], -row["consensus_score"], row.get("path", "")))
    return {
        "requested_agents": agents,
        "completed_agents": agents,
        "role_distribution": role_counts,
        "catalog_items_considered": len(rows),
        "duplicate_copies_penalized": len(duplicate_paths),
        "consensus": consensus,
    }


def command_swarm_plan(args: argparse.Namespace) -> int:
    catalog = read_json(Path(args.catalog))
    brief = Path(args.brief).read_text(encoding="utf-8") if Path(args.brief).exists() else args.brief
    swarm = swarm_consensus(catalog, brief, args.agents)
    payload: dict[str, Any] = {"schema_version": 1, "mode": "bounded-local-consensus", "workers": args.workers, "swarm": swarm}
    if args.synthesize == "openai":
        compact = [{k: row.get(k) for k in ("path", "name", "duration", "orientation", "swarm_votes", "consensus_score")} for row in swarm["consensus"][:30]]
        prompt = "Return JSON only. Convert this Viral Stitch swarm consensus into a concise editorial selection plan. Preserve exact paths and canonical audio. BRIEF:\n" + brief + "\nCONSENSUS:\n" + json.dumps(compact)
        payload["synthesis"] = _openai(prompt, args.model, args.max_tokens)
    write_json(Path(args.output), payload)
    print(f"SWARM_PLAN={Path(args.output).resolve()}")
    print(f"AGENTS={swarm['completed_agents']} ITEMS={swarm['catalog_items_considered']}")
    return 0


def command_plan(args: argparse.Namespace) -> int:
    catalog = read_json(Path(args.catalog))
    analysis = read_json(Path(args.audio_analysis)) if args.audio_analysis else {}
    brief = Path(args.brief).read_text(encoding="utf-8") if Path(args.brief).exists() else args.brief
    if args.provider in {"openai", "anthropic"}:
        compact = [{k: row.get(k) for k in ("path", "name", "duration", "width", "height", "orientation")} for row in catalog.get("items", []) if row.get("valid")]
        prompt = (
            "You are the editorial brain for a deterministic music-video system. Return JSON only. "
            "Do not invent files or timestamps. Build a ranked editorial plan with keys summary, exclusions, protected_moments, "
            "checkpoints, risks, and qc_requirements. Each checkpoint must cite exact catalog paths. Avoid repeated source windows; "
            "prefer literal lyric matches; preserve the canonical audio.\n\nBRIEF:\n" + brief +
            "\n\nAUDIO ANALYSIS:\n" + json.dumps(analysis) + "\n\nCATALOG:\n" + json.dumps(compact)
        )
        result = _openai(prompt, args.model, args.max_tokens) if args.provider == "openai" else _anthropic(prompt, args.model, args.fallback_model, args.max_tokens)
    else:
        result = _deterministic_plan(catalog, brief)
    result["schema_version"] = 1
    write_json(Path(args.output), result)
    print(f"PLAN={Path(args.output).resolve()}")
    print(f"MODEL={result.get('used_model') or 'deterministic'}")
    return 0


def audit_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    issues, windows, source_seconds = [], {}, {}
    forbidden = [re.compile(x, re.I) for x in manifest.get("forbidden_patterns", [])]
    portrait_seconds = total_seconds = 0.0
    for checkpoint in manifest.get("checkpoints", []):
        for shot in checkpoint.get("shots", []):
            path, label = str(shot.get("source", "")), str(shot.get("label", ""))
            duration, start = float(shot.get("duration", 0)), float(shot.get("source_start", 0))
            speed = float(shot.get("speed", 1))
            total_seconds += duration
            source_seconds[path] = source_seconds.get(path, 0.0) + duration
            if any(pattern.search(path + " " + label) for pattern in forbidden):
                issues.append({"severity": "error", "type": "forbidden", "shot": label, "source": path})
            interval = (start, start + duration * speed, label)
            for previous in windows.setdefault(path, []):
                overlap = max(0.0, min(interval[1], previous[1]) - max(interval[0], previous[0]))
                if overlap > 0.35:
                    issues.append({"severity": "warning", "type": "repeated_source_window", "source": path, "shots": [previous[2], label], "overlap_seconds": round(overlap, 3)})
            windows[path].append(interval)
            if shot.get("orientation") == "portrait":
                portrait_seconds += duration
    for path, seconds in source_seconds.items():
        if total_seconds and seconds / total_seconds > 0.12:
            issues.append({"severity": "warning", "type": "source_overuse", "source": path, "timeline_share": round(seconds / total_seconds, 3)})
    return {"status": "pass" if not any(x["severity"] == "error" for x in issues) else "fail", "issues": issues, "metrics": {"timeline_seconds_scheduled": round(total_seconds, 3), "unique_sources": len(source_seconds), "portrait_share": round(portrait_seconds / total_seconds, 3) if total_seconds else 0}}


def command_audit(args: argparse.Namespace) -> int:
    report = audit_manifest(read_json(Path(args.manifest)))
    write_json(Path(args.output), report)
    print(f"AUDIT={Path(args.output).resolve()}")
    print(f"STATUS={report['status']} ISSUES={len(report['issues'])}")
    return 0 if report["status"] == "pass" else 2


def command_patch(args: argparse.Namespace) -> int:
    ffmpeg = locate_tool("ffmpeg", args.ffmpeg)
    ffprobe = locate_tool("ffprobe", args.ffprobe)
    duration = args.end - args.start
    transition = args.transition
    replacement_duration = duration + 2 * transition
    filter_graph = (
        f"[0:v]trim=start=0:end={args.start},setpts=PTS-STARTPTS,fps={args.fps},setsar=1[pre];"
        f"[1:v]trim=start={args.replacement_start}:duration={replacement_duration},setpts=PTS-STARTPTS,fps={args.fps},split=2[bg][fg];"
        f"[bg]scale={args.width}:{args.height}:force_original_aspect_ratio=increase,crop={args.width}:{args.height},gblur=sigma=35,eq=brightness=-0.08[bg2];"
        f"[fg]scale=-2:{args.height}[fg2];[bg2][fg2]overlay=(W-w)/2:0,format=yuv420p,setsar=1[rep];"
        f"[0:v]trim=start={args.end},setpts=PTS-STARTPTS,fps={args.fps},setsar=1[post];"
        f"[pre][rep]xfade=transition=dissolve:duration={transition}:offset={args.start-transition}[a];"
        f"[a][post]xfade=transition=dissolve:duration={transition}:offset={args.end}[v]"
    )
    command = [str(ffmpeg), "-hide_banner", "-y", "-i", args.master, "-i", args.replacement, "-filter_complex", filter_graph, "-map", "[v]", "-map", "0:a:0", "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf), "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(args.fps), "-c:a", "copy", "-movflags", "+faststart", args.output]
    subprocess.run(command, check=True)
    probe = subprocess.run([str(ffprobe), "-v", "error", "-show_entries", "format=duration,size", "-of", "json", args.output], check=True, text=True, capture_output=True)
    print(probe.stdout)
    print(f"OUTPUT={Path(args.output).resolve()}")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    status = {"python": shutil.which("python") or shutil.which("py"), "ffmpeg": str(locate_tool("ffmpeg", args.ffmpeg)), "ffprobe": str(locate_tool("ffprobe", args.ffprobe)), "openai_key_configured": bool(os.environ.get("OPENAI_API_KEY")), "anthropic_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY")), "default_reasoning_model": DEFAULT_MODEL, "proprietary_editorial_layer": "viral-stitch-godmode", "universal_catalog_formats": 16, "default_swarm_agents": 100, "classic_commands_preserved": True}
    print(json.dumps(status, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="viral-stitch")
    subs = root.add_subparsers(dest="command", required=True)
    doctor = subs.add_parser("doctor"); doctor.add_argument("--ffmpeg"); doctor.add_argument("--ffprobe"); doctor.set_defaults(func=command_doctor)
    plan = subs.add_parser("plan"); plan.add_argument("--catalog", required=True); plan.add_argument("--audio-analysis"); plan.add_argument("--brief", required=True); plan.add_argument("--output", required=True); plan.add_argument("--provider", choices=("openai", "deterministic", "anthropic"), default="openai"); plan.add_argument("--model", default=DEFAULT_MODEL); plan.add_argument("--fallback-model", default=DEFAULT_FALLBACK); plan.add_argument("--max-tokens", type=int, default=8192); plan.set_defaults(func=command_plan)
    swarm = subs.add_parser("swarm-plan"); swarm.add_argument("--catalog", required=True); swarm.add_argument("--brief", required=True); swarm.add_argument("--output", required=True); swarm.add_argument("--agents", type=int, default=100); swarm.add_argument("--workers", type=int, default=4); swarm.add_argument("--synthesize", choices=("deterministic", "openai"), default="deterministic"); swarm.add_argument("--model", default=DEFAULT_MODEL); swarm.add_argument("--max-tokens", type=int, default=4096); swarm.set_defaults(func=command_swarm_plan)
    audit = subs.add_parser("audit-manifest"); audit.add_argument("--manifest", required=True); audit.add_argument("--output", required=True); audit.set_defaults(func=command_audit)
    patch = subs.add_parser("patch-visuals"); patch.add_argument("--master", required=True); patch.add_argument("--start", type=float, required=True); patch.add_argument("--end", type=float, required=True); patch.add_argument("--replacement", required=True); patch.add_argument("--replacement-start", type=float, default=0); patch.add_argument("--output", required=True); patch.add_argument("--transition", type=float, default=.2); patch.add_argument("--width", type=int, default=1920); patch.add_argument("--height", type=int, default=1080); patch.add_argument("--fps", type=int, default=30); patch.add_argument("--crf", type=int, default=19); patch.add_argument("--preset", default="veryfast"); patch.add_argument("--ffmpeg"); patch.add_argument("--ffprobe"); patch.set_defaults(func=command_patch)
    return root


def extension_main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    return int(args.func(args))
