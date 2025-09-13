#!/bin/bash
# Launch script for readmarkable on macOS

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "$0" )" && pwd )"

# Change to resources directory
cd "$SCRIPT_DIR/resources"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    echo "Please install Python 3 from https://www.python.org/downloads/"
    echo "Or install via Homebrew: brew install python3"
    read -p "Press any key to exit..."
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
echo "Starting readmarkable..."
python main.py

# Deactivate virtual environment when done
deactivate

# Keep terminal open
echo ""
echo "Application closed."
read -p "Press any key to exit..."