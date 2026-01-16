# Running RN Contrast Checker Locally

## Quick Start (Today)

### Option 1: Using the Run Script (Easiest)

**On Mac/Linux:**
```bash
./run_local.sh
```

**On Windows:**
```bash
run_local.bat
```

The script will:
- Create a virtual environment (if needed)
- Install all dependencies
- Start the Streamlit app
- Open it in your browser automatically

### Option 2: Manual Setup

1. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the app:**
   ```bash
   streamlit run rn_contrast_checker_app.py
   ```

The app will open at `http://localhost:8501`

## Authentication Setup (Optional for Local Use)

If you want to use the authentication features locally:

1. Create a `.streamlit` directory in the project root
2. Create a `.streamlit/secrets.toml` file with your Google Service Account credentials:
   ```toml
   private_key_id = "your_private_key_id"
   private_key = """-----BEGIN PRIVATE KEY-----
   your_private_key_content
   -----END PRIVATE KEY-----"""
   client_id = "your_client_id"
   project_id = "your_project_id"
   client_email = "your_service_account_email"
   ```

**Note:** You can still run the app without authentication setup, but you'll need to modify the code to skip authentication checks for local testing.

## Memory Management Features

The app now includes memory management features:

1. **Automatic Cleanup**: Old analysis data is automatically cleared when you upload a new file
2. **Google Sheets Storage**: Toggle in the sidebar to save results to Google Sheets instead of keeping in memory
3. **Manual Clear Button**: Use the "Clear All Analysis Data" button in the sidebar to free memory manually

## Troubleshooting

### Port Already in Use
If port 8501 is already in use:
```bash
streamlit run rn_contrast_checker_app.py --server.port 8502
```

### Missing Dependencies
Make sure you've activated your virtual environment and installed all requirements:
```bash
pip install -r requirements.txt
```

### Authentication Errors
If you see authentication errors but don't need that feature locally, you can temporarily comment out the authentication check in the code (around line 433).

## Differences from Streamlit Cloud

- **No memory limits**: Your local machine's memory is the limit
- **Faster processing**: No network latency
- **Full control**: You can modify code and see changes immediately
- **Offline capable**: Works without internet (except for Google Sheets features)

