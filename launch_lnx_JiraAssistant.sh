#!/bin/bash
# One-click launcher for Mac/Linux
set -e

echo "🔷 Jira Assistant — Local Launcher"
echo "─────────────────────────────────"

# Check Python
if ! command -v python3 &> /dev/null; then
  echo "❌ Python 3 not found. Install from https://python.org"
  exit 1
fi

# Create venv if not already present
if [ ! -d ".venv" ]; then
  echo "📦 Creating virtual environment..."
  python3 -m venv .venv
fi

# Activate
source .venv/bin/activate

# Install deps
echo "📦 Installing dependencies..."
pip install -q -r requirements.txt

# Launch
echo ""
echo "✅ Starting Jira Assistant at http://localhost:8501"
echo "   Press Ctrl+C to stop."
echo ""
streamlit run JiraAssistant.py --server.port 8501
