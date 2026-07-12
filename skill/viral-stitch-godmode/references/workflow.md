# Command workflow

Run commands through the skill wrapper:

```powershell
py scripts/run_viral_stitch.py doctor
py scripts/run_viral_stitch.py inventory --roots "D:\Downloads" "D:\sora" --output catalog.json --exclude dog --exclude bazooka
py scripts/run_viral_stitch.py analyze-audio --audio song.mp3 --output audio-analysis.json
py scripts/run_viral_stitch.py plan --provider openai --model gpt-5.6 --catalog catalog.json --audio-analysis audio-analysis.json --brief brief.md --output editorial-plan.json
py scripts/run_viral_stitch.py audit-manifest --manifest project.json --output audit.json
py scripts/run_viral_stitch.py validate-manifest --manifest project.json
py scripts/run_viral_stitch.py render --manifest project.json --proof-checkpoints 3
py scripts/run_viral_stitch.py qc --video proof.mp4 --manifest project.json --output-dir qc-proof
```

Visual-only correction:

```powershell
py scripts/run_viral_stitch.py patch-visuals --master approved.mp4 --start 25 --end 28 --replacement clean.mp4 --replacement-start 5.8 --output corrected.mp4
```

If the wrapper reports a missing package, install the release URL it prints. `OPENAI_API_KEY` enables GPT-5.6 planning. All other commands work locally without an API key.

