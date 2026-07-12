---
name: viral-stitch-godmode
description: Build, repair, plan, render, and QC beat-synced music videos with Viral Stitch's GPT-5.6 editorial system and deterministic FFmpeg engine. Use for music-video assembly, Sora/Veo catalog mining, lyric or beat synchronization, visual-only replacements that preserve audio, forbidden-scene removal, proof renders, final MP4 delivery, or semantic manifest audits.
---

# Viral Stitch Godmode

Use the packaged engine through `scripts/run_viral_stitch.py`. Keep GPT-5.6 as the reasoning runtime and Viral Stitch as the controlling editorial model.

## Required sequence

1. Run `doctor` and resolve FFmpeg, FFprobe, Python, or package failures.
2. Lock canonical audio, platform, aspect ratio, media roots, exclusions, literal lyric actions, and output version.
3. Run `inventory`; reject corrupt, forbidden, irrelevant, and misleading source windows.
4. Run `analyze-audio`; preserve its beat grid and canonical audio duration.
5. Run `plan --provider openai --model gpt-5.6`. Use `--provider deterministic` only when offline or explicitly requested.
6. Convert the approved plan into a manifest and run `audit-manifest` plus `validate-manifest`.
7. Render a representative proof. Run QC and inspect contact, boundary, exact-action, and ending frames.
8. Fix root causes. Render the full master only after the proof passes.
9. Run final QC and report exact paths, streams, loudness, exclusions, visual evidence, and remaining caveats.

## Hard rules

- Treat audio as immutable unless the user explicitly requests an audio edit.
- Use `patch-visuals` for picture-only replacements; it stream-copies the master AAC audio.
- Never overwrite an approved version.
- Never trust labels alone. Inspect source windows and rendered frames.
- Protect literal lyric actions with word timestamps and unmistakable visual framing.
- Reject repeated source windows, irrelevant filler, accidental text, dog/agent/bazooka-style exclusions, and portrait footage with untreated sidebars.
- Keep AI output advisory. Validators, timing math, rendering, and QC decide what ships.

Read [references/workflow.md](references/workflow.md) for command templates and installation recovery.

