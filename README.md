# Provenance Guard

A backend system that classifies submitted creative writing as likely AI-generated,
likely human-written, or uncertain — using two independent detection signals,
a calibrated confidence score, a transparency label, and an appeals process for
creators who believe they were misclassified.

## Architecture

When a creator submits writing via `POST /submit`, the text passes through Signal 1
(an LLM judge) and Signal 2 (stylometric heuristics) independently. Their scores are
combined into one confidence score, which maps to a transparency label. Every
submission is recorded in the audit log. If a creator disputes their label, `POST
/appeal` updates that same log entry's status to `under_review` and appends their
reasoning alongside the original evidence.