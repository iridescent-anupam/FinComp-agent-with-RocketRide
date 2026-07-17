# FinComp Check

A multi-agent compliance pipeline built on the RocketRide AI orchestration stack.

## What it does
Given raw data practice descriptions or customer privacy complaints, this tool runs a pipeline that:
1. **Redacts PII**: Sanitizes names, emails, phones, and addresses locally using NER.
2. **Retrieves Regulations**: Dynamically matches relevant articles from GDPR & CCPA (RAG).
3. **Decides Compliance**: LLM evaluates compliance status (compliant, non-compliant, or needs_review).
4. **Independent Audit**: Critique agent reviews reasoning to confirm correctness and eliminate hallucinations.

## Why it is useful
- **Automated Data Protection**: Automatically enforces privacy rules on unstructured texts, preventing manual audit bottlenecks.
- **Responsible AI Guardrails**: Injects prompt-safety and format checks to guarantee reliable JSON outputs.
- **Visual Diagnostics**: Real-time pipeline tracker shows exact source citations and redacted views.

## Who it is for
- **Data Privacy Teams & Compliance Officers**: Instantly audit compliance practices against GDPR/CCPA.
- **Security Engineers**: Sanitize and protect sensitive data before sharing it with external LLMs.
- **AI Developers**: Build and deploy reliable, critique-audited reasoning agents.

<img width="800" height="697" alt="gif-1" src="https://github.com/user-attachments/assets/3ed2f07f-c506-416a-8bc8-45fc90a0d515" />
