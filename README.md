# Viral Stitch Godmode

Production-grade, beat-synced music-video assembly powered by Viral Stitch's proprietary editorial layer on GPT-5.6, deterministic FFmpeg rendering, proof-first QC, semantic audits, and visual-only patching.

Version 1.3.0 adds universal catalog intelligence and bounded 100-agent consensus. The original v1.2.0 release remains permanently available with its original behavior.

## Any video catalog + 100-agent consensus

Mine mixed folders of generator exports, camera footage, archives, and downloads—not only Sora. Supported containers include MP4, MOV, M4V, WebM, MKV, AVI, MTS, M2TS, TS, MPG, MPEG, WMV, FLV, OGV, 3GP, and VOB. Inventory reports now expose sampled fingerprints, duplicate groups, format and orientation counts, duration, and bytes.

```powershell
viral-stitch inventory --roots "D:\videos" "D:\camera" "D:\downloads" --output catalog.json
viral-stitch swarm-plan --catalog catalog.json --brief "literal lyric matches, cinematic landscape, no dogs" --agents 100 --output swarm-plan.json
```

The swarm is 100 reproducible local editorial voters spanning relevance, literal lyrics, beat energy, quality, diversity, format fit, duration, uniqueness, continuity, and risk. Add `--synthesize openai --model gpt-5.6` for one final model synthesis after consensus.

## Why it is different

- The AI never renders media or silently changes timing. It proposes an editorial plan; deterministic validators and FFmpeg execute it.
- `patch-visuals` replaces picture ranges while stream-copying the canonical AAC audio unchanged.
- Beat-aligned microcuts, content-hashed caches, forbidden-source enforcement, loudness measurement, contact sheets, boundary sheets, ending checks, black/freeze scans, and stream-duration gates are built in.
- GPT-5.6 supplies frontier reasoning, but Viral Stitch owns the editorial policy, schemas, training examples, timing logic, validators, renderer, and QC. The deterministic fallback works fully offline.

## Install

```powershell
py -m pip install -e .
viral-stitch doctor
```

## Install as a Codex skill

Download `viral-stitch-godmode-skill-1.3.0.zip` from the GitHub release, extract its `viral-stitch-godmode` folder into `~/.codex/skills`, and start a new Codex task. Invoke it with `$viral-stitch-godmode`.

The skill is a thin, validated workflow layer over this package. Both delivery modes use the same engine, GPT-5.6 runtime, validators, renderer, and QC contract.

FFmpeg and FFprobe must be on `PATH`, supplied by CLI flags, or installed at the default Windows location used by the engine.

## Viral Stitch model on GPT-5.6

```powershell
$env:OPENAI_API_KEY = "your-key"
viral-stitch plan --provider openai --model gpt-5.6 `
  --catalog catalog.json --audio-analysis audio-analysis.json `
  --brief creative-brief.md --output editorial-plan.json
```

Use `--provider deterministic` for offline planning. Anthropic remains an optional compatibility connector, not the product's brain.

## Proven deterministic workflow

```powershell
viral-stitch inventory --roots "D:\Downloads" "D:\sora" --output catalog.json --exclude dog --exclude bazooka
viral-stitch analyze-audio --audio song.mp3 --output audio-analysis.json
viral-stitch audit-manifest --manifest project.json --output audit.json
viral-stitch validate-manifest --manifest project.json
viral-stitch render --manifest project.json --proof-checkpoints 3
viral-stitch qc --video proof.mp4 --manifest project.json --output-dir qc-proof
viral-stitch render --manifest project.json
viral-stitch qc --video final.mp4 --manifest project.json --output-dir qc-final
```

## Visual-only repair without touching audio

```powershell
viral-stitch patch-visuals --master approved.mp4 --start 25 --end 28 `
  --replacement clean-shot.mp4 --replacement-start 5.8 --output corrected.mp4
```

The replacement is extended by the transition handles, dissolved at both boundaries, and the master audio stream is copied unchanged.

## Security

API keys are read only from environment variables. Media, prompts, manifests, and credentials are excluded from Git by default. GPT-5.6 receives the supplied brief, compact catalog metadata, and audio-analysis JSON—not the media files themselves.
