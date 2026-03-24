#!/bin/bash
# Website Opportunity Engine — Start Script
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Start server
echo ""
echo "🚀 Starting Website Opportunity Engine..."
echo "   → Open http://localhost:8000 in your browser"
echo ""
python -m uvicorn src.dashboard:app --reload --host 0.0.0.0 --port 8000
