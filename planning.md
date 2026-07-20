# Provenance Guard

A backend system that classifies submitted creative writing as likely AI-generated,
likely human-written, or uncertain — using two independent detection signals, a
calibrated confidence score, a transparency label, and an appeals process for
creators who believe they were misclassified.

## Architecture

When a creator submits writing via POST /submit, the text passes through Signal 1
(LLM judge) and Signal 2 (stylometry) independently, and their scores are combined
into one confidence score, which maps to a transparency label describing if the
text is written by AI or human. Every step is recorded in the audit log. If a
creator disputes their label, POST /appeal updates that same log entry's status
to "under_review" and appends their reasoning.

Submission flow:
POST /submit
→ Signal 1 (LLM judge) ──┐
→ Signal 2 (stylometry) ─┴→ confidence scoring → label → audit log → response
Appeal flow:
POST /appeal → find content_id → status = "under_review"
→ append to existing audit log entry → response

## Detection Signals

Signal 1 — LLM Judge. Sends the submitted text to an LLM with a prompt asking it
to rate on a scale from 0 to 1 how likely the text is to be AI generated, along
with a short explanation. Outputs a float between 0 and 1. Initial testing revealed
a real problem: the model would sometimes give reasoning that clearly argued for
"AI-generated" but still output a low score (e.g. reasoning said "consistent with
AI-generated content" while scoring 0.3). Reordering the prompt so reasoning is
written before the score, and adding explicit scale anchors (0.0–0.2 = clearly
human, 0.8–1.0 = clearly AI), fixed the mismatch — the model's stated reasoning
and its numeric score now agree.

Signal 2 — Stylometric Heuristics. Computes sentence length variance and how many
unique words were used out of total words. These are normalized and averaged into
a single float between 0 and 1, where higher = more "AI-like." I initially used
raw sentence-length variance, but a single short or long outlier sentence (e.g. a
one-word sentence like "Underwhelming.") would inflate the raw variance number
and swamp the signal, making it fail to distinguish AI from human text at all.
Switching to coefficient of variation (standard deviation ÷ mean) fixed this by
measuring variability relative to the text's own average sentence length, rather
than in absolute terms.

Combining them: combined_score = (0.7 * signal1_score) + (0.3 * signal2_score).
Signal 1 is weighted higher because it reads the whole text holistically, while
Signal 2 is a narrower statistical check used to support or challenge Signal 1's
read. My original spec called for a 0.6/0.4 weighting, but testing against four
canonical inputs (clearly AI, clearly human, and two borderline cases) showed
0.6/0.4 let a noisy Signal 2 reading pull a clearly-AI example (0.90 on Signal 1)
down into the "uncertain" range (0.61) instead of a confident "likely AI."
Bumping Signal 1's weight to 0.7 fixed this while still preserving the system's
ability to catch a real false positive (see Appeals Workflow below).

**What I'd change for a real deployment:** Signal 1 depends entirely on a single
LLM call, which means it inherits that model's blind spots wholesale — including
the formality bias documented below. In production I'd want a second, independent
LLM judge from a different model family (not just a different prompt) to
cross-check Signal 1, since two different models are less likely to share the
same blind spot. I'd also want Signal 2 computing on a rolling basis across a
creator's submission history, not just one document at a time and a single short
caption will always be statistically weak on its own, but a creator's writing
style across dozens of submissions is a much sturdier signal.

**Two example submissions with different confidence scores:**

| Input | Signal 1 | Signal 2 | Confidence | Label |
|---|---|---|---|---|
| "Artificial intelligence represents a transformative paradigm shift..." | 0.90 | 0.17 | 0.68 | Likely AI-generated |
| "ok so i finally tried that new ramen place downtown and honestly?..." | 0.00 | 0.06 | 0.01 | Likely human-written |

## Uncertainty Representation

A confidence score is the combined_score from above, always between 0 and 1.

- 0.00–0.40: "likely human" — both signals lean human, or signal 2 has low
  confidence because the text is too short.
- 0.40–0.65: "uncertain" — signals disagree, or both are borderline.
- 0.65–1.00: "likely AI" — both signals lean AI like.

I picked 0.40 and 0.65 (not a single 0.5 cutoff) specifically so a mixed or
borderline case doesn't get treated with false confidence.

## Transparency Label Design

Exact text for each variant:

- High confidence AI (score ≥ 0.65): "This content is likely AI generated. (Confidence: {score})"
- Uncertain (0.40–0.65): "This content's origin is uncertain - our signals produced mixed results. (Confidence: {score})"
- High-confidence human (score < 0.40): "This content is likely human written. (Confidence: {score})"

## Appeals Workflow

Who: any creator_id who submitted a piece of content.
What they provide: content_id and free text explaining why they believe the label
is wrong.
What happens: the system finds the existing log entry for that content_id,
changes its status field from "classified" to "under_review", appends the
creator_reasoning text to that same entry, and returns a confirmation message to
the creator.
What a reviewer sees: opening GET /log shows the full original entry (both
signal scores, combined confidence, original label) with the appeal reasoning
sitting right next to it — so they see the evidence and the creator's
explanation together, not in separate places.

**Real test case (this is the exact false-positive scenario from my original
architecture plan, actually occurring in testing):** A formal paragraph about
monetary policy which is genuinely human-written but formal and uniform in style,
scored 0.80 on Signal 1 alone, which would have crossed the 0.65 "likely AI"
threshold on its own. The combined score (with Signal 2 pulling it down) landed
at 0.64 and correctly "uncertain" rather than a false "likely AI." I then
submitted a real appeal against this content_id:

```json
{
  "appeal_reasoning": "I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical.",
  "attribution": "uncertain",
  "confidence": 0.6404863419412555,
  "content_id": "48deecb7-4cc5-4ad9-a5fb-8db26fb5a7d7",
  "creator_id": "test-user-formal",
  "llm_score": 0.8,
  "status": "under_review",
  "stylometry_score": 0.2682878064708518,
  "timestamp": "2026-07-20T01:50:25.255725+00:00"
}
```

## Rate Limiting

`/submit` is limited to **10 requests per minute and 100 per day per IP**, using
Flask-Limiter with in-memory storage. 10/minute is generous enough for a real
writer submitting their own work (no legitimate user submits 10 pieces of
writing inside one minute) while still blocking a script flooding the endpoint.
100/day caps sustained abuse without blocking heavy legitimate daily use.

**Evidence — 12 rapid requests sent, exceeding the 10/minute limit:**

127.0.0.1 - - [19/Jul/2026 19:34:47] "POST /submit HTTP/1.1" 200 -
127.0.0.1 - - [19/Jul/2026 19:34:47] "POST /submit HTTP/1.1" 200 -
127.0.0.1 - - [19/Jul/2026 19:34:47] "POST /submit HTTP/1.1" 200 -
127.0.0.1 - - [19/Jul/2026 19:34:48] "POST /submit HTTP/1.1" 200 -
127.0.0.1 - - [19/Jul/2026 19:34:48] "POST /submit HTTP/1.1" 200 -
127.0.0.1 - - [19/Jul/2026 19:34:48] "POST /submit HTTP/1.1" 200 -
127.0.0.1 - - [19/Jul/2026 19:34:48] "POST /submit HTTP/1.1" 200 -
127.0.0.1 - - [19/Jul/2026 19:34:49] "POST /submit HTTP/1.1" 200 -
127.0.0.1 - - [19/Jul/2026 19:34:49] "POST /submit HTTP/1.1" 200 -
127.0.0.1 - - [19/Jul/2026 19:34:49] "POST /submit HTTP/1.1" 200 -
127.0.0.1 - - [19/Jul/2026 19:34:49] "POST /submit HTTP/1.1" 429 -
127.0.0.1 - - [19/Jul/2026 19:34:49] "POST /submit HTTP/1.1" 429 -

## Audit Log Sample

                    {
                        "attribution":  "likely_human",
                        "confidence":  0.01285714285714286,
                        "content_id":  "80f21741-fe4a-4b21-b51c-6bfe73abca34",
                        "creator_id":  "test-user-human",
                        "llm_score":  0.0,
                        "status":  "classified",
                        "stylometry_score":  0.04285714285714287,
                        "timestamp":  "2026-07-20T01:49:23.241677+00:00"
                    },
                    {
                        "appeal_reasoning":  "I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical.",
                        "attribution":  "uncertain",
                        "confidence":  0.6404863419412555,
                        "content_id":  "48deecb7-4cc5-4ad9-a5fb-8db26fb5a7d7",
                        "creator_id":  "test-user-formal",
                        "llm_score":  0.8,
                        "status":  "under_review",
                        "stylometry_score":  0.2682878064708518,
                        "timestamp":  "2026-07-20T01:50:25.255725+00:00"
                    },
                    {
                        "attribution":  "likely_ai",
                        "confidence":  0.836,
                        "content_id":  "7bd2e23f-2d08-41b1-9e4a-fd41f896577a",
                        "creator_id":  "ratelimit-test",
                        "llm_score":  0.98,
                        "status":  "classified",
                        "stylometry_score":  0.5,
                        "timestamp":  "2026-07-20T02:34:49.507108+00:00"
                    }

## Anticipated Edge Cases / Known Limitations

Very short submissions like a haiku would cause issues since Signal 2
(stylometry) needs enough words to compute meaningful sentence length variance.
On something like a 10 word submission, these stats are close to meaningless,
so the combined score leans too heavily on Signal 1 alone without me flagging
that in the response.

Formal or non native English writing can also cause Signal 1 to over associate
careful, grammatically uniform prose with "AI like" patterns, even when it's a
human writing carefully in a non native language. This risks a false "likely
AI" result for a specific group of real people writing — and this is not just
theoretical: a formal paragraph about monetary policy scored 0.80 on Signal 1
alone in real testing (see Appeals Workflow above), high enough to cross the
"likely AI" threshold on its own.

## Spec Reflection

My planning.md's confidence formula (0.6 Signal 1 / 0.4 Signal 2) held up well
conceptually — combining a holistic LLM judge with a narrower statistical check
is what let me catch and correctly handle a real false positive. I diverged when I 
changed the actual weighting to 0.7/0.3 after testing against my
four canonical inputs showed 0.6/0.4 let a noisy Signal 2 reading pull an
obviously AI example down into "uncertain." I made this change deliberately and
verified it against all four test cases before locking it in, rather than
picking a number that just looked better on one case.

## AI Usage

1. **Signal 1 prompt design:** I asked Claude to generate the Groq-based LLM
   judge function from my planning.md's Detection Signals section. The first
   version produced a function where the model's stated reasoning and its
   numeric score sometimes contradicted each other (reasoning said
   "AI-generated," score said 0.3). I caught this by testing directly and
   printing raw output, then had Claude revise the prompt to require reasoning
   before the score plus explicit scale anchors, which fixed the mismatch.
2. **Signal 2 stylometry bug:** The first version of the stylometry function
   used raw sentence-length variance, which I tested against real examples and
   found was getting distorted by single outlier sentences (like a one-word
   sentence), causing it to fail to distinguish AI from human text at all. I
   asked for a fix, and the revised version used coefficient of variation
   instead, which corrected the issue.

## AI Tool Plan

M3 (submission endpoint + Signal 1): I gave the AI tool the Detection Signals
section + the diagram, and asked it to generate a Flask skeleton with a POST
/submit stub plus the Signal 1 function. I verified by calling Signal 1
directly with test strings and checking the output was a float between 0 and 1
matching my spec, before wiring it into the route.

M4 (Signal 2 + confidence scoring): I gave it the Detection Signals +
Uncertainty Representation sections + the diagram, and asked for the Signal 2
function plus the scoring logic. I verified by running the 4 test inputs from
the project doc and checking scores differed meaningfully between the
clearly-AI and clearly-human examples, and adjusted the weighting when
thresholds didn't behave as expected.

M5 (production layer): I gave it the Transparency Label Design + Appeals
Workflow sections + the diagram, and asked for the label generation function
and the POST /appeal endpoint. I verified by forcing inputs that hit all three
label ranges, and by submitting a real appeal and confirming GET /log showed
status: under_review with the reasoning attached.

