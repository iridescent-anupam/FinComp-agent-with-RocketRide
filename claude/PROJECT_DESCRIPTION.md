# Project Description — Data Handling Compliance Checker

> `compliance-checker.pipe` and `index.html` are built, deployed, and
> confirmed working end-to-end against the live RocketRide Cloud API (not
> just locally authored) — see the real captured run at the bottom.

## Implementation notes / deviations from the original AGENTS.md plan
`.rocketride/docs/` (the mandatory reading list in `.claude/rules/rocketride.md`)
did not exist in this repo — only `.rocketride/schema/` (126 node schemas) and
`services-catalog.json` did. The pipeline was authored and iterated against
those plus RocketRide's hosted docs (`docs.rocketride.org`) and, ultimately,
live testing against `api.rocketride.ai` via the installed `rocketride`
Python SDK (`.venv`), since the schema files alone weren't enough to get a
working pipeline. Four deliberate deviations from AGENTS.md's literal spec:

1. **Audit trail node**: swapped `Memory (Internal)` for `Persistent Memory`
   (`memory_persistent`, `backend: "memory"`). RocketRide's docs confirm
   `Memory (Internal)` is run-scoped (cleared after every webhook call) — it
   cannot back a cross-request history view. `Persistent Memory` retains data
   across invocations and its in-memory backend needs no external Redis, so
   the $0-external-cost constraint still holds.
2. **No `tool_python` lookup node**: `regulations.json`'s 5 entries are small
   enough to embed directly as prompt text instead of fetching them via a
   Python tool at runtime. Closed-set enforcement is done via Guardrails'
   `allowed_topics` keyword check (the 5 regulation ids) with
   `policy_mode: "block"`, rather than the Python fallback AGENTS.md
   pre-approved.
3. **No `CrewAI Agent` (or any agent) nodes — this is the big one.**
   Every agent node type RocketRide offers (`agent_crewai` standalone,
   `agent_crewai_manager` + `agent_crewai_subagent`, and `agent_langchain`)
   fails at runtime with `You must have 1, and only 1 llm node connected to
   your agent`, thrown at `__init__` in a shared server-side module
   (`/opt/rocketride/ai/common/agent/_internal/host.py:33`) before any data
   is processed. This was confirmed as a genuine platform bug, not a
   pipeline-authoring mistake, by exhaustively testing every plausible wire
   format for the agent→LLM `control` connection (8 variants: the
   documented `{"classType":"llm","from":"..."}` shape, provider-name
   `classType`, an `invoke` key instead of `control`, the connection
   declared in reverse on the LLM node, plain string ids, `id` instead of
   `from`, an extra `config.llm` field, and no connection at all) against
   both a minimal 4-node repro and the full pipeline — all either got
   rejected by the server's own JSON validation (proving the *correct*
   variants really were syntactically fine) or hit the identical runtime
   error. Switching from CrewAI to LangChain agents made no difference —
   same error, same file/line, confirming the bug lives in infrastructure
   shared across every agent framework the platform offers, not in a
   specific implementation.

   **Workaround shipped instead:** Triage → Verdict → Audit is one
   `llm_openai` completion (no agent wrapper), fed by a `Prompt` node that
   packs all three reasoning passes' instructions into a single request —
   explicitly told to treat them as separate passes and to actively look for
   reasons the Verdict could be wrong before confirming it, rather than
   rubber-stamping. This is a real, working architectural downgrade from
   "three independent models cross-checking each other" to "one model doing
   structured self-critique" — worth reverting once RocketRide fixes the
   agent-node bug, since genuine multi-agent independence is a stronger
   correctness guarantee than any single model's self-critique, no matter
   how it's prompted. Everything else — PII redaction (NER + Anonymize),
   both Guardrails passes (pre-LLM prompt-injection/PII check, post-LLM
   PII/format/closed-set check), and the persisted audit trail — is real
   and unaffected by this.
4. **History view is client-side, not server-queryable.** The original design
   had the Auditor agent call a `memory` control connection to read back
   recent audit records for the frontend. With no working agent node, there's
   no way to invoke `Persistent Memory`'s query methods from within the
   pipeline. Every run still writes a real record to `mem_persistent_1`
   (verifiable server-side), but `index.html` currently keeps its own
   browser-local history via `localStorage` rather than reading the
   pipeline's own audit trail back out. Revisit once agent nodes work again.

## Problem
Compliance teams handle customer complaints and internal data-practice
descriptions that often contain real personal data (names, emails, phone
numbers) mixed in with the substance of the issue. A tool that pipes that
text straight into an LLM both leaks PII into a model's context unnecessarily
and produces reasoning that isn't reliably traceable back to an actual rule
— and a single LLM call reasoning end-to-end has no independent check on its
own conclusions.

## Solution
A compliance-checker pipeline that: (1) detects and redacts PII before any
reasoning step ever sees it, (2) a single structured LLM pass extracts
Triage fields (constrained to a closed set of known regulations, enforced by
a guardrail), reasons to a Verdict grounded strictly in the matched
regulation's text, then performs an explicit Audit self-critique pass that
actively looks for reasons the Verdict could be wrong rather than confirming
it, and (3) a final guardrail pass validates the combined output before it's
returned and persisted to an audit log. Originally designed as three
independent agents (Triage/Verdict/Audit) cross-checking each other; a
platform-wide bug in RocketRide's agent nodes (see deviation #3 above) forced
a fallback to one model performing three explicit, separately-instructed
reasoning passes instead. Every stage that *isn't* the LLM reasoning itself —
redaction, both guardrail checks, the audit write — is still a discrete,
inspectable native RocketRide node.

