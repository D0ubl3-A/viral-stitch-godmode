# Debate Production Intelligence v2

This layer is mandatory for Bigo panels and other multi-speaker debates before publication.

## Speaker identity and attribution

Create a speaker registry containing display name, tile history, approved reference image, voice embedding reference, face embedding reference, and moderator status. Fuse these signals for every interval:

- Bigo active-tile glow
- audio energy by tile or isolated channel
- voice-embedding match
- lip-motion match
- nearby speaker continuity
- manually locked identity

Never publish a quote when the fused decision is unresolved. Tile glow alone is insufficient.

## Two-pass caption verification

Run the initial Groq transcription over the complete chunked recording. For every selected short, chapter hook, title quote, named entity, number, allegation, or low-confidence segment, extract the source audio again and run a focused second transcription pass.

Compare both passes. A mismatch, low-confidence entity, disagreement over a number, crosstalk, or unclear proper name creates a review blocker. The locked transcript is the only source for public quotes and captions.

## Claim and risk classification

Classify every publishable statement as:

- opinion
- prediction
- personal experience
- factual assertion
- serious allegation

Factual assertions must be described as the speaker's claim unless a supporting source card is attached. Serious allegations require human editorial review and must not be dramatized with generated documentary-style imagery.

## Viral clip story scoring

A short must work as a complete miniature story:

1. understandable setup
2. clear conflict
3. rebuttal or escalation
4. payoff or completed response
5. clean ending

Penalize clips that begin mid-sentence, end before the response, contain excessive crosstalk, include too many speakers, rely on missing earlier context, contain dead air, or make unsupported serious allegations.

## Honest impact framing

Do not automatically call a speaker destroyed, humiliated, speechless, exposed, cooked, or defeated. Such language must be directly supported and manually approved. Prefer evidence-based titles such as:

- This Question Changed the Debate
- The Panel Reacted to This Rebuttal
- Their Claims Collided Here
- He Had No Immediate Answer

Quoted title text must appear verbatim in the locked transcript.

## Visual hierarchy

Prefer, in order:

1. actual panel footage
2. real source cards, documents, maps, timelines, or statistics
3. disclosed generated illustration
4. symbolic-safe abstract fallback

Generated imagery is illustrative, not evidence. Never generate a fake photograph of an alleged event. Generated speaker likenesses require an approved reference image and verified active-speaker interval. Add disclosure metadata wherever a generated visual could be mistaken for reality.

## Long-form editing

Long-form output must include more than chapters. Apply:

- dead-air removal
- repeated-point compression without synthetic sentence splicing
- filler reduction where meaning is preserved
- loudness normalization
- layout stabilization
- verified speaker labels
- claim cards and citations where available
- periodic visual resets
- concise argument recaps
- complete chapter endings
- content warnings where necessary

## Render QA

Publication is blocked unless all required checks pass:

- video decodes
- audio exists
- audio/video offset is within tolerance
- no clipping
- captions remain in mobile safe areas
- no caption overflow
- speaker labels are verified
- generated imagery is disclosed
- black-frame rate is acceptable
- title validation passes
- transcript disputes are cleared
- speaker attribution is verified
- serious allegations receive review

Every final package must contain a deterministic audit hash tying its transcript, speaker decisions, claims, title validation, and render checks together.

## Platform exports

Generate separate deliverables for YouTube Shorts, TikTok, Instagram Reels, and YouTube long-form. Respect each platform's aspect ratio, practical duration, caption-safe region, title style, thumbnail requirements, and disclosure needs.
