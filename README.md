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

## Prerequisites & Requirements
Before setting up and running FinComp Check, ensure you have:

- **Python**: Python 3.10 or higher
- **Node.js / npm** *(optional)*: If extending frontend tooling
- **RocketRide Engine**: Installed and accessible locally or remotely
- **OpenAI API Key**: OpenAI API key with access to GPT-4o / GPT-4o-mini models (required for LLM reasoning & auditor critique stages)

## Setup & Quickstart

### 1. Clone & Set Up Virtual Environment
```bash
git clone <repository-url>
cd FinComp-agent-with-RocketRide
python3 -m venv .venv
source .venv/bin/python3
pip install -r requirements.txt # or install rocketride SDK
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory:
```env
ROCKETRIDE_URI=http://127.0.0.1:51234
ROCKETRIDE_APIKEY=your_rocketride_api_key
ROCKETRIDE_OPENAI_KEY=your_openai_api_key
```

### 3. Start RocketRide Local Engine
Start your RocketRide engine background process (or ensure your engine daemon is listening on the configured port).

### 4. Run Dev Bridge Server & Web UI
```bash
python3 server.py
```
Open **`http://localhost:8000`** in your browser to access the interactive dashboard.

<img width="800" height="697" alt="gif-1" src="https://github.com/user-attachments/assets/3ed2f07f-c506-416a-8bc8-45fc90a0d515" />