## RocketRide Cloud pipeline structure
As deployed and confirmed working in `compliance-checker.pipe`:
- `webhook_1` — accepts raw text (`Content-Type: text/plain`), may contain
  raw PII
- `ner_1` (Named Entity Recognition, BERT Large) — detects names, emails,
  phones, locations in `text` lane from the webhook
- `anonymize_1` (Anonymize, GLiNER PII Large) — masks entities found by NER
- `question_1` (Question) — bridges the redacted `text` lane into a
  `questions` lane
- `prompt_1` (Prompt) — packs the closed regulation set and the
  Triage/Verdict/Audit instructions onto the redacted `questions` input
- `guardrails_input_1` (Guardrails, custom profile, `policy_mode: block`) —
  pre-LLM check: prompt-injection detection, PII (defense-in-depth in case
  Anonymize missed something), max input length
- `llm_openai_1` (OpenAI, `gpt-4o-mini`) — the single completion producing
  `{practice, data_type, jurisdiction, regulation_guess, risk_level, verdict,
  reasoning, cited_regulation, confidence, audit_passed, audit_notes,
  final_verdict, audit_id, redacted_text_seen}`
- `guardrails_final_1` (Guardrails, custom profile, `policy_mode: block`) —
  validates JSON format, no PII leakage, and that the cited regulation is one
  of the 5 allowed ids (`allowed_topics`)
- `mem_persistent_1` (Persistent Memory, `backend: memory`) — writes the
  validated answer to the audit trail via its native lane-based auto-store
  (no external DB); see deviation #4 above re: read-back
- `response_answers_1` (Return Answers) — returns the final JSON to the caller
- Webhook: `POST https://api.rocketride.ai/webhook`, `Authorization: Bearer
  <publicToken>` — see `test_pipeline.py` for how to start a run and get a
  fresh token/publicToken pair

## Why redaction, guardrails, and an audit trail — even without true multi-agent
The core "responsible AI" value — PII never reaching the model, a closed set
of citable regulations enforced by a native guardrail (not just a prompt
request), and a persisted audit record for every run — survives the
agent-node workaround intact. What's lost is *architectural* independence
between the reasoning passes: a single model doing self-critique is weaker
than a separate model re-deriving the answer from scratch, because it can
still be anchored on its own first answer. The prompt explicitly instructs
against this ("actively look for a reason the Verdict could be wrong before
confirming it"), and in testing it did catch a real issue (see example below)
— but that's not the same guarantee as genuine independence, and should be
called out as a known limitation of the current build, not glossed over.

## Responsible AI design decisions
- **PII never reaches the reasoning step.** NER + Anonymize run before the
  prompt is ever built, so the LLM call only ever sees masked text.
- **No hallucinated regulations.** The prompt constrains `regulation_guess`/
  `cited_regulation` to a closed set of 5 ids; `guardrails_final_1` rejects
  anything outside that set via `allowed_topics`.
- **Guardrails run twice** — once on the built prompt before it reaches the
  LLM (injection/PII), once on the final output (PII/format/allowed
  regulations) — rather than trusting a single validation pass.
- **Every verdict cites a specific regulation entry**, not a general
  impression of "GDPR" or "CCPA" — from a maintained reference table.
- **Persisted audit trail.** Every validated run is written to
  `Persistent Memory`, not just returned once and discarded — though see
  deviation #4 for the current read-back limitation.

## Cost
The only paid dependency is OpenAI `gpt-4o-mini` (one call per run, well
under a cent). PII detection, redaction, guardrail validation, and the audit
trail all run on RocketRide's built-in nodes with no additional external
service or API key. No web search API of any kind is used.

### Example of output (real captured run, `pii_redaction_demo` scenario)
```
Input:
Hello, my name is Maria Alvarez and I requested deletion of my account on
your EU site over six months ago. You still have my email
maria.alvarez@example.com and my phone number +34 612 345 678 on file, and I
received a marketing email from you just last week. My address is Calle
Mayor 12, Madrid, Spain. Please explain why my data has not been deleted.

Redacted (as seen by the LLM, via redacted_text_seen echoed back):
Hello, my name is █████████████ and I requested deletion of my account on
your ██ site over six months ago. You still have my email
█████████████████████████ and my phone number ███████████████ on file, and
I received a marketing email from you just last week. My address is
█████████████████████████████. Please explain why my data has not been
deleted.

Triage: practice="Failure to delete personal data after a valid deletion
request.", data_type="Email, phone number, address", jurisdiction="EU",
regulation_guess="gdpr_art17", risk_level="high"

Verdict: verdict="non-compliant", cited_regulation="gdpr_art17",
confidence="high", reasoning="The organization did not comply with the
request for deletion of personal data within the required timeframe,
violating the right to erasure under GDPR Article 17."

Audit: audit_passed=false, audit_notes="While the organization failed to
delete the data, the reasoning did not consider potential overriding legal
grounds for retention, which could affect compliance status.",
final_verdict="needs_review"

Audit ID: audit-4f2a1b3c
```
This is a genuine catch, not a decorative one: the Verdict pass concluded
`non-compliant`, and the Audit pass downgraded it to `needs_review` because
the reasoning hadn't ruled out a legitimate retention justification — exactly
the kind of self-correction the three-stage prompt was designed to produce.
```

## What I'd do next
1. **Revert to true multi-agent once RocketRide fixes the agent-node bug**
   (deviation #3) — file it with them using the minimal 4-node repro; this is
   the single highest-value change, since it restores genuine cross-model
   independence instead of one model's self-critique.
2. Recover server-side history read-back (deviation #4) once agents work
   again, replacing the current `localStorage`-only frontend history.
3. Expand the regulation reference table beyond GDPR/CCPA.
4. Add a human-review escalation path for `needs_review` verdicts.