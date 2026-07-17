# AGENTS.md — Responsible, Guardrailed Data Privacy Compliance Checker

## Context
Hackathon build, HackwithSeattle 2.0, using Claude Code inside the
RocketRide VS Code extension. Team has a good amount of build time
available (more than the original 4-hour assumption) — this file reflects
the expanded scope that unlocks, not a rush job.

**UPDATE FROM EVENT ORGANIZERS**: Linkup integration is no longer a
mandatory requirement (confirmed by the panel, event rules changed after the
original problem statement was published). Do not build any Linkup/live web
search integration. RocketRide Cloud deployment is still required — deploy
the final pipeline there, not just locally.

**A teammate circulated an alternate plan (`Regulatory_Watch_Agent_Plan.docx`)
proposing Tavily/Exa/Firecrawl web search, a vector-embedded "risk graph,"
an exposure-scoring formula, and CI/CD release gating. That plan has been
reviewed and rejected — do not build any of it.** Reasons, for context if
it resurfaces: it reintroduces a paid search API ($5-8 per 1,000 queries)
against an explicit low-cost/free requirement; its pipeline JSON uses node
type strings (`source.cron`, `database.vector_store`, `llm.generation`,
`tool.custom_http`, `llm.reconcile`, `action.webhook`) that do not match any
node in the actual RocketRide "Add Node" palette confirmed for this project;
and its scope (enterprise risk graphs, CI/CD gating, webhook dispatch to
external security systems) solves a different, larger problem than the one
being demoed here. Stick to the architecture below.

Given Linkup is gone, the differentiation strategy is: a genuinely
production-credible, **responsible-AI, multi-agent** pipeline — PII
redaction, entity recognition, guardrailed structured outputs, cited
regulation sources, and a persisted, browsable audit trail — built natively
as RocketRide nodes. This is the "sophisticated and working" bar to hit, not
live web grounding.

**Cost constraint**: keep this as close to $0 as possible. Use only the
OpenAI API (key already available, no new signup) with the cheapest capable
model (`gpt-4o-mini`) for every LLM step. `Named Entity Recognition`,
`Anonymize`, `Guardrails`, and `Memory (Internal)` are RocketRide's own
built-in nodes — they run inside the pipeline, not as paid external API
calls, so they cost nothing beyond RocketRide Cloud hosting itself. Do not
introduce any other paid service (no external vector DB, no external audit
DB, no other search API, no other LLM provider).

## What we're building
A "Data Handling Compliance Checker." User describes a data-handling
practice or customer complaint in plain English (may contain real PII, e.g.
names/emails/phone numbers in a customer statement). The app:
1. Detects and redacts PII before any of it reaches the reasoning steps.
2. **Triage Agent** extracts structured fields (jurisdiction, data type,
   practice, likely regulation) from the anonymized text.
3. Validates that extraction against a guardrail (no hallucinated
   regulation names, output schema must conform).
4. **Verdict Agent** looks up the matching entry in a curated GDPR/CCPA
   reference table (`regulations.json`) and produces a verdict (compliant /
   non-compliant / needs review) with reasoning that cites the specific
   regulation/article.
5. **Auditor Agent** independently re-checks the Verdict Agent's output
   against the same `regulations.json` entry — confirming the cited
   regulation actually supports the stated verdict, not just that a
   regulation was cited at all. This is a second, independent reasoning
   pass, not a rerun of the same prompt.
6. A final guardrail pass validates the output (valid JSON, verdict is one
   of the allowed values, no PII leaked into the response, reasoning length
   bounded).
7. The full record — redaction counts, both guardrail results, all three
   agents' outputs, and a generated audit id — is persisted via
   `Memory (Internal)` and is browsable from the frontend, not just
   returned once and discarded.

Domain: GDPR (EU) and CCPA (California) only — do not expand scope.

## Explicit non-goals
- No Linkup, no Tavily/Exa/Firecrawl, no live web search, no external search
  API of any kind, no MCP search server.
- No vector database / embeddings / RAG. The existing `my-first-pipeline.pipe`
  template (Webhook/Chat → Parser → embeddings → Elasticsearch) is NOT the
  base for this project — start a new pipeline file, don't extend it.
- No cron scheduling, no CI/CD gating, no webhooks to external systems.
- No exposure-scoring formula or weighted risk math — this is a
  compliance-checker demo, not a risk-quantification platform.
