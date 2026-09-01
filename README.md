# Job Hunter Agent

An observable agentic workflow for automated job research, CV matching, and tailored application drafting.

## 🎯 Week 1 Goal
By Day 7, this agent will:
- Search for relevant jobs using the FreeHire API.
- Research company context using web search.
- Compare job descriptions against a candidate's CV.
- Produce a consolidated Markdown report containing match reasoning, tailored CV highlights, and cover letter drafts.
- Expose every decision, tool call, and error through a strict audit trail.

## 📦 Output Strategy
To keep the prototype lean and focused, the agent currently generates a **single consolidated Markdown report** (e.g., `output/job_research_report.md`). This allows us to easily review the LLM's reasoning, match logic, and generated drafts in one place.

## ⚙️ Setup & OpenAI API Guide

### Step 1: Provision your OpenAI API Key
This project uses OpenAI for LLM reasoning and structured output.
1. Go to [platform.openai.com](https://platform.openai.com/) and sign in (or create an account).
2. **Add a Payment Method:** Navigate to **Settings > Billing**. You must add a valid payment method and purchase a minimum of $5 in credits to use the API.
3. **Set a Hard Monthly Limit (Crucial for Agents!):** While in the Billing section, set a "Soft Limit" and "Hard Limit" (e.g., $10.00). Agentic loops can occasionally get stuck in retry cycles and burn through credits. This is your financial guardrail.
4. **Create the API Key:** Navigate to **API Keys** and click "Create new secret key". Name it `job-hunter-dev`. Copy it immediately (you won't see it again).

### Step 2: Project Installation
```bash
# Clone or create the project directory
cd job-hunter-agent

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate

# Install dependencies
pip install -e .