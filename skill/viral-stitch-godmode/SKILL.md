---
name: viral-stitch-godmode
description: Build, repair, plan, render, caption, promote, and QC music videos or long Bigo panel debates with Viral Stitch's GPT-5.6 editorial system, Groq word timestamps, deterministic FFmpeg execution, viral shorts, long-form recuts, and image-generated thumbnails.
---

# Viral Stitch Godmode

Use the packaged engine through `scripts/run_viral_stitch.py`. Keep GPT-5.6 as the reasoning runtime, Viral Stitch as the controlling editorial model, Groq as the debate transcription engine, and deterministic validators as the final authority.

## Choose the workflow

- Use the classic music-video sequence for songs, generated footage, lyric synchronization, beat editing, or visual-only repair.
- Use **Bigo Debate God Mode** for a 1-2 hour Bigo Live panel recording that must become multiple viral Shorts plus a promoted long-form edit.

## Classic required sequence

1. Run `doctor` and resolve FFmpeg, FFprobe, Python, or package failures.
2. Lock canonical audio, platform, aspect ratio, media roots, exclusions, literal lyric actions, and output version.
3. Run `inventory`; reject corrupt, forbidden, irrelevant, and misleading source windows.
4. Run `analyze-audio`; preserve its beat grid and canonical audio duration.
5. Run `plan --provider openai --model gpt-5.6`. Use `--provider deterministic` only when offline or explicitly requested.
6. Convert the approved plan into a manifest and run `audit-manifest` plus `validate-manifest`.
7. Render a representative proof. Run QC and inspect contact, boundary, exact-action, and ending frames.
8. Fix root causes. Render the full master only after the proof passes.
9. Run final QC and report exact paths, streams, loudness, exclusions, visual evidence, and remaining caveats.

## Bigo Debate God Mode sequence

1. Obtain the original Bigo panel recording, exact panelist names, show/channel branding, and a spelling glossary for names, slang, organizations, religious terms, political terms, and recurring phrases.
2. Run `doctor`; require FFmpeg and `GROQ_API_KEY`.
3. Run the debate command. It extracts mono 16 kHz WAV chunks, sends each chunk to Groq with zero temperature, requests word timestamps, applies approved spellings, removes chunk-boundary duplicates, and produces `transcript.json` plus `captions-review.srt`.
4. Review every segment below the configured confidence threshold against source audio. The workflow must remain blocked until flagged captions are corrected. Never promise literal zero-error transcription without source-audio verification.
5. Lock the approved transcript. All titles, descriptions, thumbnails, quote cards, hooks, and captions must derive from the locked words. Never manufacture an admission, insult, fact, quote, or winner/loser claim.
6. Review `viral-shorts-plan.json`. Prefer complete exchanges with a hook in the first 1-4 seconds, understandable context, visible conflict, a payoff, and no misleading cut.
7. Review `viral-long-plan.json`. Preserve enough context to represent each speaker fairly; include transcript-derived chapters and clearly identify the upload as an edited Bigo panel debate.
8. Call the installed **image-generation skill** through `image_gen` for every selected Short and long-form thumbnail. Use supplied panelist images for accurate likeness. Do not generate fake quote text or depict events not present in the clip.
9. Render deterministic 9:16 Shorts and a 16:9 long-form master with FFmpeg. Keep captions tied to approved word timestamps, normalize loudness, protect faces from caption overlap, and never stretch speech.
10. Run final QC: spelling, speaker/name accuracy, caption timing, source continuity, no deceptive edits, no clipped words, no duplicate clips, safe margins, thumbnail accuracy, title accuracy, chapter accuracy, audio sync, and platform exports.

### Command

```powershell
py scripts/run_viral_stitch.py debate `
  --input "D:\Bigo\panel-debate.mp4" `
  --output "D:\Bigo\viral-stitch-output" `
  --panelist "Prez Craig" `
  --panelist "Panelist Two" `
  --glossary "D:\Bigo\approved-spellings.json" `
  --short-count 20 `
  --short-min 25 `
  --short-max 75 `
  --long-minutes 35
```

Expected output:

- `transcript.json`: authoritative word timestamps, caption confidence, and review queue.
- `captions-review.srt`: editable captions generated from timestamped words.
- `viral-shorts-plan.json`: ranked Short windows, accurate hooks, promotion fields, and per-clip image-generation requests.
- `viral-long-plan.json`: chapter plan, accurate promotion requirements, and long-form thumbnail request.
- `debate-run.json`: publishing gate and next action.
- `raw-groq-responses.json`: preserved provider evidence for auditing.

## Hard rules

- Treat audio as immutable unless the user explicitly requests an audio edit.
- Use `patch-visuals` for picture-only replacements; it stream-copies the master AAC audio.
- Never overwrite an approved version.
- Never trust labels alone. Inspect source windows and rendered frames.
- Protect literal lyric actions and debate quotes with exact word timestamps.
- Reject repeated source windows, irrelevant filler, accidental text, deceptive context removal, and untreated portrait sidebars.
- Keep AI output advisory. Validators, timing math, source audio, rendering, and QC decide what ships.
- Preserve the original/classic workflow. Debate mode, universal catalog, and swarm planning are additive.

## Universal catalog swarm

Run `inventory` against any mix of generator exports, cameras, downloads, or archives. Then run `swarm-plan --catalog catalog.json --brief "..." --agents 100 --output swarm-plan.json`. The swarm uses 100 bounded local editorial voters and may optionally perform one GPT-5.6 synthesis with `--synthesize openai`.

Read [references/workflow.md](references/workflow.md) for classic command templates and [references/bigo-debate.md](references/bigo-debate.md) for the production debate contract.