- No classifier training, no fine-tuning, no custom eval harness.
- Frontend stays a single static HTML/JS page. No build step, no framework.

## Architecture (target pipeline: `compliance-checker.pipe`)
Confirmed available node types (from the RocketRide "Add Node" palette —
use these exact node types, do not substitute, and do not invent node type
strings not present in this list):

- Source: `Webhook`
- Data: `Named Entity Recognition`
- Text: `Anonymize`
- Agent: `CrewAI Agent` (used for the Triage, Verdict, and Auditor agents)
- LLM provider: `OpenAI` (under the LLM category) — use `gpt-4o-mini`
- Guard: `Guardrails` (Experimental)
- Memory: `Memory (Internal)` — for the audit trail, no external DB
- Infrastructure: `Return Text` or `Return Answers`

Wiring, in order:

1. **`Webhook`** (Source) — accepts the free-text input (may contain raw
   PII — intentional, it's what makes the redaction step demoable).
2. **`Named Entity Recognition`** (Data) — extracts entities: person names,
   emails, phone numbers, locations, monetary amounts.
3. **`Anonymize`** (Text) — masks the entities found in step 2. Nothing
   downstream of this node should ever see raw PII again — treat that as a
   hard rule when wiring the graph.
4. **`OpenAI`** provider node — configure once with `gpt-4o-mini`; this is
   the shared model backing all three `CrewAI Agent` nodes below (check the
   schema for whether one provider node can feed multiple agent nodes, or
   whether each needs its own connection).
5. **`CrewAI Agent` — Triage Agent**: input = anonymized text from step 3.
   Role: extract structured fields. Output ONLY JSON:
   `{ practice, data_type, jurisdiction, regulation_guess, risk_level }`.
   `regulation_guess` must be one of the `id` values in `regulations.json`
   (pass the list of valid ids into the agent's prompt/backstory so it
   picks from a closed set instead of inventing one).
6. **`Guardrails`** (Guard) — validates step 5's output: JSON schema
   conforms, `regulation_guess` is in the allowed set, no PII patterns
   present. If `Guardrails` config proves too undocumented/fiddly to wire
   correctly with time remaining, fall back to a `Python` (Tool) node doing
   the same schema/allowlist validation in plain code and note the fallback
   in `PROJECT_DESCRIPTION.md` — judging cares about the validated-output
   *behavior*, not which node implements it.
7. **`CrewAI Agent` — Verdict Agent**: input = step 5's fields + the
   matching entry from `regulations.json` (looked up by `regulation_guess`
   — check whether RocketRide supports a static data/lookup node for this,
   or whether a small `Python` (Tool) node should do the lookup and hand
   off to the agent). Role: reason over the matched regulation and produce
   a verdict. Output ONLY JSON:
   `{ verdict, reasoning, cited_regulation, confidence }`, verdict must be
   exactly one of `compliant`, `non-compliant`, `needs_review`. Forbid
   citing anything outside the matched `regulations.json` entry.
8. **`CrewAI Agent` — Auditor Agent**: input = step 7's full output + the
   same matched `regulations.json` entry (fetched independently, not passed
   through from step 7, so this is a genuine second check rather than a
   rubber stamp). Role: confirm the cited regulation actually supports the
   stated verdict — e.g. catch a case where the Verdict Agent cited the
   right regulation but drew the wrong conclusion from it. Output:
   `{ audit_passed: boolean, audit_notes: string, final_verdict }` — where
   `final_verdict` is either step 7's verdict unchanged, or a corrected one
   if the Auditor disagrees (log the disagreement in `audit_notes` either
   way — a caught disagreement is a good demo moment, not a bug to hide).
9. **`Guardrails`** (Guard, second pass) — validates the final combined
   output: valid JSON, verdict in the allowed enum, reasoning under ~120
   words, and a simple regex/pattern check confirming no email/phone-shaped
   strings leaked into the response (defense in depth on top of step 3's
   masking).
10. **`Memory (Internal)`** — writes an audit record for this run: a
    generated `audit_id`, timestamp, entity types redacted (counts only,
    never raw values), `regulation_guess`/`cited_regulation`, both
    guardrail pass/fail results, the Verdict Agent's output, and the
    Auditor Agent's `audit_passed`/`audit_notes`/`final_verdict`. Check the
    schema for how `Memory (Internal)` is queried back out — this is
    required (not just nice-to-have) for the frontend history view below.
11. **`Return Text`** (Infrastructure) — sends the final verdict JSON back
    to the webhook caller, including `final_verdict`, `cited_regulation`,
    `audit_notes`, and the `audit_id` from step 10.

Before authoring the `.pipe` JSON: inspect `.rocketride/docs`,
`.rocketride/schema`, and `services-catalog.json` for exact required fields
per node type — especially `CrewAI Agent`, `Named Entity Recognition`,
`Anonymize`, `Guardrails`, and `Memory (Internal)`, since none of these were
used in the existing template. The existing `my-first-pipeline.pipe` is a
working example of correct JSON shape/wiring conventions; mirror its
structure even though the graph itself is different.

## Environment
- `OPENAI_API_KEY` — the only external API key this project needs. Use it
  for the `OpenAI` provider node, model `gpt-4o-mini`.
- No Linkup key, no Tavily/Exa/Firecrawl key — do not add any of these to
  `.env`.
- No other provider keys — do not sign up for or configure any other LLM
  provider, vector DB, or external service.

## Test scenarios
Six scenarios in `scenarios.json` (five regulation-description cases plus
one with obvious PII to demo the NER + Anonymize step). Run all six against
every build/deploy milestone below. Add more scenarios if time allows,
especially one deliberately ambiguous or malformed input to demonstrate the
Guardrails/Auditor layers actually catching something — a guardrail that has
never observably rejected anything is hard to demo convincingly.

## Frontend (single static HTML file, no framework)
- Textarea for free-text input + "Check Compliance" button
- "Try a sample" buttons pre-filling from `scenarios.json`
- Result card showing: final verdict (color-coded), reasoning, cited
  regulation, Auditor notes (especially visible if the Auditor corrected
  the Verdict Agent — that's a strong demo moment), and the audit id
- Original vs. redacted text shown side by side, to make PII masking visible
- **History view**: a simple list/table reading past runs back out of
  `Memory (Internal)` by audit id — "pull up any past compliance check" is
  the single most convincing piece of the audit-trail story, worth the
  extra build time now that there's room for it
- Calls the deployed RocketRide Cloud pipeline endpoint. Keep the endpoint
  URL as one obvious config variable at the top of the file.

## Build order
1. Read `.rocketride/schema` + `services-catalog.json` to confirm real
   config shape for `CrewAI Agent`, `Named Entity Recognition`, `Anonymize`,
   `Guardrails`, and `Memory (Internal)` (including how to query it back
   out for the history view).
2. Author `compliance-checker.pipe` with the 11-node graph above.
3. Run locally against all 6 scenarios in `scenarios.json`. Confirm PII is
   masked before the Triage Agent step, and deliberately construct one bad
   input to confirm Guardrails/Auditor actually catch something rather than
   passing everything through.
4. Build `index.html`, including the history view, verify end-to-end locally.
5. Deploy to RocketRide Cloud. Update frontend config to the cloud endpoint.
   Re-verify all 6 scenarios against the CLOUD deployment specifically.
6. If time remains: expand `regulations.json` with more entries per
   regulation for richer coverage — still free, it's just more curated text.
7. Fill in `PROJECT_DESCRIPTION.md` with the pipeline structure, the
   responsible-AI design decisions, why there are three agents instead of
   one, and a real captured example including a case where the Auditor
   caught or confirmed the Verdict Agent's reasoning.

## Definition of done
- [ ] `compliance-checker.pipe` deployed and reachable at a
      `cloud.rocketride.ai` URL
- [ ] All 6 scenarios produce sensible verdicts against the CLOUD endpoint
- [ ] PII in the input (name/email/phone) is verifiably masked before the
      Triage Agent step — demoable, not just claimed
- [ ] Guardrails (native node or Python fallback) actually rejects/catches
      at least one deliberately bad case in testing
- [ ] The Auditor Agent runs as a genuinely independent second check (not a
      passthrough) — verified by at least one test case where it flags or
      corrects the Verdict Agent
- [ ] Every verdict cites a specific entry from `regulations.json`, never an
      invented regulation
- [ ] Each run writes an audit record via `Memory (Internal)` with an
      `audit_id`, and that record is retrievable from the frontend history view
- [ ] The only external cost incurred anywhere in the pipeline is OpenAI
      `gpt-4o-mini` calls — confirm no other paid node/service crept in
- [ ] `index.html` works end-to-end against the cloud endpoint, including
      the history view
- [ ] `PROJECT_DESCRIPTION.md` filled in with a real captured example