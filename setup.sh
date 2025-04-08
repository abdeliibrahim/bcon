#!/bin/bash
# Setup script for Business Contact & Outreach Network (BCON)

echo "Setting up Business Contact & Outreach Network (BCON)..."

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

echo "Setup complete! You can now run the application."
echo "To start the web interface, run: python app.py"
echo "To use the command-line interface, run: python email_finder.py <first_name> <last_name> <company>"
