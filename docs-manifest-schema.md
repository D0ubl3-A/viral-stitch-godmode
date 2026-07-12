# Viral Stitch Manifest

Use UTF-8 JSON. Relative paths resolve from the manifest directory.

```json
{
  "project": "Project title",
  "audio": "D:/media/song.mp3",
  "audio_analysis": "D:/media/audio-analysis.json",
  "output": "D:/media/project-v03-final.mp4",
  "proof_output": "D:/media/project-v03-proof.mp4",
  "work_dir": "D:/media/work/project-v03",
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "crf": 18,
  "transition_duration": 0.2,
  "target_lufs": -14.0,
  "true_peak": -1.5,
  "auto_microcuts": true,
  "max_shot_duration": 2.8,
  "forbidden_patterns": ["Kover", "spaceman", "UFO", "Final_system_transition"],
  "checkpoints": [
    {
      "name": "Squad Formation",
      "start": 0.0,
      "end": 7.26,
      "lyric_cue": "opening call and formation",
      "transition": "fadeblack",
      "shots": [
        {
          "label": "cold open impact",
          "source": "D:/media/action.mp4",
          "source_start": 4.0,
          "duration": 1.2,
          "zoom": 1.06,
          "microcut": false
        }
      ]
    }
  ]
}
```

## Required fields

- Root: `audio`, `output`, `work_dir`, `checkpoints`.
- Checkpoint: `name`, `start`, `end`, `shots`.
- Shot: `source`, `source_start`, `duration`.

## Timing rule

For every checkpoint except the last:

`sum(shots.duration) = checkpoint.end - checkpoint.start + transition_duration`

For the last checkpoint:

`sum(shots.duration) = checkpoint.end - checkpoint.start`

This overlap keeps checkpoint starts fixed after transitions are assembled.

## Optional shot controls

- `label`: Human-readable manifest/QC label.
- `zoom`: Static crop multiplier from `1.0` to `1.8`; reserve values above `1.35` for intentional detail shots.
- `speed`: Source playback rate while preserving the shot's timeline `duration`; use values below `1.0` for slow motion and above `1.0` for acceleration.
- `microcut`: Set `false` to preserve a continuous healing, reveal, or ending shot.

When `auto_microcuts` is enabled, shots longer than `max_shot_duration` are split into sequential jump cuts with alternating crop multipliers. Source time remains continuous and total checkpoint timing does not change.

## Supported transitions

Use restrained FFmpeg `xfade` names such as `fade`, `fadeblack`, `fadewhite`, `dissolve`, `smoothleft`, `smoothright`, `hblur`, or `radial`.
