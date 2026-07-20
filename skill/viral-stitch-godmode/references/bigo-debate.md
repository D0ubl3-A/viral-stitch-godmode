# Bigo Debate God Mode production contract

## Purpose

Turn a 1-2 hour Bigo Live panel debate into a transcript-locked content package containing high-retention vertical clips, an edited long-form debate, accurate captions, metadata, chapters, active-speaker visuals, and original image-generated thumbnails.

## Accuracy gate

Groq provides the first-pass transcript and word timestamps. It is not treated as infallible. The pipeline deliberately blocks publication when caption confidence falls below the configured threshold. A reviewer must compare every flagged segment to the original audio, correct names and wording, and then lock the transcript.

Every public-facing claim must be traceable to the locked transcript:

- Quotation marks require exact verbatim words.
- “Admits,” “lies,” “loses,” “gets destroyed,” “debunked,” and similar claims require clear support from the full exchange, not a misleading excerpt.
- Panelist names must come from the approved panelist list and spelling glossary.
- Numbers, dates, organizations, scripture references, legal terms, political terms, and proper nouns must be checked manually when confidence is low.

## Active-speaker truth

Bigo panel recordings usually indicate the current speaker by lighting, animating, or outlining that participant's tile. Treat this UI state as timestamped evidence, not decoration.

1. Define each panel tile once with normalized `x`, `y`, `width`, and `height` coordinates plus the approved display name and reference image.
2. Sample frames throughout the source recording.
3. For every tile, measure border luminance, saturation change, glow animation, and mouth-motion energy.
4. Require a stable winner with a confidence margin. Reject ties and uncertain intervals instead of assigning the wrong speaker.
5. Produce speaker intervals aligned to the Groq word timestamps.
6. Every crop, caption label, generated likeness, and reaction shot must use the verified interval.

The lit box identifies who is speaking. It does not prove who is correct, who won, or what another participant felt.

## Short selection contract

Each Short should:

1. Open with an intelligible hook inside 1-4 seconds.
2. Include enough setup to understand the disagreement.
3. Preserve the response or payoff.
4. Avoid cuts that reverse or distort meaning.
5. Prefer 25-75 seconds unless a complete exchange requires a justified exception.
6. Use 9:16 framing with active-speaker prioritization and captions inside safe margins.
7. Avoid duplicate moments across the batch.
8. Prefer exchanges with a claim, challenge, quote-back, contradiction, evidence, rebuttal, and understandable payoff.

The edit may make a clean rebuttal feel decisive, memorable, and like the point was served up debate-style. It must not falsely declare a winner, manufacture humiliation, invent facial reactions, or create a fake admission.

## Context-aware generated visuals

For each selected viral clip, split the transcript into visual beats. A beat may use:

- **Speaker dominant:** the active speaker's accurate likeness, with verified opponent tiles as secondary context.
- **Argument visualization:** a clear image of the concrete subject being discussed, such as constitutional rights, courts, economics, religion, public policy, history, or everyday consequences.
- **Evidence emphasis:** transcript-supported numbers, documents, locations, or concepts, without fabricating evidence.
- **Symbolic-safe fallback:** when an explicit visualization would be inappropriate, use a respectful symbolic background rather than showing the explicit act.

For American political or civic discussion, select the symbolic fallback intelligently:

- Use an American flag or constitutional civic background when the actual statement supports America, American institutions, veterans, constitutional rights, or patriotic values.
- Use a neutral world, civic, or debate-stage background when the actual statement is critical of America or does not express a patriotic stance.
- Never assign patriotism, anti-American sentiment, party affiliation, religion, or ideology from appearance alone. Derive it only from the approved transcript and surrounding context.

Panelists may discuss controversial or adult topics. The transcript and debate itself remain intact. Only the generated visualization falls back to a non-explicit symbolic treatment when an explicit depiction would be unsuitable.

## Long-form contract

The long-form edit should preserve representative context, remove only dead air, repeated introductions, technical interruptions, unrelated waiting, and redundant loops. It must include transcript-derived chapter timestamps and clearly state that it is an edited Bigo panel debate.

## Image-generation call contract

Call the installed image-generation skill through `image_gen` after clip approval. Every request must include:

- exact clip start and end timestamps;
- active speaker ID and approved display name;
- supplied reference image for every depicted panelist;
- transcript excerpt and surrounding context;
- visual mode and subject;
- prohibited claims and prohibited invented text;
- caption-safe area;
- output ratio and platform;
- a statement that generated text is not permitted unless copied exactly from the locked transcript.

Generated thumbnails and inserts must be original, high-contrast, mobile-readable, and faithful to the clip. Do not invent facial injuries, weapons, tears, arrests, admissions, quote text, or events that were not present.

When no approved reference image exists, keep the original Bigo tile or use a non-likeness symbolic visual. Do not guess a private person's face.

## Promotion contract

Generate platform-specific titles, descriptions, tags, and chapter text only from the locked transcript. Titles should lead with the real unresolved question, contradiction, admission, rebuttal, or factual dispute. Descriptions should identify the speakers and clarify that the source is an edited Bigo panel debate. Avoid spam keyword stuffing and unsupported certainty.

## Publishing gate

A clip cannot publish until all of these pass:

- active speaker timing verified;
- words verified against source audio;
- panelist names and spellings approved;
- selected context image matches the actual topic;
- symbolic fallback matches the speaker's actual stated position;
- no fabricated quote, admission, ideology, winner claim, or reaction;
- clip preserves enough context to represent the exchange fairly;
- thumbnail and title accurately describe the clip;
- captions remain synchronized and readable on mobile.

## Required evidence retained

Keep the original source, raw Groq responses, approved glossary, transcript versions, speaker-tile map, active-speaker event file, selected source windows, caption files, render manifests, thumbnail prompts, and final QC report. This makes every published word and claim auditable.
