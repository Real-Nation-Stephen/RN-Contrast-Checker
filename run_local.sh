#!/bin/bash

# Local Run Script for RN Contrast Checker
# This script helps you run the app locally

echo "🚀 Starting RN Contrast Checker locally..."
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "📥 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Check if .streamlit directory exists
if [ ! -d ".streamlit" ]; then
    echo "📁 Creating .streamlit directory..."
    mkdir -p .streamlit
fi

# Check if secrets.toml exists
if [ ! -f ".streamlit/secrets.toml" ]; then
    echo "⚠️  Warning: .streamlit/secrets.toml not found!"
    echo "   For full functionality, you'll need to set up Google Sheets authentication."
    echo "   You can still run the app, but some features may not work."
    echo ""
    echo "   To set up secrets.toml, copy your Google Service Account credentials."
    echo "   See README.md for instructions."
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Run Streamlit with authentication disabled for local development
echo ""
echo "✅ Starting Streamlit app (authentication disabled for local testing)..."
echo "   The app will open in your browser automatically."
echo "   Press Ctrl+C to stop the server."
echo ""
STREAMLIT_SKIP_AUTH=true streamlit run rn_contrast_checker_app.py

