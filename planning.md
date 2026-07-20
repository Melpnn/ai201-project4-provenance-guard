## Detection Signals

Signal 1 — LLM Judge. Sends the submitted text to an LLM with a prompt asking it to rate on a scale from 0 to 1 how likely the text is to be AI generated, along with a short explanation. Outputs a float between 0 and 1

Signal 2 — Stylometric Heuristics. Computes sentence length variance and how many unique words were used out of total words. These are normalized and averaged into a single float between 0 and 1, where higher = more "AI-like".

Combining them: combined_score = (0.7 * signal1_score) + (0.3 * signal2_score). Signal 1 is weighted higher because it reads the whole text holistically, while Signal 2 is a narrower statistical check used to support or challenge Signal 1's read.

## Uncertainty Representation
A confidence score is the combined_score from above, always between 0 and 1.

0.00–0.40: "likely human" — both signals lean human, or signal 2 has low confidence because the text is too short.
0.40–0.65: "uncertain" — signals disagree, or both are borderline.
0.65–1.00: "likely AI" — both signals lean AI like.

I picked 0.40 and 0.65 (not a single 0.5 cutoff) specifically so a mixed or borderline case doesn't get treated with false confidence. 

## Transparency Label Design
Exact text for each variant:

High confidence AI (score ≥ 0.65): "This content is likely AI generated. (Confidence: {score})"
Uncertain (0.40–0.65): "This content's origin is uncertain - our signals produced mixed results. (Confidence: {score})"
High-confidence human (score < 0.40): "This content is likely human written. (Confidence: {score})"

## Appeals Workflow

Who: any creator_id who submitted a piece of content.
What they provide: content_id and free text explaining why they believe the label is wrong.
What happens: the system finds the existing log entry for that content_id, changes its status field from "classified" to "under_review", appends the creator_reasoning text to that same entry, and returns a confirmation message to the creator.
What a reviewer sees: opening GET /log shows the full original entry (both signal scores, combined confidence, original label) with the appeal reasoning sitting right next to it — so they see the evidence and the creator's explanation together, not in separate places.

## Anticipated Edge Cases

Very short submissions like a haiku would cause issues since Signal 2 (stylometry) needs enough words to compute meaningful sentence length variance. On something like a 10 word submission, these stats are close to meaningless, so the combined score leans too heavily on Signal 1 alone without me flagging that in the response.
Formal or non native English writing can also cause Signal 1 to over associate careful, grammatically uniform prose with "AI like" patterns, even when it's a human writing carefully in a non native language. This risks a false "likely AI" result for a specific group of real people writing.

## Architecture  

When a creator submits writing via POST /submit, the text passes through Signal 1 (LLM judge) and Signal 2 (stylometry) independently, and their scores are combined into one confidence score, which maps to a transparency label describing if the text is written by AI or human. Every step is recorded in the audit log. If a creator disputes their label, POST /appeal updates that same log entry's status to "under_review" and appends their reasoning.

Submission flow:
POST /submit
   → Signal 1 (LLM judge) ──┐
   → Signal 2 (stylometry) ─┴→ confidence scoring → label → audit log → response

Appeal flow:
POST /appeal → find content_id → status = "under_review"
   → append to existing audit log entry → response

## AI Tool Plan section
M3 (submission endpoint + Signal 1): I'll give the AI tool the Detection Signals section + the diagram, and ask it to generate a Flask skeleton with a POST /submit stub plus the Signal 1 function. I'll verify by calling Signal 1 directly with 2–3 test strings and checking the output is a float between 0 and 1, matching my spec, before wiring it into the route.

M4 (Signal 2 + confidence scoring): I'll give it the Detection Signals + Uncertainty Representation sections + the diagram, and ask for the Signal 2 function plus the scoring logic. I'll verify by running 4 test inputs from the project doc and checking scores actually differ meaningfully between the clearly-AI and clearly-human examples, and that thresholds match 0.40/0.65 exactly.

M5 (production layer): I'll give it the Transparency Label Design + Appeals Workflow sections + the diagram, and ask for the label generation function and the POST /appeal endpoint. I'll verify by forcing inputs that hit all three label ranges, and by submitting a real appeal and confirming GET /log shows status: under_review with the reasoning attached.