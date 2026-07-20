# Bigo Debate God Mode production contract

## Purpose

Turn a 1-2 hour Bigo Live panel debate into a transcript-locked content package containing high-retention vertical clips, an edited long-form debate, accurate captions, metadata, chapters, and original image-generated thumbnails.

## Accuracy gate

Groq provides the first-pass transcript and word timestamps. It is not treated as infallible. The pipeline deliberately blocks publication when caption confidence falls below the configured threshold. A reviewer must compare every flagged segment to the original audio, correct names and wording, and then lock the transcript.

Every public-facing claim must be traceable to the locked transcript:

- Quotation marks require exact verbatim words.
- “Admits,” “lies,” “loses,” “gets destroyed,” “debunked,” and similar claims require clear support from the full exchange, not a misleading excerpt.
- Panelist names must come from the approved panelist list and spelling glossary.
- Numbers, dates, organizations, scripture references, legal terms, political terms, and proper nouns must be checked manually when confidence is low.

## Short selection contract

Each Short should:

1. Open with an intelligible hook inside 1-4 seconds.
2. Include enough setup to understand the disagreement.
3. Preserve the response or payoff.
4. Avoid cuts that reverse or distort meaning.
5. Prefer 25-75 seconds unless a complete exchange requires a justified exception.
6. Use 9:16 framing with active-speaker prioritization and captions inside safe margins.
7. Avoid duplicate moments across the batch.

## Long-form contract

The long-form edit should preserve representative context, remove only dead air, repeated introductions, technical interruptions, unrelated waiting, and redundant loops. It must include transcript-derived chapter timestamps and clearly state that it is an edited Bigo panel debate.

## Thumbnail generation contract

Call the installed image-generation skill through `image_gen` after clip approval. For accurate people, provide panelist reference images. Generated thumbnails must be original, high-contrast, mobile-readable, and faithful to the clip. Do not invent facial injuries, weapons, tears, arrests, admissions, quote text, or events that were not present.

## Promotion contract

Generate platform-specific titles, descriptions, tags, and chapter text only from the locked transcript. Titles should lead with the real unresolved question, contradiction, admission, or factual dispute. Descriptions should identify the speakers and clarify that the source is an edited Bigo panel debate. Avoid spam keyword stuffing and unsupported certainty.

## Required evidence retained

Keep the original source, raw Groq responses, approved glossary, transcript versions, selected source windows, caption files, render manifests, thumbnail prompts, and final QC report. This makes every published word and claim auditable.
