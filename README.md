# Viral Stitch Godmode

Production-grade, beat-synced music-video assembly with deterministic FFmpeg rendering, proof-first QC, semantic manifest audits, visual-only patching, and optional Claude Fable 5 editorial planning.

## Why it is different

- The AI never renders media or silently changes timing. It proposes an editorial plan; deterministic validators and FFmpeg execute it.
- `patch-visuals` replaces picture ranges while stream-copying the canonical AAC audio unchanged.
- Beat-aligned microcuts, content-hashed caches, forbidden-source enforcement, loudness measurement, contact sheets, boundary sheets, ending checks, black/freeze scans, and stream-duration gates are built in.
- Anthropic is optional. The full inventory, audio analysis, renderer, QC, audits, and deterministic planner work locally.

## Install

```powershell
py -m pip install -e .
viral-stitch doctor
```

FFmpeg and FFprobe must be on `PATH`, supplied by CLI flags, or installed at the default Windows location used by the engine.

## Claude Fable 5 planning

```powershell
$env:ANTHROPIC_API_KEY = "your-key"
viral-stitch plan --provider anthropic --model claude-fable-5 `
  --catalog catalog.json --audio-analysis audio-analysis.json `
  --brief creative-brief.md --output editorial-plan.json
```

If Fable 5 returns a classifier refusal, the client retries with `claude-opus-4-8` by default. API calls are never required to render or QC.

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

API keys are read only from environment variables. Media, prompts, manifests, and credentials are excluded from Git by default. Fable 5 requests send the supplied brief, compact catalog metadata, and audio-analysis JSON—not the media files themselves.

