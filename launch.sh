#!/bin/bash
# Launch script for readMarkable on Linux/macOS

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to resources directory
cd "$SCRIPT_DIR/resources"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    echo "Please install Python 3 to continue"
    exit 1
fi

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install requirements if needed
if [ -f "requirements.txt" ]; then
    echo "Checking dependencies..."
    pip install -q -r requirements.txt 2>/dev/null || {
        echo "Installing required packages..."
        pip install -r requirements.txt
    }
fi

# Launch the application
echo "Starting readMarkable..."
python main.py

# Deactivate virtual environment when done
deactivate