#!/bin/bash
# Run the orientation viewer using the local Python venv
cd "$(dirname "$0")"

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
    echo "Installing dependencies..."
    .venv/bin/pip install -r requirements.txt
fi

# Activate and run
source .venv/bin/activate
python server.py "$@"
