#!/bin/bash
# Day 14: Manual recovery demonstration script
#
# This script demonstrates the kill/resume cycle using the real agent.
# It's designed to be run interactively so you can see each step.
#
# Usage: bash scripts/demo_recovery.sh

set -e

RUN_ID="demo_$(date +%Y%m%d_%H%M%S)"
QUERY="python engineer london"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  Day 14: Agent Recovery Demonstration                     ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Run ID: $RUN_ID"
echo "Query:  $QUERY"
echo ""

# ── Step 1: Start the agent ──
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 1: Starting agent (will process 5 jobs)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Press Ctrl+C after 1-2 jobs to simulate a crash."
echo "The agent will save its state before exiting."
echo ""
read -p "Press Enter to start..."

python -m src.job_agent.main "$QUERY" \
    --max-jobs 5 \
    --run-id "$RUN_ID" \
    --verbose || true

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 2: Agent interrupted. Checkpoint saved."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Step 2: Show interrupted runs ──
echo "Listing interrupted runs:"
echo ""
python -m src.job_agent.main --list-interrupted

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 3: Resume from checkpoint"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "The agent will resume from where it left off."
echo "Already-processed jobs will be skipped."
echo ""
read -p "Press Enter to resume..."

python -m src.job_agent.main "$QUERY" \
    --resume \
    --run-id "$RUN_ID" \
    --verbose

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 4: Show recovery trace"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Audit trail shows the full recovery narrative:"
echo ""
python -m src.job_agent.view_trace --run-id "$RUN_ID" --narrative

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║  ✅ Recovery demonstration complete                        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Files generated:"
echo "  - checkpoints/checkpoint_$RUN_ID.jsonl"
echo "  - traces/trace_*.jsonl"
echo "  - reports/report_*.md"
echo ""