"""
RN Contrast Checker - A Streamlit application for analyzing PDF documents for color contrast accessibility.

This application helps ensure documents meet WCAG 2.1 guidelines by:
- Analyzing text and background colors in PDFs
- Calculating contrast ratios
- Generating visual heatmaps
- Producing detailed accessibility reports

Author: Stephen
Version: 1.0.0
"""

import io
import os
import hashlib
import base64
import fitz  # PyMuPDF
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from fpdf import FPDF
from datetime import datetime
import re
import csv
from io import StringIO
from collections import defaultdict
import subprocess
import tempfile
import pandas as pd  # For colour-pair summarisation tables
import numpy as np
from scipy.spatial.distance import cdist
import xlsxwriter

# Feature toggle: stroke-to-fill preprocessing via mutool. Disable by default.
ENABLE_STROKE_OUTLINE = False

# =====================================================================================
# AUTHENTICATION SYSTEM
# =====================================================================================

def load_users_from_sheet():
    """Load users from Google Sheets with better error handling"""
    
    try:
        # Check if we have the required secrets (try both locations)
        service_account = getattr(st.secrets, 'service_account', None)
        if service_account or (hasattr(st, 'secrets') and st.secrets.get("private_key_id")):
            
            # Use service_account section if available, otherwise root level
            if service_account:
                private_key_id = service_account.get("private_key_id", "")
                private_key = service_account.get("private_key", "")
                client_id = service_account.get("client_id", "")
            else:
                private_key_id = st.secrets.get("private_key_id", "")
                private_key = st.secrets.get("private_key", "")
                client_id = st.secrets.get("client_id", "")
            
            # Check if we have valid credentials
            if (private_key_id and private_key and client_id and
                "your_private_key_id_here" not in str(private_key_id)):
                
                import gspread
                from google.oauth2.service_account import Credentials
                
                # Define the scope
                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                
                # Service account credentials
                credentials_info = {
                    "type": "service_account",
                    "project_id": "rn-copy-checker-app",
                    "private_key_id": private_key_id,
                    "private_key": private_key.replace('\\n', '\n'),
                    "client_email": "rn-copy-checker@rn-copy-checker-app.iam.gserviceaccount.com",
                    "client_id": client_id,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/rn-copy-checker%40rn-copy-checker-app.iam.gserviceaccount.com"
                }
                
                # Create credentials
                credentials = Credentials.from_service_account_info(credentials_info, scopes=scope)
                
                # Authorize the client
                client = gspread.authorize(credentials)
                
                # Open the Google Sheet
                sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1nLOJvUut6RgfYbsSQa1ghPnJMaUWdHbbvlWqSDwwmU4/edit?usp=sharing")
                worksheet = sheet.get_worksheet(0)  # Get first worksheet
                
                # Get all records
                records = worksheet.get_all_records()
                
                # Convert to dictionary with name as key
                users = {}
                for record in records:
                    if record.get('Name') and record.get('Password'):
                        # Try different possible column names for the image URL
                        image_url = (record.get('Profile Image', '') or 
                                   record.get('Image', '') or 
                                   record.get('Photo', '') or 
                                   record.get('Picture', '') or
                                   record.get('Image URL', '') or '')
                        
                        users[record['Name']] = {
                            'email': record.get('Email', ''),
                            'password': record.get('Password', ''),
                            'image_url': image_url.strip() if image_url else ''
                        }
                
                if users:
                    return users
        
    except Exception as e:
        # Show warning in the UI only during login attempts
        if 'authenticated' not in st.session_state or not st.session_state.authenticated:
            st.warning(f"⚠️ Google Sheets connection failed: {str(e)[:100]}... Using offline user list.")
    
    # Fallback to hardcoded users
    return {
        "Stephen Maguire": {"email": "stephen.maguire@realnation.ie", "password": "RealSpark2025", "image_url": ""},
        "Kay McKeon": {"email": "kay.mckeon@realnation.ie", "password": "RealNest2025", "image_url": ""},
        "Gráinne O'Sullivan": {"email": "grainne.osullivan@realnation.ie", "password": "RealBolt2025", "image_url": ""},
        "Dan Vaughan": {"email": "dan.vaughan@realnation.ie", "password": "RealPath2025", "image_url": ""},
        "Craig Thiel": {"email": "craig.thiel@realnation.ie", "password": "RealGrid2025", "image_url": ""},
        "Design freelancer 3": {"email": "designfreelancer3@realnation.ie", "password": "RealCore2025", "image_url": ""},
        "Design freelancer 2": {"email": "designfreelancer2@realnation.ie", "password": "RealLink2025", "image_url": ""},
        "Design freelancer 1": {"email": "designfreelancer1@realnation.ie", "password": "RealDrift2025", "image_url": ""},
        "Gwen Robinson": {"email": "gwen.robinson@realnation.ie", "password": "RealWeb2025", "image_url": ""}
    }

def convert_google_drive_url(url):
    """Convert Google Drive sharing URLs to direct image URLs"""
    if not url or not url.strip():
        return ""
    
    # Handle different Google Drive URL formats
    if "drive.google.com" in url:
        # Extract file ID from various Google Drive URL formats
        import re
        
        # Pattern for /file/d/{file_id}/view or similar
        match = re.search(r'/file/d/([a-zA-Z0-9-_]+)', url)
        if match:
            file_id = match.group(1)
            # Try the thumbnail format which sometimes works better for embedding
            return f"https://drive.google.com/thumbnail?id={file_id}&sz=w400-h400"
            
        # Pattern for id={file_id}
        match = re.search(r'id=([a-zA-Z0-9-_]+)', url)
        if match:
            file_id = match.group(1)
            return f"https://drive.google.com/thumbnail?id={file_id}&sz=w400-h400"
    
    # Return original URL if it's not a Google Drive URL
    return url

def get_user_initials(name):
    """Get user initials from full name"""
    if not name:
        return "👤"
    
    words = name.strip().split()
    if len(words) >= 2:
        return f"{words[0][0]}{words[-1][0]}".upper()
    elif len(words) == 1:
        return words[0][:2].upper()
    else:
        return "👤"

def get_user_color(name):
    """Generate a consistent color for each user based on their name"""
    if not name:
        return "#667eea", "#764ba2"
    
    # Generate colors based on name hash for consistency
    import hashlib
    hash_val = int(hashlib.md5(name.encode()).hexdigest()[:6], 16)
    
    # Define pleasant color pairs
    color_pairs = [
        ("#667eea", "#764ba2"),  # Purple-blue
        ("#f093fb", "#f5576c"),  # Pink-red
        ("#4facfe", "#00f2fe"),  # Blue-cyan
        ("#43e97b", "#38f9d7"),  # Green-teal
        ("#fa709a", "#fee140"),  # Pink-yellow
        ("#a8edea", "#fed6e3"),  # Teal-pink
        ("#ffecd2", "#fcb69f"),  # Peach-orange
        ("#ff9a9e", "#fecfef"),  # Rose-purple
        ("#667eea", "#764ba2"),  # Default purple-blue
    ]
    
    return color_pairs[hash_val % len(color_pairs)]

def display_profile_image(image_url, size=100, caption=None, user_name=""):
    """Safely display a profile image with personalized fallback"""
    if image_url and image_url.strip():
        # Convert Google Drive URLs to direct image URLs
        converted_url = convert_google_drive_url(image_url)
        
        try:
            # Wrap st.image in a centered container
            st.markdown('<div style="display: flex; justify-content: center;">', unsafe_allow_html=True)
            st.image(converted_url, width=size, caption=caption)  
            st.markdown('</div>', unsafe_allow_html=True)
            return True
        except Exception:
            # If image fails to load, show personalized avatar
            pass
    
    # Create personalized avatar with initials
    initials = get_user_initials(user_name)
    color1, color2 = get_user_color(user_name)
    font_size = max(12, size // 4)
    
    st.markdown(f"""
        <div style="display: flex; justify-content: center;">
            <div style="width: {size}px; height: {size}px; background: linear-gradient(45deg, {color1} 0%, {color2} 100%); 
            border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; 
            font-size: {font_size}px; font-weight: bold; margin: 10px auto; box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-align: center;">
                {initials}
            </div>
        </div>
    """, unsafe_allow_html=True)
    return False

def show_login():
    """Display clean horizontal 3-column login form"""
    users = load_users_from_sheet()

    if not users:
        st.error("Unable to load user data. Please contact support.")
        return False

    # Get the current selection (use session state for persistence)
    if 'selected_user' not in st.session_state:
        st.session_state.selected_user = list(users.keys())[0]
    
    selected_user = st.session_state.selected_user

    # Custom CSS for sign-in button
    st.markdown("""
    <style>
    .stButton > button[kind="primary"] {
        background-color: #2b1e66 !important;
        border-color: #2b1e66 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #1e1547 !important;
        border-color: #1e1547 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<br><br><br>", unsafe_allow_html=True)  # More top spacing

    # Container to constrain width (20% tighter than before)
    outer_col1, main_container, outer_col3 = st.columns([2, 4, 2])
    
    with main_container:
        # TOP PANEL - 3 columns with dividers (no headings needed)
        col1, div1, col2, div2, col3 = st.columns([1, 0.1, 2, 0.1, 1])
        
        # Column 1: Profile Image
        with col1:
            if selected_user in users:
                user_image_url = users[selected_user].get('image_url', '')
                display_profile_image(user_image_url, size=100, user_name=selected_user)
        
        # Divider 1
        with div1:
            st.markdown('<div style="width: 1px; height: 120px; background-color: #ddd; margin: 0 auto;"></div>', unsafe_allow_html=True)
        
        # Column 2: App Title
        with col2:
            st.markdown("### RN Contrast Checker")
            st.caption("Welcome back! Please sign in to continue.")
        
        # Divider 2  
        with div2:
            st.markdown('<div style="width: 1px; height: 120px; background-color: #ddd; margin: 0 auto;"></div>', unsafe_allow_html=True)
        
        # Column 3: Account Info
        with col3:
            if selected_user in users:
                st.markdown(f"**{selected_user}**")
                st.caption(f"📧 {users[selected_user].get('email', 'No email')}")
    
        st.markdown("<br>", unsafe_allow_html=True)
        
        # MIDDLE PANEL - User Selection
        st.markdown("---")
        st.markdown("#### 👤 Select User")
        new_selection = st.selectbox(
            "Choose your name:",
            options=list(users.keys()),
            index=list(users.keys()).index(selected_user),
            key="user_dropdown",
            label_visibility="collapsed"
        )
        
        # Update session state when selection changes
        if new_selection != st.session_state.selected_user:
            st.session_state.selected_user = new_selection
            st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # BOTTOM PANEL - Password Entry
        st.markdown("---")
        with st.form("login_form"):
            st.markdown("#### 🔒 Enter Password")
            password = st.text_input(
                "Password:", 
                type="password", 
                placeholder="Enter your password...",
                label_visibility="collapsed"
            )
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            login_button = st.form_submit_button(
                "🚀 Sign In", 
                type="primary", 
                width='stretch'
            )
            
            if login_button:
                current_user = st.session_state.get('selected_user', list(users.keys())[0])
                if current_user in users and password == users[current_user]['password']:
                    st.session_state.authenticated = True
                    st.session_state.current_user = current_user
                    st.session_state.user_email = users[current_user]['email']
                    st.session_state.user_image = users[current_user].get('image_url', '')
                    st.success(f"🎉 Welcome back, {current_user}!")
                    st.rerun()
                else:
                    st.error("❌ Invalid credentials. Please try again.")
        
        # Footer
        st.markdown("""
        <div style="text-align: center; margin-top: 2rem; color: #888; font-size: 0.9rem;">
            Need help? Contact your administrator.
        </div>
        """, unsafe_allow_html=True)
    
    return False

def check_authentication():
    """Check if user is authenticated"""
    # Skip authentication when running locally
    import os
    is_local = os.getenv('STREAMLIT_SKIP_AUTH', '').lower() == 'true'
    
    # Also check if we're likely running locally (no secrets or localhost)
    if not is_local:
        try:
            # Try to detect if we're on Streamlit Cloud (has specific config)
            # If secrets don't exist or we're clearly local, skip auth
            if not hasattr(st, 'secrets') or not st.secrets:
                is_local = True
            # Check if running via localhost (common local setup)
            import socket
            hostname = socket.gethostname()
            if 'localhost' in hostname.lower() or hostname.startswith('127.'):
                is_local = True
        except:
            # If we can't determine, assume local for safety
            is_local = True
    
    if is_local:
        # Auto-authenticate for local development
        if 'authenticated' not in st.session_state or not st.session_state.authenticated:
            st.session_state.authenticated = True
            st.session_state.current_user = "Local Developer"
            st.session_state.user_email = "local@localhost"
            st.session_state.user_image = ""
        return True
    
    # Normal authentication check for production
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        show_login()
        return False
    
    return True

def show_logout_button():
    """Show clean, modern profile sidebar"""
    with st.sidebar:
        st.markdown("---")
        
        # Profile image centered
        user_image = st.session_state.get('user_image', '')
        current_user = st.session_state.get('current_user', '')
        
        # Center the profile image
        profile_col1, profile_col2, profile_col3 = st.columns([1, 1, 1])
        with profile_col2:
            display_profile_image(user_image, size=80, user_name=current_user)
        
        # User details centered with grey pills
        st.markdown(f"""
        <div style="text-align: center; margin: 1rem 0;">
            <div style="background-color: white; border-radius: 15px; padding: 0.3rem 0.8rem; margin: 0.3rem auto; display: inline-block; color: #333; font-weight: 500; font-size: 0.9rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                {st.session_state.get('current_user', 'Unknown')}
            </div>
            <br>
            <div style="background-color: white; border-radius: 15px; padding: 0.3rem 0.8rem; margin: 0.3rem auto; display: inline-block; color: #666; font-size: 0.8rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                📧 {st.session_state.get('user_email', 'Unknown')}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("🚪 Logout", type="secondary", use_container_width=True):
            # Clear authentication
            st.session_state.authenticated = False
            if 'current_user' in st.session_state:
                del st.session_state.current_user
            if 'user_email' in st.session_state:
                del st.session_state.user_email
            if 'user_image' in st.session_state:
                del st.session_state.user_image
            st.rerun()
        
        st.markdown("---")

# =====================================================================================
# END AUTHENTICATION SYSTEM
# =====================================================================================

# =====================================================================================
# MEMORY MANAGEMENT FUNCTIONS
# =====================================================================================

def clear_analysis_data():
    """Clear all analysis-related data from session state to free memory"""
    data_keys = [
        'contrast_results',
        'pdf_results', 
        'text_blocks_by_page',
        'contrast_df',
        'current_file_hash',
        'results_in_sheets',
        'results_sheet_hash'
    ]
    for key in data_keys:
        if key in st.session_state:
            del st.session_state[key]
    # Force garbage collection multiple times to ensure cleanup
    import gc
    gc.collect()
    gc.collect()  # Second pass for cyclic references

def save_results_to_sheets(contrast_results, pdf_results, file_hash, user_email=None):
    """Optionally save results to Google Sheets instead of keeping in memory"""
    try:
        service_account = getattr(st.secrets, 'service_account', None)
        if not service_account and not hasattr(st, 'secrets'):
            return False
        
        if service_account:
            private_key_id = service_account.get("private_key_id", "")
            private_key = service_account.get("private_key", "")
        else:
            private_key_id = st.secrets.get("private_key_id", "")
            private_key = st.secrets.get("private_key", "")
        
        if not private_key_id or "your_private_key_id_here" in str(private_key_id):
            return False
        
        import gspread
        from google.oauth2.service_account import Credentials
        from gspread.exceptions import APIError
        
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        credentials_info = {
            "type": "service_account",
            "project_id": "rn-copy-checker-app",
            "private_key_id": private_key_id,
            "private_key": private_key.replace('\\n', '\n'),
            "client_email": "rn-copy-checker@rn-copy-checker-app.iam.gserviceaccount.com",
            "client_id": st.secrets.get("client_id", ""),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/rn-copy-checker%40rn-copy-checker-app.iam.gserviceaccount.com"
        }
        
        credentials = Credentials.from_service_account_info(credentials_info, scopes=scope)
        client = gspread.authorize(credentials)
        
        # Try to open results sheet (create if doesn't exist)
        try:
            sheet = client.open("RN_Contrast_Checker_Results")
        except APIError as e:
            # Check if it's a quota error
            if '403' in str(e) and ('quota' in str(e).lower() or 'storage' in str(e).lower()):
                # Disable Google Sheets storage option permanently for this session
                st.session_state['use_sheets_storage'] = False
                st.session_state['sheets_quota_exceeded'] = True
                st.error("⚠️ Google Drive storage quota exceeded. Google Sheets archiving has been disabled. Results will be stored in memory only. Please free up Google Drive space or upgrade your storage plan.")
                return False
            # Try to create if it doesn't exist (but this might also fail with quota)
            try:
                sheet = client.create("RN_Contrast_Checker_Results")
                sheet.share("", perm_type='anyone', role='writer')
            except APIError as create_error:
                if '403' in str(create_error) and ('quota' in str(create_error).lower() or 'storage' in str(create_error).lower()):
                    st.session_state['use_sheets_storage'] = False
                    st.session_state['sheets_quota_exceeded'] = True
                    st.error("⚠️ Google Drive storage quota exceeded. Google Sheets archiving has been disabled.")
                    return False
                raise
        except Exception as e:
            # Other errors - just return False without disabling
            return False
        
        worksheet_name = f"Results_{file_hash[:8]}"
        try:
            worksheet = sheet.worksheet(worksheet_name)
            worksheet.clear()
        except:
            try:
                worksheet = sheet.add_worksheet(title=worksheet_name, rows=1000, cols=20)
            except APIError as e:
                if '403' in str(e) and ('quota' in str(e).lower() or 'storage' in str(e).lower()):
                    st.session_state['use_sheets_storage'] = False
                    st.session_state['sheets_quota_exceeded'] = True
                    st.error("⚠️ Google Drive storage quota exceeded. Google Sheets archiving has been disabled.")
                    return False
                raise
        
        # Flatten and save results
        flat_results = _flatten_results(contrast_results)
        if flat_results:
            df = pd.DataFrame(flat_results)
            try:
                worksheet.update([df.columns.values.tolist()] + df.values.tolist())
            except APIError as e:
                if '403' in str(e) and ('quota' in str(e).lower() or 'storage' in str(e).lower()):
                    st.session_state['use_sheets_storage'] = False
                    st.session_state['sheets_quota_exceeded'] = True
                    st.error("⚠️ Google Drive storage quota exceeded. Google Sheets archiving has been disabled.")
                    return False
                raise
        
        return True
    except Exception as e:
        # Check if it's a quota error
        error_str = str(e).lower()
        if '403' in str(e) and ('quota' in error_str or 'storage' in error_str):
            st.session_state['use_sheets_storage'] = False
            st.session_state['sheets_quota_exceeded'] = True
            st.error("⚠️ Google Drive storage quota exceeded. Google Sheets archiving has been disabled. Results will be stored in memory only.")
        else:
            # Other errors - show warning but don't disable
            st.warning(f"Could not save to Google Sheets: {str(e)[:100]}")
        return False

# Initialize session state variables
SESSION_STATE_VARS = {
    'contrast_results': None,
    'pdf_results': None,
    'text_blocks_by_page': None,
    'current_file_hash': None,
    'use_sheets_storage': False  # Toggle for Google Sheets storage
}

# Initialize all session state variables at once
for var, default_value in SESSION_STATE_VARS.items():
    if var not in st.session_state:
        st.session_state[var] = default_value

# Set up the Streamlit page
st.set_page_config(
    page_title="RN Contrast Checker",
    page_icon="assets/Contrast Checker Icon.png",
    layout="wide"
)

# =====================================================================================
# AUTHENTICATION CHECK - Protect the entire app
# =====================================================================================

if not check_authentication():
    st.stop()  # Stop execution if not authenticated

# Show logout button in sidebar (skip on local)
import os
is_local = os.getenv('STREAMLIT_SKIP_AUTH', '').lower() == 'true'
if not is_local:
    try:
        if not hasattr(st, 'secrets') or not st.secrets:
            is_local = True
    except:
        is_local = True

if not is_local:
    show_logout_button()

# =====================================================================================
# MAIN APPLICATION (Only accessible after authentication)
# =====================================================================================

# Add title and description
st.title("RN Contrast Checker")
st.markdown("""
This tool analyzes PDF documents for color contrast accessibility according to WCAG 2.1 guidelines.
Upload a PDF to check if the text meets contrast requirements for readability.
""")

# Add memory management options in sidebar
with st.sidebar:
    st.markdown("### ⚙️ Memory Settings")
    
    # Check if quota was exceeded
    quota_exceeded = st.session_state.get('sheets_quota_exceeded', False)
    if quota_exceeded:
        st.error("⚠️ Google Sheets storage unavailable (quota exceeded)")
        st.info("💡 Results will be stored in memory. Use 'Clear All Analysis Data' to free memory.")
        use_sheets_storage = False
        st.session_state['use_sheets_storage'] = False
    else:
        use_sheets_storage = st.checkbox(
            "💾 Use Google Sheets for data storage (reduces memory usage)",
            value=st.session_state.get('use_sheets_storage', False),
            help="When enabled, analysis results are saved to Google Sheets instead of keeping in memory. This helps prevent memory issues on Streamlit Cloud."
        )
        st.session_state['use_sheets_storage'] = use_sheets_storage
    
    if st.button("🗑️ Clear All Analysis Data", help="Manually clear cached analysis data to free memory"):
        clear_analysis_data()
        st.success("Analysis data cleared!")
        st.rerun()

# Add file uploader
uploaded_file = st.file_uploader("Upload PDF file", type="pdf", label_visibility="collapsed")

# Add options
show_heatmap = st.checkbox("Show contrast heatmap overlay", value=True)

# Global padding style
st.markdown("""
    <style>
        .main .block-container {
            padding-right: 5rem;
        }
    </style>
""", unsafe_allow_html=True)

# Add sidebar with logo and style selection
st.sidebar.markdown("""
    <style>
        /* Container for the logo */
        .sidebar-logo {
            position: fixed;
            bottom: 0;
            padding: 2rem 0.5rem 2rem 0.5rem;
            z-index: 1000;
            width: calc(100% - 1rem);
        }
        
        /* Logo image styling */
        .sidebar-logo img {
            width: calc(100% - 1rem);
            max-width: 200px;
            height: auto;
            display: block;
        }

        /* Theme-aware logo display for Studio Mode */
        @media (prefers-color-scheme: light) {
            .studio-mode-logo.light { display: block; }
            .studio-mode-logo.dark { display: none; }
        }
        @media (prefers-color-scheme: dark) {
            .studio-mode-logo.light { display: none; }
            .studio-mode-logo.dark { display: block; }
        }
    </style>
""", unsafe_allow_html=True)

# Logo handling - always use Studio Mode
logo_sparkle_path = "assets/Logo Sparkle.png"
logo_studio_path = "assets/Logo Studio.png"

with open(logo_sparkle_path, "rb") as f:
    logo_sparkle_base64 = base64.b64encode(f.read()).decode()

with open(logo_studio_path, "rb") as f:
    logo_studio_base64 = base64.b64encode(f.read()).decode()

# Always display Studio Mode logo with theme-aware switching
st.sidebar.markdown(f"""
    <div class="sidebar-logo">
        <img src="data:image/png;base64,{logo_studio_base64}" class="studio-mode-logo light">
        <img src="data:image/png;base64,{logo_sparkle_base64}" class="studio-mode-logo dark">
    </div>
""", unsafe_allow_html=True)

def clean_text_for_pdf(text):
    """Clean text for PDF output by replacing Unicode characters with ASCII equivalents"""
    if text is None:
        return ''
    
    # Convert to string first
    text = str(text)
    
    replacements = {
        '\u2013': '-',    # en dash
        '\u2014': '-',    # em dash
        '\u2018': "'",    # left single quote
        '\u2019': "'",    # right single quote
        '\u201c': '"',    # left double quote
        '\u201d': '"',    # right double quote
        '\u00a0': ' ',    # non-breaking space
        '\u200b': '',     # zero-width space
        '\u2026': '...',  # ellipsis
        '\u2122': '(TM)', # trademark
        '\u00ae': '(R)',  # registered trademark
        '\u00b0': 'deg',  # degree
        '\u20ac': 'EUR',  # euro
        '\u00a3': 'GBP',  # pound
        '\u00a5': 'JPY',  # yen
        '\u00a9': '(C)',  # copyright
        '\u00e9': 'e',    # e with acute
        '\u00e8': 'e',    # e with grave
        '\u00ea': 'e',    # e with circumflex
        '\u00eb': 'e',    # e with diaeresis
        '\u00e0': 'a',    # a with grave
        '\u00e1': 'a',    # a with acute
        '\u00e2': 'a',    # a with circumflex
        '\u00e4': 'a',    # a with diaeresis
        '\u00fc': 'u',    # u with diaeresis
        '\u00f1': 'n',    # n with tilde
        '\u00e7': 'c',    # c with cedilla
    }
    
    # Apply replacements and filter out non-ASCII characters
    result = ''
    for c in text:
        if c in replacements:
            result += replacements[c]
        elif ord(c) < 128:  # Standard ASCII
            result += c
        else:
            # Replace any remaining Unicode characters with underscore
            result += '_'
    
    return result

# -------------------------------------------------------------
# Color detection helpers
# -------------------------------------------------------------

# Utility helpers for bbox handling
def _rect_from(b):
    """Return a normalized fitz.Rect from a tuple/list/Rect"""
    import fitz
    if isinstance(b, fitz.Rect):
        return fitz.Rect(b)
    return fitz.Rect(*b)


def _rect_area(r):
    """Area of a rectangle (0 if degenerate)"""
    return max(0, (r.x1 - r.x0) * (r.y1 - r.y0))


def _rect_contains(outer, inner, margin=0):
    """Does outer fully contain inner (with optional margin)?"""
    return (
        inner.x0 >= outer.x0 - margin and
        inner.y0 >= outer.y0 - margin and
        inner.x1 <= outer.x1 + margin and
        inner.y1 <= outer.y1 + margin
    )


def _rect_overlap_ratio(r1, r2):
    """Return intersection area divided by the smaller rectangle's area.
    If either rectangle has zero area (degenerate) the ratio is 0 to avoid
    divide-by-zero warnings that can spam the console."""
    import fitz
    a1 = _rect_area(r1)
    a2 = _rect_area(r2)
    if a1 == 0 or a2 == 0:
        return 0.0
    inter = fitz.Rect(r1 & r2)
    ia = _rect_area(inter)
    if ia == 0:
        return 0.0
    return ia / min(a1, a2)


class ColorDetector:
    """
    A class for detecting and analyzing colors in PDF documents.
    
    This class provides methods for:
    - Extracting text and background colors from PDF elements
    - Calculating color contrast ratios
    - Handling various color formats and edge cases
    
    Attributes:
        debug (bool): Enable debug mode for additional logging
        last_pixel_sample (tuple): Cache of the last sampled pixel color
        last_metadata_sample (tuple): Cache of the last metadata color
        last_bg_variance (float): Cache of the last background color variance
    """
    
    def __init__(self, debug=False):
        """
        Initialize the ColorDetector.
        
        Args:
            debug (bool): Enable debug mode for additional logging
        """
        self.debug = debug
        self.last_pixel_sample = None
        self.last_metadata_sample = None
        self.last_bg_variance = None
    
    def unpack_color(self, color):
        """
        Safely unpack a color value into RGB components.
        
        Args:
            color: Color value in various formats (list, tuple, int, float)
            
        Returns:
            list: RGB values as floats [r, g, b] or None if invalid
        """
        try:
            if isinstance(color, (list, tuple)):
                if len(color) >= 3:
                    # Ensure values are between 0 and 1
                    rgb = [float(c) for c in color[:3]]
                    return [max(0.0, min(1.0, c)) for c in rgb]
                return None
            elif isinstance(color, (int, float)):
                if isinstance(color, int) and color > 1:
                    # Treat as 24-bit RGB integer (0xRRGGBB)
                    r = ((color >> 16) & 0xFF) / 255.0
                    g = ((color >> 8) & 0xFF) / 255.0
                    b = (color & 0xFF) / 255.0
                    return [r, g, b]
                else:
                    # Handle single value as grayscale (0-1 range)
                    value = float(color)
                    value = max(0.0, min(1.0, value))
                    return [value, value, value]
            elif isinstance(color, str):
                # Handle hex strings like '#RRGGBB' or 'RRGGBB'
                if color.startswith('#'):
                    color = color[1:]
                if len(color) == 6:
                    try:
                        r = int(color[0:2], 16) / 255.0
                        g = int(color[2:4], 16) / 255.0
                        b = int(color[4:6], 16) / 255.0
                        return [r, g, b]
                    except ValueError:
                        pass
            return None
        except (ValueError, TypeError) as e:
            if self.debug:
                print(f"Error unpacking color {color}: {str(e)}")
            return None
    
    def get_dominant_background_color(self, colors):
        """Get the most common background color from sampled pixels"""
        from collections import Counter
        
        # Convert colors to tuples for counting
        color_tuples = [tuple(int(c * 255) for c in color) for color in colors]
        
        # Count occurrences of each color
        color_counts = Counter(color_tuples)
        
        # Get the most common color
        if color_counts:
            dominant_color = color_counts.most_common(1)[0][0]
            return [c / 255.0 for c in dominant_color]
        
        return [1, 1, 1]  # Default to white if no colors found
    
    # ------------------------------------------------------------------
    # Pixel sampling (no bbox expansion) – generic utility
    # ------------------------------------------------------------------
    def sample_pixels(self, page, bbox, zoom=2):
        """Return dominant colour of the *border* of bbox (1-px frame)."""
        import fitz
        try:
            rect = _rect_from(bbox)
            if rect.x1 - rect.x0 <= 0 or rect.y1 - rect.y0 <= 0:
                return [1, 1, 1]

            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, clip=rect, alpha=False)

            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            if img.width == 0 or img.height == 0:
                return [1, 1, 1]

            colors = []
            # Top & bottom rows
            for x in range(img.width):
                colors.append(img.getpixel((x, 0)))
                colors.append(img.getpixel((x, img.height - 1)))
            # Left & right columns
            for y in range(img.height):
                colors.append(img.getpixel((0, y)))
                colors.append(img.getpixel((img.width - 1, y)))

            if not colors:
                return [1, 1, 1]

            # Convert to 0-1 rgb and find dominant
            colors_f = [[c[0]/255, c[1]/255, c[2]/255] for c in colors]
            dominant = self.get_dominant_background_color(colors_f)
            return dominant

        except Exception as e:
            if self.debug:
                print(f"Error sampling pixels: {e}")
            return [1, 1, 1]
    
    def get_text_color(self, page, bbox, metadata_color, bg_color):
        """Get text color, prioritizing metadata over pixel sampling"""
        # Try metadata color first
        color = self.unpack_color(metadata_color)
        if color:
            self.last_metadata_sample = color
            return color
            
        # If no metadata, try to detect from pixels
        try:
            # Sample the text area
            mat = fitz.Matrix(2, 2)  # 2x zoom for better sampling
            pix = page.get_pixmap(matrix=mat, clip=bbox, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Get colors that are significantly different from background
            bg_sum = sum(bg_color)
            colors = []
            for c in img.get_flattened_data():
                r, g, b = c
                r, g, b = r/255.0, g/255.0, b/255.0
                if abs(r + g + b - bg_sum) > 0.3:  # Threshold for difference
                    colors.append([r, g, b])
            
            if colors:
                # Use the most common non-background color
                text_color = self.get_dominant_background_color(colors)
                self.last_pixel_sample = text_color
                return text_color
            
        except Exception as e:
            if self.debug:
                print(f"Error detecting text color: {str(e)}")
        
        return None
    
    def calculate_relative_luminance(self, r, g, b):
        """
        Calculate the relative luminance of a color according to WCAG 2.1 specifications.
        
        Args:
            r (float): Red component (0-1)
            g (float): Green component (0-1)
            b (float): Blue component (0-1)
            
        Returns:
            float: Relative luminance value
        """
        def adjust(value):
            """
            Apply the WCAG 2.1 transformation to a color component.
            
            Args:
                value (float): Color component value
                
            Returns:
                float: Adjusted value
            """
            value = max(0.0, min(1.0, value))
            return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

        return 0.2126 * adjust(r) + 0.7152 * adjust(g) + 0.0722 * adjust(b)

    def calculate_contrast_ratio(self, color1, color2):
        """
        Calculate the contrast ratio between two colors according to WCAG 2.1.
        
        Args:
            color1 (list): First color as [r, g, b] values (0-1)
            color2 (list): Second color as [r, g, b] values (0-1)
            
        Returns:
            tuple: (contrast_ratio, meets_AA_normal, meets_AA_large, meets_AAA_normal, meets_AAA_large)
            or None if calculation fails
        """
        try:
            if not color1 or not color2:
                return None
                
            # Calculate relative luminance for both colors
            l1 = self.calculate_relative_luminance(*color1)
            l2 = self.calculate_relative_luminance(*color2)
            
            # Ensure proper ordering (lighter color should have higher luminance)
            lighter = max(l1, l2)
            darker = min(l1, l2)
            
            # Calculate contrast ratio
            contrast_ratio = (lighter + 0.05) / (darker + 0.05)
            
            # Check against WCAG 2.1 criteria
            meets_AA_normal = contrast_ratio >= 4.5
            meets_AA_large = contrast_ratio >= 3.0
            meets_AAA_normal = contrast_ratio >= 7.0
            meets_AAA_large = contrast_ratio >= 4.5
            
            return (
                contrast_ratio,
                meets_AA_normal,
                meets_AA_large,
                meets_AAA_normal,
                meets_AAA_large
            )
            
        except (TypeError, ValueError, ZeroDivisionError) as e:
            if self.debug:
                print(f"Error calculating contrast ratio: {str(e)}")
            return None

    # ------------------------------------------------------------------
    # Sleeve sampling – looks at a thin sleeve *outside* the span to infer
    # a uniform background colour when metadata lookup fails.
    # ------------------------------------------------------------------
    def sample_sleeve(self, page, bbox, margin_pt=5, zoom=2):
        """Sample a thin margin around the bbox; if >90 % of the sampled
        pixels share the same colour return that as background, else None."""
        import fitz, math
        try:
            rect = _rect_from(bbox)
            # Inflate rectangle
            sleeve = fitz.Rect(rect.x0 - margin_pt,
                               rect.y0 - margin_pt,
                               rect.x1 + margin_pt,
                               rect.y1 + margin_pt)
            # Remove original rect to keep only sleeve area by creating a mask
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, clip=sleeve, alpha=False)
            from PIL import Image, ImageDraw
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Create mask for sleeve area (= full image minus inner rect)
            mask = Image.new("1", img.size, 1)
            draw = ImageDraw.Draw(mask)
            inner = [margin_pt*zoom, margin_pt*zoom, img.width-margin_pt*zoom, img.height-margin_pt*zoom]
            draw.rectangle(inner, fill=0)
            pixels = [img.getpixel((x, y)) for y in range(img.height) for x in range(img.width) if mask.getpixel((x, y))]
            if not pixels:
                return None
            # Count occurrences
            from collections import Counter
            cnt = Counter(pixels)
            (r, g, b), hits = cnt.most_common(1)[0]
            if hits / len(pixels) >= 0.9:
                return [r/255, g/255, b/255]
            return None
        except Exception as e:
            if self.debug:
                print(f"Sleeve sample error: {e}")
            return None

    def sample_bg_inside_span(self, page, bbox, text_color, zoom=3):
        """Sample pixels *inside* the text span that are *not* the text colour
        in order to infer the visual background when metadata / vector analysis
        is wrong.

        Args:
            page (fitz.Page): The page object.
            bbox (fitz.Rect): Bounding box of the text span.
            text_color (list[float]): Detected text colour (0-1 range).
            zoom (int, optional): Render zoom. Defaults to 3.

        Returns:
            list[float] | None: Dominant background RGB in 0-1 range or None.
        """
        import fitz
        try:
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, clip=bbox, alpha=False)
            if pix.width == 0 or pix.height == 0:
                return None

            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            txt = [int(c * 255) for c in text_color]
            candidates = []
            # Simple RGB manhattan distance threshold – skips anti-aliased glyph
            # edges but captures fully background pixels.
            for r, g, b in img.get_flattened_data():
                if abs(r - txt[0]) + abs(g - txt[1]) + abs(b - txt[2]) > 50:
                    candidates.append([r / 255, g / 255, b / 255])

            # Need a reasonable amount of background pixels to be reliable
            if len(candidates) < 10:
                return None

            return self.get_dominant_background_color(candidates)
        except Exception as e:
            if self.debug:
                print(f"Error sampling bg inside span: {e}")
            return None

def check_color_contrast(doc):
    """Check color contrast in PDF document"""
    contrast_results = []
    pdf_results = []
    
    # Create detector instance with debug mode off
    detector = ColorDetector(debug=False)
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict", flags=11)["blocks"]  # flags=11 includes images and tables
        page_results = []
        
        # ---------------------------------------------------------
        # Build background stack (filled paths & images) – drawing order
        # ---------------------------------------------------------
        bg_stack = []
        try:
            import fitz
            # Vector drawings
            for draw in page.get_drawings():
                d_type = draw.get('type')  # 'fill' or 'stroke'
                rect = _rect_from(draw.get('rect'))

                if d_type == 'fill':
                    # ------------------------------------------------------------------
                    # Filled shapes – keep only if they have measurable area.
                    # ------------------------------------------------------------------
                    if _rect_area(rect) == 0:
                        continue
                    fill = draw.get('fill')
                    if not fill:
                        continue
                    bg_stack.append({'type': 'path', 'bbox': rect, 'color': detector.unpack_color(fill)})

                elif d_type == 'stroke':
                    sw_global = draw.get('width', 0) or 0
                    col_global = detector.unpack_color(draw.get('stroke'))

                    # Iterate individual path items because Illustrator sometimes
                    # stores each segment with its own (degenerate) bbox.
                    items = draw.get('items') or []
                    for it in items or [None]:
                        if it:
                            it_bbox = _rect_from(it.get('bbox'))
                            sw = it.get('width', sw_global) or sw_global
                            col = detector.unpack_color(it.get('stroke')) or col_global
                        else:
                            it_bbox = rect
                            sw = sw_global
                            col = col_global

                        if sw < 6 or _rect_area(it_bbox) == 0:
                            # Skip thin strokes; for degenerate bbox inflate below
                            pass

                        # Inflate degenerate bbox
                        if it_bbox.height == 0:
                            it_bbox = fitz.Rect(it_bbox.x0, it_bbox.y0 - sw/2, it_bbox.x1, it_bbox.y1 + sw/2)
                        elif it_bbox.width == 0:
                            it_bbox = fitz.Rect(it_bbox.x0 - sw/2, it_bbox.y0, it_bbox.x1 + sw/2, it_bbox.y1)

                        if _rect_area(it_bbox) == 0:
                            continue

                        # Aspect-ratio guard (<=0.25 after inflation)
                        thin = min(it_bbox.width, it_bbox.height) / max(it_bbox.width, it_bbox.height)
                        if thin > 0.25:
                            continue
                        if not col:
                            continue
                        bg_stack.append({'type': 'stroke', 'bbox': it_bbox, 'color': col})
        except Exception:
            pass

        try:
            # Images
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    rect = _rect_from(page.get_image_bbox(xref))
                except Exception:
                    continue
                if _rect_area(rect) == 0:
                    continue
                bg_stack.append({'type': 'image', 'bbox': rect, 'xref': xref})
        except Exception:
            pass

        # ---------------------------------------------------------
        # Add "path" blocks coming from get_text dict (type == 4)
        # ---------------------------------------------------------
        try:
            for blk in blocks:
                if blk.get('type') != 4:
                    continue
                rect = _rect_from(blk.get('bbox'))
                if _rect_area(rect) == 0:
                    continue
                col = blk.get('color') or blk.get('stroke') or blk.get('fill')
                if not col:
                    continue
                bg_stack.append({'type': 'path', 'bbox': rect, 'color': detector.unpack_color(col)})
        except Exception:
            pass

        # ---------------------------------------------------------
        # Detect thick stroked shapes (possible fake backgrounds)
        # (legacy heuristic kept – independent of bg_stack logic)
        # ---------------------------------------------------------
        stroke_boxes = []  # list[(bbox, stroke_rgb)]
        try:
            for drawing in page.get_drawings():
                if drawing.get("type") != "stroke":
                    continue
                # Each stroke drawing can contain multiple paths / items
                stroke_width = drawing.get("width", 0)
                if stroke_width <= 2:
                    continue  # ignore hairlines
                stroke_color = drawing.get("color", (1, 1, 1))  # default white-ish
                # Aggregate bbox of drawing items
                for item in drawing.get("items", []):
                    bbox = item.get("bbox") or item.get("rect")
                    if bbox and (bbox[2] - bbox[0]) and (bbox[3] - bbox[1]):
                        stroke_boxes.append((bbox, stroke_color))
        except Exception:
            # If get_drawings is missing or fails, fall back silently
            stroke_boxes = []

        # Small helper – bbox intersection with margin (5 pt)
        def _bbox_intersects(b1, b2, margin=5):
            return not (
                b1[2] + margin < b2[0] or  # right of left
                b1[0] - margin > b2[2] or  # left of right
                b1[3] + margin < b2[1] or  # bottom above top
                b1[1] - margin > b2[3]     # top below bottom
            )
        
        for block in blocks:
            if "lines" not in block:
                continue
                
            for line in block["lines"]:
                for span in line["spans"]:
                    # Skip empty or special text
                    text = span.get("text", "").strip()
                    if not text or text.startswith(("Color Contrast:", "✅", "❌")):
                        continue
                        
                    # Get required span properties
                    bbox = span.get("bbox")
                    if not bbox:
                        continue
                        
                    try:
                        # Get text properties
                        font_size = span.get("size", 12)
                        font_flags = span.get("flags", 0)
                        is_bold = bool(font_flags & 2**2)
                        is_large_text = (font_size >= 18) or (font_size >= 14 and is_bold)
                        
                        # --------------------------------------------------
                        # Determine background using drawing / image stack
                        # --------------------------------------------------

                        span_rect = _rect_from(bbox)

                        # Search stack top->bottom
                        bg_color = None
                        for obj in reversed(bg_stack):
                            orect = obj['bbox']
                            if obj['type'] in ('path', 'bar', 'stroke'):
                                ov1 = _rect_overlap_ratio(orect, span_rect)
                                ov2 = _rect_overlap_ratio(span_rect, orect)
                                if _rect_contains(orect, span_rect, margin=1) or ov1 > 0.5 or ov2 > 0.5:
                                    cand = obj['color']
                                    # Skip if candidate colour almost equals text colour – it might be
                                    # an outline or decorative element rather than true background.
                                    if cand and abs(sum(cand) - sum(text_color := detector.unpack_color(span.get("color")))) < 0.05:
                                        continue
                                    bg_color = cand
                                    break
                            else:  # image
                                if _rect_overlap_ratio(orect, span_rect) > 0.9:
                                    inter = _rect_from(orect & span_rect)
                                    bg_color = detector.sample_pixels(page, inter)
                                    break

                        if not bg_color:
                            # Try sleeve sampling first (option-2 fallback)
                            bg_color = detector.sample_sleeve(page, span_rect, margin_pt=5) or detector.sample_pixels(page, span_rect)

                        # ------------------------------------------------------------------
                        # FINAL fallback – if background is still None or suspiciously similar
                        # to the text colour, attempt to take the colour of any thick stroke
                        # bar that intersects the span (option-1). This specifically targets
                        # the white horizontal line behind the front-page heading.
                        # ------------------------------------------------------------------
                        if (not bg_color) or (
                                bg_color and detector.unpack_color(span.get("color")) and
                                abs(sum(bg_color) - sum(detector.unpack_color(span.get("color")))) < 0.05):
                            try:
                                for sbbox, scol in stroke_boxes:
                                    if _bbox_intersects(span_rect, sbbox):
                                        bg_color = detector.unpack_color(scol)
                                        break
                            except Exception:
                                pass

                        # Get text color from metadata or sampling
                        text_color = detector.get_text_color(page, bbox, span.get("color"), bg_color)
                        if not text_color:
                            # Fallback: try to get text color directly from span metadata
                            text_color = detector.unpack_color(span.get("color", 0))
                            if not text_color:
                                # Final fallback: assume black text
                                text_color = [0, 0, 0]
                        
                        # Ensure we have a background color
                        if not bg_color:
                            # Final fallback: assume white background
                            bg_color = [1, 1, 1]
                        
                        # Calculate contrast
                        ratio_result = detector.calculate_contrast_ratio(text_color, bg_color)
                        if not ratio_result:
                            # This should rarely happen now, but skip if it does
                            continue
                        contrast_ratio = ratio_result[0]
                        # Remove the contrast_ratio <= 1.0 filter as it may skip valid headings
                        # if contrast_ratio <= 1.0:
                        #     continue

                        # Detect fake background technique via edge sampling
                        fake_bg_detected = False
                        try:
                            # Expand bbox by 10px on each side
                            margin_px = 10
                            expanded = fitz.Rect(bbox[0] - margin_px,
                                                  bbox[1] - margin_px,
                                                  bbox[2] + margin_px,
                                                  bbox[3] + margin_px)
                            # Sample at native resolution (no zoom)
                            pix_sample = page.get_pixmap(matrix=fitz.Matrix(1, 1), clip=expanded, alpha=False)
                            img_sample = Image.frombytes("RGB", [pix_sample.width, pix_sample.height], pix_sample.samples)
                            # Collect edge pixels
                            edge_pixels = []
                            # Top & bottom rows
                            for x in range(img_sample.width):
                                edge_pixels.append(img_sample.getpixel((x, 0)))
                                edge_pixels.append(img_sample.getpixel((x, img_sample.height - 1)))
                            # Left & right columns
                            for y in range(img_sample.height):
                                edge_pixels.append(img_sample.getpixel((0, y)))
                                edge_pixels.append(img_sample.getpixel((img_sample.width - 1, y)))
                            if edge_pixels:
                                avg_edge = [sum(p[i] for p in edge_pixels) / len(edge_pixels) for i in range(3)]
                                text_rgb = [int(c * 255) for c in text_color]
                                bg_rgb = [int(c * 255) for c in bg_color]
                                def rgb_dist(c1, c2):
                                    return ((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2 + (c1[2]-c2[2])**2) ** 0.5
                                if rgb_dist(avg_edge, text_rgb) > 100 and rgb_dist(avg_edge, bg_rgb) > 100:
                                    fake_bg_detected = True
                        except Exception as edge_err:
                            # If edge sampling fails we simply don't flag fake background
                            fake_bg_detected = False

                        # ------------------------------------------------------------------
                        # NEW: stroked-shape (fake background) detection via get_drawings
                        # ------------------------------------------------------------------
                        manual_reason = None
                        if not manual_reason:  # Only if not already flagged by edge sampling
                            try:
                                for sbbox, scol in stroke_boxes:
                                    if _bbox_intersects(bbox, sbbox):
                                        # Compute simple RGB distance between stroke & text colours
                                        stroke_rgb = [int(c*255) for c in scol[:3]]
                                        text_rgb = [int(c*255) for c in text_color]
                                        dist = ((stroke_rgb[0]-text_rgb[0])**2 + (stroke_rgb[1]-text_rgb[1])**2 + (stroke_rgb[2]-text_rgb[2])**2)**0.5
                                        if dist > 150:  # highly contrasting stroke (likely white)
                                            manual_reason = "Possible stroked shape behind text (fake background). Review manually."
                                            break
                            except Exception:
                                pass

                        # ------------------------------------------------------------------
                        # Pixel-sampling fallback – if initial contrast is suspiciously low
                        # (e.g. metadata says FG and BG are nearly identical) attempt to
                        # resample background colours directly from raster.
                        # ------------------------------------------------------------------
                        # Enable fallback for more scenarios (increased from 2.0 to 4.0)
                        if contrast_ratio < 4.0 or is_large_text:
                            sampled_bg = detector.sample_bg_inside_span(page, span_rect, text_color)
                            if sampled_bg and sampled_bg != bg_color:
                                alt_ratio_res = detector.calculate_contrast_ratio(text_color, sampled_bg)
                                if alt_ratio_res and alt_ratio_res[0] > contrast_ratio:
                                    # Adopt the sampled background as the final one
                                    bg_color = sampled_bg
                                    contrast_ratio = alt_ratio_res[0]
                                    ratio_result = alt_ratio_res
                                    # Flag for manual review so the report shows provenance
                                    if not manual_reason:
                                        manual_reason = "Background updated by pixel sampling (metadata likely incorrect)."

                        # ------------------------------------------------------------------
                        # Pixel-sampling verification – always perform a quick raster check
                        # to validate the metadata-derived background. If the dominant pixel
                        # colour differs markedly, use the pixel colour instead.
                        # ------------------------------------------------------------------
                        sampled_bg = detector.sample_bg_inside_span(page, span_rect, text_color)
                        if sampled_bg:
                            colour_delta = sum(abs(sampled_bg[i] - bg_color[i]) for i in range(3))
                            if colour_delta > 0.15:  # ≈38/255 average channel diff
                                alt_ratio_res = detector.calculate_contrast_ratio(text_color, sampled_bg)
                                if alt_ratio_res:
                                    bg_color = sampled_bg
                                    contrast_ratio = alt_ratio_res[0]
                                    ratio_result = alt_ratio_res
                                    if not manual_reason:
                                        manual_reason = "Background updated by pixel sampling (metadata mismatch)."

                        # Check against WCAG criteria
                        passes_aa = (contrast_ratio >= 3.0 if is_large_text else contrast_ratio >= 4.5)
                        passes_aaa = (contrast_ratio >= 4.5 if is_large_text else contrast_ratio >= 7.0)
                        
                        # Get sampling data
                        sample_values = {
                            'pixel': detector.last_pixel_sample,
                            'metadata': detector.last_metadata_sample
                        }
                        
                        # Store result
                        result = {
                            'text': text,
                            'contrast_ratio': contrast_ratio,
                            'is_large_text': is_large_text,
                            'passes_aa': passes_aa,
                            'passes_aaa': passes_aaa,
                            'font_size': font_size,
                            'is_bold': is_bold,
                            'bbox': bbox,
                            'color': text_color,
                            'bgcolor': bg_color,
                            'confidence': 'HIGH',
                            'manual_check_reason': manual_reason,
                            'sample_values': sample_values,
                            'page': page_num + 1
                        }
                        
                        # Only store if we have all required data
                        if all([
                            result['text'].strip(),
                            result['color'],
                            result['bgcolor'],
                            isinstance(result['contrast_ratio'], (int, float))
                        ]):
                            page_results.append(result)
                            # Add to PDF results
                            pdf_results.append(result)
                            
                    except Exception as e:
                        if isinstance(e, KeyboardInterrupt):
                            raise e
                        print(f"Error processing span: {str(e)}")
                        continue
        
        # Store page results even if empty (to track scanned pages)
        contrast_results.append({
            'page': page_num,
            'results': page_results
        })
    
    return contrast_results, pdf_results

def render_debug_overlay(page, debug_info, output_path=None):
    """
    Render debug overlay showing color detection results
    """
    # Create page image
    zoom = 2
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    draw = ImageDraw.Draw(img)
    
    # Try to load a font, fallback to default if not found
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12 * zoom)
    except:
        font = ImageFont.load_default()

    # Draw debug info for each text block
    for info in debug_info:
        if not info.get('bbox'):
            continue
            
        bbox = [coord * zoom for coord in info['bbox']]
        x, y = bbox[0], bbox[1]
        
        # Draw color swatches and text
        swatch_size = 10 * zoom
        spacing = 5 * zoom
        
        # Text color swatch
        if info['final_text_color']:
            text_color = hex_to_rgb(info['final_text_color'])
            draw.rectangle([x, y, x + swatch_size, y + swatch_size], fill=text_color)
            
        # Background color swatch
        if info['final_bg_color']:
            bg_color = hex_to_rgb(info['final_bg_color'])
            draw.rectangle([x + swatch_size + spacing, y, 
                          x + 2 * swatch_size + spacing, y + swatch_size], 
                         fill=bg_color)
        
        # Draw text
        label = f"Contrast: {info['contrast_ratio']:.1f}:1 - {info['method']}"
        draw.text((x, y + swatch_size + spacing), label, 
                 fill=(0, 0, 0), font=font)
        
        # Draw bbox outline
        draw.rectangle(bbox, outline=(255, 0, 0), width=1)

    if output_path:
        img.save(output_path)
    return img

class PDF(FPDF):
    def __init__(self):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(True, margin=25)
        self.set_margins(20, 20, 20)  # Left, Top, Right margins
        self.set_compression(True)
        
        # Page dimensions and margins
        self.page_width = 210  # A4 width in mm
        self.page_height = 297  # A4 height in mm
        self.left_margin = 20
        self.right_margin = 20
        self.top_margin = 30  # Increased top margin for header
        self.bottom_margin = 25  # Increased bottom margin for footer
        self.header_height = 20  # Space reserved for header
        self.footer_height = 15  # Space reserved for footer
        
        # Calculate effective content area
        self.content_width = self.page_width - (self.left_margin + self.right_margin)
        self.content_height = self.page_height - (self.top_margin + self.bottom_margin + self.header_height + self.footer_height)
        
        # Current Y position tracking (start after header)
        self.current_y = self.top_margin + self.header_height
        
        # Use built-in fonts
        self.font_family = 'helvetica'
        self.set_font(self.font_family, '', 10)
        
        # Add first page
        self.add_page()

def rgb_to_hex(r, g, b):
    """Convert RGB (0-1) to hex color code"""
    r = min(max(int(r * 255), 0), 255)
    g = min(max(int(g * 255), 0), 255)
    b = min(max(int(b * 255), 0), 255)
    return f"#{r:02x}{g:02x}{b:02x}"

def _flatten_results(contrast_results):
    """Helper to flatten nested contrast_results into a list of text blocks."""
    if not contrast_results:
        return []
    # If already a list of blocks (each has 'text'), return as is
    if isinstance(contrast_results[0], dict) and 'text' in contrast_results[0]:
        return contrast_results
    # Else, assume format [{page, results:[...]}, ...]
    flattened = []
    for page_entry in contrast_results:
        page_num = page_entry.get('page', None)
        for block in page_entry.get('results', []):
            # Ensure page attribute present
            if 'page' not in block:
                block['page'] = page_num + 1 if isinstance(page_num, int) else page_num
            flattened.append(block)
    return flattened

def display_results(contrast_results, pdf_results):
    """
    Display contrast analysis results in the Streamlit UI.
    """
    try:
        # Flatten results for easier processing
        flat_results = _flatten_results(contrast_results)
        if not flat_results:
            st.warning("No text elements found to analyze.")
            return

        # Display summary metrics
        total_elements = len(flat_results)
        passing_elements = sum(1 for block in flat_results if block.get('passes_aa', False))

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Elements", total_elements)
        with col2:
            st.metric("WCAG AA Compliant", passing_elements)
        with col3:
            compliance_rate = (passing_elements / total_elements * 100) if total_elements > 0 else 0
            st.metric("Compliance Rate", f"{compliance_rate:.1f}%")

        # Display detailed results
        st.subheader("Detailed Results")
        tab1, tab2 = st.tabs(["Table View", "Page View"])

        with tab1:
            # Convert results to DataFrame for table view
            data = []
            for block in flat_results:
                text_raw = block.get('text', '')
                text = clean_text_for_pdf(text_raw)
                if not text:
                    continue
                if len(text) > 50:
                    text = text[:47] + "..."
                data.append({
                    'Page': block.get('page', ''),
                    'Text': text,
                    'Contrast Ratio': f"{block.get('contrast_ratio', 0):.2f}",
                    'Status': '✅ Pass' if block.get('passes_aa', False) else '❌ Fail',
                    'Font Size': f"{block.get('font_size', 12):.1f}pt",
                    'WCAG AAA': '✅' if block.get('passes_aaa', False) else '❌'
                })
            st.dataframe(data, width='stretch')

        with tab2:
            pages = {}
            for block in flat_results:
                page = block.get('page', 1)
                pages.setdefault(page, []).append(block)
            for page_num in sorted(pages.keys()):
                with st.expander(f"Page {page_num}"):
                    for block in pages[page_num]:
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.text(block.get('text', '').strip())
                        with col2:
                            ratio = block.get('contrast_ratio', 0)
                            if block.get('passes_aa', False):
                                st.success(f"Ratio: {ratio:.2f}")
                            else:
                                st.error(f"Ratio: {ratio:.2f}")
        # Removed all colour-pair summary UI from here
    except Exception as e:
        st.error(f"Error displaying results: {str(e)}")

def generate_contrast_report(results):
    """
    Generate a detailed contrast analysis report in PDF format.

    Args:
        results (list): Flat list of contrast analysis results

    Returns:
        bytes: PDF report as bytes, or None if generation fails
    """
    try:
        if not results:
            return None

        pdf = PDF()
        pdf.add_page()

        # Add report header
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, 'Color Contrast Analysis Report', ln=True, align='C')
        pdf.ln(10)

        # Add summary section
        pdf.set_font('helvetica', 'B', 14)
        pdf.cell(0, 10, 'Summary', ln=True)
        pdf.set_font('helvetica', '', 12)

        total_elements = len(results)
        passing_elements = sum(1 for block in results if block.get('passes_aa', False))

        pdf.cell(0, 8, f'Total Text Elements Analyzed: {total_elements}', ln=True)
        pdf.cell(0, 8, f'WCAG AA Compliant Elements: {passing_elements}', ln=True)
        pdf.cell(0, 8, f'Compliance Rate: {(passing_elements/total_elements*100):.1f}%', ln=True)
        pdf.ln(10)

        # Add detailed results
        pdf.set_font('helvetica', 'B', 14)
        pdf.cell(0, 10, 'Detailed Results', ln=True)
        pdf.set_font('helvetica', '', 10)

        # Create table headers
        col_widths = [12, 12, 12, 60, 25, 15, 15]
        headers = ['Pg', 'FG', 'BG', 'Text', 'Contrast', 'AA', 'AAA']
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 10, header, 1)
        pdf.ln()

        # Add table rows
        for block in results:
            text = clean_text_for_pdf(block.get('text', ''))
            if not text:
                continue  # Skip blank / unrepresentable text rows
            if len(text) > 40:
                text = text[:37] + '...'

            # Page number
            pdf.cell(col_widths[0], 10, str(block.get('page', '')), 1)

            # Foreground (text) color box with 'T'
            fg_rgb = [int(c * 255) for c in block.get('color', [0, 0, 0])]
            pdf.set_fill_color(*fg_rgb)
            x_before = pdf.get_x()
            y_before = pdf.get_y()
            pdf.cell(col_widths[1], 10, '', 1, 0, fill=True)
            # Overlay 'T' centered
            pdf.set_text_color(255 if sum(fg_rgb) < 382 else 0)
            pdf.set_xy(x_before, y_before)
            pdf.cell(col_widths[1], 10, 'T', 0, 0, 'C')
            pdf.set_text_color(0)

            # Background color box
            bg_rgb = [int(c * 255) for c in block.get('bgcolor', [255, 255, 255])]
            pdf.set_fill_color(*bg_rgb)
            pdf.cell(col_widths[2], 10, '', 1, 0, fill=True)

            # Text and data
            pdf.cell(col_widths[3], 10, text, 1)
            pdf.cell(col_widths[4], 10, f"{block.get('contrast_ratio', 0):.2f}", 1)

            aa_status = 'Pass' if block.get('passes_aa', False) else 'Fail'
            aaa_status = 'Pass' if block.get('passes_aaa', False) else 'Fail'
            pdf.cell(col_widths[5], 10, aa_status, 1, align='C')
            pdf.cell(col_widths[6], 10, aaa_status, 1, align='C')
            pdf.ln()

        # Add timestamp
        pdf.ln(5)
        pdf.set_font('helvetica', 'I', 10)
        pdf.cell(0, 10, f"Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True)

        # Generate the PDF content. `output(dest='S')` may return either a
        # `str` (Latin-1 encoded) or a `bytes`/`bytearray` depending on the
        # version of the fpdf library.  Handle both cases gracefully so we
        # avoid errors such as "'bytearray' object has no attribute 'encode'".

        pdf_data = pdf.output(dest='S')

        if isinstance(pdf_data, (bytes, bytearray)):
            pdf_bytes = bytes(pdf_data)  # Ensure immutable bytes type
        else:
            # Older versions can return `str` – encode to Latin-1 which is the
            # expected output format of fpdf.
            pdf_bytes = pdf_data.encode('latin1')

        buffer = io.BytesIO(pdf_bytes)
        buffer.seek(0)
        return buffer

    except Exception as e:
        st.error(f"Error generating report: {str(e)}")
        return None

def create_contrast_overlay(page, text_blocks):
    """Create a visual overlay showing contrast issues"""
    # Create a pixmap with higher resolution for better quality
    zoom = 2
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    
    # Guard against empty pixmap which would cause division errors
    if pix.width == 0 or pix.height == 0 or page.rect.width == 0 or page.rect.height == 0:
        # Return simple RGB image copy to avoid crash
        return Image.new('RGB', (max(pix.width, 1), max(pix.height, 1)), color='white')
    
    # Convert to PIL Image
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    
    # Create transparent overlay
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Try to load a font, fallback to default if not found
    try:
        # Use a smaller font size (25% of original)
        font_size = int(12 * zoom * 0.25)
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except:
        font = ImageFont.load_default()
    
    # Calculate scale factor for coordinates (ensure no division by zero)
    safe_width = page.rect.width if page.rect.width else 1
    safe_height = page.rect.height if page.rect.height else 1
    scale_x = pix.width / safe_width if safe_width else 1
    scale_y = pix.height / safe_height if safe_height else 1
    
    # Draw rectangles for each text block
    for block in text_blocks:
        try:
            bbox = block['bbox']
            if not bbox or bbox[2] - bbox[0] == 0 or bbox[3] - bbox[1] == 0:
                continue  # skip degenerate boxes
            contrast_ratio = block['contrast_ratio']
            is_large = block['is_large_text']

            # Scale coordinates
            x0, y0, x1, y1 = [
                bbox[0] * scale_x,
                bbox[1] * scale_y,
                bbox[2] * scale_x,
                bbox[3] * scale_y
            ]

            # Ensure at least 1 pixel size
            if x1 <= x0:
                x1 = x0 + 1
            if y1 <= y0:
                y1 = y0 + 1

            # Determine WCAG status
            aa_required = 3.0 if is_large else 4.5
            aaa_required = 4.5 if is_large else 7.0
            passes_aa = contrast_ratio >= aa_required
            passes_aaa = contrast_ratio >= aaa_required

            # Determine color based on WCAG status
            if passes_aaa:
                color = (0, 255, 0, 80)  # Green (passes AAA)
                status = "AAA PASS"
            elif passes_aa:
                color = (255, 255, 0, 80)  # Yellow (passes AA)
                status = "AA PASS"
            else:
                color = (255, 0, 0, 80)  # Red (fails)
                status = "FAIL"

            # Draw rectangle
            draw.rectangle([x0, y0, x1, y1], fill=color)

            # Create text for the pill
            text = f"{contrast_ratio:.1f}:1 - {status}"

            # Calculate text size for pill background
            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]

            # Add padding to pill
            padding_x = 8
            padding_y = 4

            # Position text above the block if possible
            text_y = y0 - text_height - padding_y * 2 if y0 > text_height + padding_y * 2 else y1 + padding_y

            # Draw dark grey pill background
            pill_x0 = x0
            pill_y0 = text_y
            pill_x1 = x0 + text_width + padding_x * 2
            pill_y1 = text_y + text_height + padding_y * 2
            draw.rectangle([pill_x0, pill_y0, pill_x1, pill_y1],
                          fill=(64, 64, 64, 230),  # Dark grey with high opacity
                          outline=(32, 32, 32, 255))  # Darker outline

            # Draw white text
            text_x = x0 + padding_x
            text_y = text_y + padding_y
            draw.text((text_x, text_y), text,
                      font=font, fill=(255, 255, 255, 255))  # White text
        except Exception:
            # Silently skip problematic block in production; comment out for debug
            continue
    
    # Combine original image with overlay
    result = Image.alpha_composite(img.convert('RGBA'), overlay)
    return result

def generate_heatmap_pdf(doc, text_blocks_by_page):
    """Generate a PDF with contrast heatmap overlays"""
    # Create output PDF
    output_pdf = fitz.open()
    
    # Create detector for color calculations
    detector = ColorDetector()
    
    for page_num in range(len(doc)):
        try:
            original_page = doc[page_num]
            if original_page.rect.width == 0 or original_page.rect.height == 0:
                continue  # skip zero-dimension pages

            text_blocks = text_blocks_by_page.get(page_num)
            if not text_blocks or not isinstance(text_blocks, list):
                continue

            # Filter out any degenerate bboxes (zero area)
            text_blocks = [b for b in text_blocks if (b.get('bbox') and b['bbox'][2]-b['bbox'][0] and b['bbox'][3]-b['bbox'][1])]
            if not text_blocks:
                continue

            overlay_image = create_contrast_overlay(original_page, text_blocks)

            img_bytes = io.BytesIO()
            overlay_image.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            img_w, img_h = overlay_image.size
            new_page = output_pdf.new_page(width=max(img_w, 1), height=max(img_h, 1))
            new_page.insert_image(new_page.rect, stream=img_bytes.getvalue())
        except Exception as e:
            print(f"Error creating heatmap for page {page_num+1}: {e}")
            continue
    
    # Add legend page
    legend_page = output_pdf.new_page(width=595, height=842)  # A4
    
    # Add legend text
    legend_page.insert_text((50, 50), clean_text_for_pdf("Contrast Check Heatmap Legend"), 
                           fontsize=16, color=(0, 0, 0))
    
    # Add color boxes and explanations
    y_pos = 100
    box_size = 20
    spacing = 40
    
    # Green box - AAA Pass
    legend_page.draw_rect((50, y_pos, 50 + box_size, y_pos + box_size), 
                         color=(0, 1, 0), fill=(0, 1, 0), fill_opacity=0.3)
    legend_page.insert_text((90, y_pos + 15), 
                           clean_text_for_pdf("Passes WCAG AAA (>=7.0:1 normal text, >=4.5:1 large text)"), 
                           fontsize=12)
    
    # Yellow box - AA Pass
    y_pos += spacing
    legend_page.draw_rect((50, y_pos, 50 + box_size, y_pos + box_size), 
                         color=(1, 1, 0), fill=(1, 1, 0), fill_opacity=0.3)
    legend_page.insert_text((90, y_pos + 15), 
                           clean_text_for_pdf("Passes WCAG AA (>=4.5:1 normal text, >=3.0:1 large text)"), 
                           fontsize=12)
    
    # Red box - Fail
    y_pos += spacing
    legend_page.draw_rect((50, y_pos, 50 + box_size, y_pos + box_size), 
                         color=(1, 0, 0), fill=(1, 0, 0), fill_opacity=0.3)
    legend_page.insert_text((90, y_pos + 15), 
                           clean_text_for_pdf("Fails WCAG AA requirements"), 
                           fontsize=12)
    
    # Add text size explanation
    y_pos += spacing * 1.5
    legend_page.insert_text((50, y_pos), 
                           clean_text_for_pdf("Text Size Categories:"), 
                           fontsize=14)
    y_pos += spacing
    legend_page.insert_text((50, y_pos), 
                           clean_text_for_pdf("• Large Text: >=18pt or >=14pt bold"), 
                           fontsize=12)
    y_pos += spacing / 2
    legend_page.insert_text((50, y_pos), 
                           clean_text_for_pdf("• Normal Text: <18pt and <14pt bold"), 
                           fontsize=12)
    
    # Create buffer and save PDF
    buffer = io.BytesIO()
    output_pdf.save(buffer)
    buffer.seek(0)
    return buffer

# ------------------------------------------------------------------
# PDF preprocessing helper – convert stroked paths to filled outlines
# using MuPDF's CLI (mutool). Falls back silently if mutool is missing.
# ------------------------------------------------------------------

def outline_strokes(pdf_bytes):
    """Return a copy of the PDF where every stroke has been converted to a
    filled path so thick bars are detectable as rectangles. If the external
    mutool binary cannot be executed we simply return the original bytes."""
    try:
        # Write original bytes to a temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_in:
            tmp_in.write(pdf_bytes)
            tmp_in_path = tmp_in.name

        tmp_out_path = tmp_in_path + "_outlined.pdf"

        cmd = ["mutool", "convert", "-O", "stroke=1", "-o", tmp_out_path, tmp_in_path]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0:
            return pdf_bytes  # mutool not available or failed

        with open(tmp_out_path, "rb") as f_out:
            outlined = f_out.read()
        # Clean up temp files
        os.remove(tmp_in_path)
        os.remove(tmp_out_path)
        return outlined if outlined else pdf_bytes
    except Exception:
        return pdf_bytes

# Add PDF validation and error handling
def validate_pdf_file(file):
    """Validate uploaded PDF file"""
    try:
        if file is None:
            return False, None, "No file uploaded"
            
        # Get file content
        file_bytes = file.getvalue()
        file_size = len(file_bytes)
        
        # Debug info
        st.info(f"Debug: Uploaded file size: {file_size/1024:.1f}KB, Type: {file.type}")
        
        # Check minimum file size (5KB)
        if file_size < 5 * 1024:  # 5KB
            return False, None, "File is too small to be a valid PDF (minimum 5KB required)"
            
        # Check file signature
        if not file_bytes.startswith(b'%PDF-'):
            return False, None, "Invalid PDF file format (missing PDF signature)"
            
        # Attempt stroke-to-outline conversion for more reliable background detection
        if ENABLE_STROKE_OUTLINE:
            outlined_bytes = outline_strokes(file_bytes)
        else:
            outlined_bytes = file_bytes
        doc = fitz.open(stream=outlined_bytes, filetype="pdf")

        if doc.page_count == 0:
            doc.close()
            return False, None, "PDF file contains no pages"
        return True, outlined_bytes, None
            
    except Exception as e:
        return False, None, f"Error validating PDF file: {str(e)}"

def is_large_document(doc, file_size):
    """Determine if a document is large based on pages and file size."""
    LARGE_PAGE_COUNT = 20  # More than 20 pages is considered large
    LARGE_FILE_SIZE = 5 * 1024 * 1024  # 5MB is considered large
    COMPLEX_PAGE_SIZE = 250 * 1024  # 250KB per page is considered complex
    
    page_count = len(doc)
    avg_page_size = file_size / page_count
    
    return (page_count > LARGE_PAGE_COUNT or 
            file_size > LARGE_FILE_SIZE or 
            avg_page_size > COMPLEX_PAGE_SIZE)

# Main logic
if uploaded_file is not None:
    try:
        # Validate PDF file
        is_valid, file_bytes, error_message = validate_pdf_file(uploaded_file)
        
        if not is_valid:
            st.error(error_message)
        else:
            # Calculate file hash to detect changes
            current_hash = hashlib.md5(file_bytes).hexdigest()
            
            # Check document size and complexity
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                if is_large_document(doc, len(file_bytes)):
                    st.warning("⚠️ Note: For larger and more complex documents, the analysis process can take several minutes. Please be patient.", icon="⏳")
            
            # Check if we need to rescan
            need_rescan = (st.session_state.current_file_hash != current_hash or
                          st.session_state.contrast_results is None)

            # Clear old data if this is a new file (different hash)
            if need_rescan and st.session_state.current_file_hash is not None:
                # Clear old analysis data to free memory before processing new file
                clear_analysis_data()
                # Re-initialize session state variables
                for var, default_value in SESSION_STATE_VARS.items():
                    if var not in st.session_state:
                        st.session_state[var] = default_value

            if need_rescan:
                try:
                    doc = fitz.open(stream=file_bytes, filetype="pdf")
                    total_pages = len(doc)
                    # Create progress bars
                    scan_progress = st.progress(0, text="Starting contrast analysis...")
                    # Initialize results and detector
                    contrast_results = []
                    pdf_results = []
                    text_blocks_by_page = {}
                    detector = ColorDetector(debug=True)
                    # Analyze each page
                    for page_num in range(total_pages):
                        page = doc[page_num]
                        # Update progress
                        progress = (page_num + 1) / total_pages
                        scan_progress.progress(progress, f"Analyzing page {page_num + 1} of {total_pages}")
                        # Analyze contrast for this page
                        text_blocks = []
                        blocks = page.get_text("dict")["blocks"]
                        for block in blocks:
                            if "lines" not in block:
                                continue
                            for line in block["lines"]:
                                for span in line["spans"]:
                                    text = span.get("text", "").strip()
                                    if not text:
                                        continue
                                    if text.startswith("Color Contrast:") or text.startswith("✅") or text.startswith("❌"):
                                        continue
                                    # Get text properties
                                    font_size = span.get("size", 12)
                                    font_flags = span.get("flags", 0)
                                    is_bold = bool(font_flags & 2**2)
                                    text_color = detector.unpack_color(span.get("color", 0))
                                    bbox = span.get("bbox", None)
                                    if not bbox:
                                        continue
                                    try:
                                        # Get background color
                                        bg_color = detector.unpack_color(span.get("bgcolor", [1, 1, 1]))
                                        if not text_color or not bg_color:
                                            continue
                                        # Calculate contrast
                                        ratio_result = detector.calculate_contrast_ratio(text_color, bg_color)
                                        if not ratio_result:
                                            continue
                                        contrast_ratio = ratio_result[0]
                                        # Store block info
                                        text_blocks.append({
                                            'text': text,
                                            'bbox': bbox,
                                            'contrast_ratio': contrast_ratio,
                                            'is_large_text': (font_size >= 18) or (font_size >= 14 and is_bold)
                                        })
                                    except Exception:
                                        continue
                        if text_blocks:
                            text_blocks_by_page[page_num] = text_blocks

                    # Get overall results - PROCESS FULL DOCUMENT (no truncation)
                    contrast_results, pdf_results = check_color_contrast(doc)

                    # Store results temporarily for this session (will be cleared after use)
                    st.session_state.contrast_results = contrast_results
                    st.session_state.pdf_results = pdf_results
                    st.session_state.text_blocks_by_page = text_blocks_by_page
                    st.session_state.current_file_hash = current_hash
                    
                    # Calculate and store summary statistics (lightweight, keep these)
                    flat_results = _flatten_results(contrast_results)
                    total_elements = len(flat_results)
                    passing_aa = sum(1 for block in flat_results if block.get('passes_aa', False))
                    passing_aaa = sum(1 for block in flat_results if block.get('passes_aaa', False))
                    st.session_state['summary_stats'] = {
                        'total_elements': total_elements,
                        'passing_aa': passing_aa,
                        'passing_aaa': passing_aaa,
                        'compliance_rate_aa': (passing_aa / total_elements * 100) if total_elements > 0 else 0,
                        'compliance_rate_aaa': (passing_aaa / total_elements * 100) if total_elements > 0 else 0,
                        'file_hash': current_hash
                    }

                    # Optionally save backup to Google Sheets (archive feature)
                    use_sheets = st.session_state.get('use_sheets_storage', False)
                    quota_exceeded = st.session_state.get('sheets_quota_exceeded', False)
                    if use_sheets and not quota_exceeded:
                        user_email = st.session_state.get('user_email', '')
                        if save_results_to_sheets(contrast_results, pdf_results, current_hash, user_email):
                            st.info("💾 Results archived to Google Sheets.")
                        # Note: If save fails due to quota, the function will disable the option and show error
                    
                    # -----------------------------------------------------
                    # Make flattened results available for other UI modules
                    # -----------------------------------------------------
                    try:
                        st.session_state["contrast_df"] = pd.DataFrame(_flatten_results(contrast_results))
                    except Exception as _df_err:
                        # Keep a placeholder DataFrame so downstream code
                        # doesn't KeyError even if conversion failed.
                        st.session_state["contrast_df"] = pd.DataFrame()
                        st.warning(f"Could not build contrast_df: {_df_err}")
                    
                    # Close document after analysis
                    doc.close()

                    # Clear progress bar
                    scan_progress.empty()
                except Exception as e:
                    st.error(f"Error during PDF analysis: {str(e)}")
            else:
                # Use cached results
                contrast_results = st.session_state.get("contrast_results", [])
                pdf_results = st.session_state.get("pdf_results", [])
                text_blocks_by_page = st.session_state.get("text_blocks_by_page", {})

                # ------------------------------------------------------------------
                # Populate contrast_df if it is missing (e.g. first run after reload
                # that hit the cache branch).  Down-stream UI like the colour-pair
                # summary expects this to exist.
                # ------------------------------------------------------------------
                if "contrast_df" not in st.session_state or st.session_state["contrast_df"].empty:
                    try:
                        st.session_state["contrast_df"] = pd.DataFrame(_flatten_results(contrast_results))
                    except Exception as _cdf_err:
                        st.session_state["contrast_df"] = pd.DataFrame()
                        st.warning(f"Could not rebuild contrast_df from cache: {_cdf_err}")

            # Only rebuild text_blocks_by_page if not already stored (avoid duplication)
            if 'text_blocks_by_page' not in st.session_state or st.session_state['text_blocks_by_page'] is None:
                contrast_results_flat = _flatten_results(contrast_results)
                text_blocks_by_page = defaultdict(list)
                for blk in contrast_results_flat:
                    if not blk.get('bbox'):
                        continue
                    page_idx = max(blk.get('page', 1) - 1, 0)
                    text_blocks_by_page[page_idx].append(blk)
                # Store back to session for reuse
                st.session_state['text_blocks_by_page'] = text_blocks_by_page
            else:
                text_blocks_by_page = st.session_state.get('text_blocks_by_page', {})

            # Create a columns layout for the download buttons
            st.markdown("### Download Reports")
            col1, col2 = st.columns(2)

            # -----------------------------------------------------------------
            # Step-bar for post-scan artefacts (report + heatmap)
            # -----------------------------------------------------------------
            status_bar = st.progress(0, text="Generating text report …")

            # Generate text report PDF
            try:
                pdf_buffer = generate_contrast_report(pdf_results)
                if pdf_buffer:
                    with col1:
                        st.download_button(
                            "📄 Download Text Report (PDF)",
                            pdf_buffer.getvalue(),
                            file_name="contrast_report.pdf",
                            mime="application/pdf"
                        )
                else:
                    st.error("Could not generate text report: Invalid PDF data")
            except Exception as pdf_error:
                st.error(f"Could not generate text report: {str(pdf_error)}")

            status_bar.progress(0.33, text="Generating heatmap PDF …")

            # Generate heatmap PDF if overlay is enabled
            if show_heatmap:
                text_blocks_by_page = st.session_state.get("text_blocks_by_page")
                if not text_blocks_by_page:
                    st.error("Contrast analysis must be run before generating heatmap.")
                else:
                    try:
                        # Open document just for heatmap generation
                        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                            heatmap_buffer = generate_heatmap_pdf(doc, text_blocks_by_page)
                            if heatmap_buffer:
                                with col2:
                                    st.download_button(
                                        "🎨 Download Heatmap PDF",
                                        heatmap_buffer.getvalue(),
                                        file_name="contrast_heatmap.pdf",
                                        mime="application/pdf"
                                    )
                            else:
                                st.warning("Heatmap PDF contained no overlay pages – likely no eligible text blocks were detected. Try toggling 'Show contrast heatmap overlay' and re-running the scan.")
                    except Exception as heatmap_error:
                        st.error(f"Could not generate heatmap PDF: {str(heatmap_error)}")

            status_bar.progress(0.66, text="Preparing heatmap previews …")
            status_bar.progress(1.0, text="Done ✔️")

            # Delay removal a bit so user sees the final state
            import time as _dbg_time; _dbg_time.sleep(0.5)
            status_bar.empty()

            # Display contrast results
            display_results(contrast_results, pdf_results)

            # -------------------- Debug download (page-1 results) ---------------------
            try:
                import json
                page1_results = [blk for blk in pdf_results if blk.get('page') == 1]

                # -------------------------------------------------------------
                # Also capture what the algorithm *sees* on page-1 so that we can
                # cross-compare with the Illustrator / Acrobat layer listings.
                # -------------------------------------------------------------
                raw_page1_info = {}
                try:
                    with fitz.open(stream=file_bytes, filetype="pdf") as _doc_dbg:
                        if len(_doc_dbg) >= 1:
                            p0 = _doc_dbg[0]

                            # Convert drawing objects (fills & strokes) into a
                            # JSON-serialisable form, trimming fields that are
                            # large or binary.
                            drawings = []
                            for d in p0.get_drawings():
                                # PyMuPDF < 1.21 may return tuples instead of dicts
                                if isinstance(d, tuple):
                                    # Tuple layout: (type, rect, width, color, items)
                                    d_type, d_rect, d_width, d_color, d_items = d
                                    d_dict = {
                                        'type': d_type,
                                        'rect': d_rect,
                                        'width': d_width,
                                        'stroke': d_color,
                                        'fill': None,
                                        'items': d_items
                                    }
                                else:
                                    d_dict = d

                                d_summary = {
                                    'type': d_dict.get('type'),
                                    'rect': d_dict.get('rect'),
                                    'width': d_dict.get('width'),
                                    'stroke': d_dict.get('stroke'),
                                    'fill': d_dict.get('fill'),
                                    'items': []
                                }
                                # Only keep bbox + width + stroke for each
                                # item to reduce size.
                                for it in d_dict.get('items', [])[:50]:  # cap to 50
                                    # Fix: Handle case where 'it' is a tuple instead of dict
                                    if isinstance(it, dict):
                                        d_summary['items'].append({
                                            'bbox': it.get('bbox'),
                                            'width': it.get('width'),
                                            'stroke': it.get('stroke')
                                        })
                                    else:
                                        # If it's a tuple or other type, skip or use safe defaults
                                        d_summary['items'].append({
                                            'bbox': None,
                                            'width': None,
                                            'stroke': None
                                        })
                                drawings.append(d_summary)

                            # Grab path blocks (type 4) which often represent
                            # filled rectangles.
                            blocks = p0.get_text("dict", flags=11)["blocks"]
                            path_blocks = [
                                {
                                    'bbox': blk.get('bbox'),
                                    'color': blk.get('color'),
                                    'stroke': blk.get('stroke'),
                                    'fill': blk.get('fill')
                                }
                                for blk in blocks if blk.get('type') == 4
                            ]

                            raw_page1_info = {
                                'drawings': drawings,
                                'path_blocks': path_blocks,
                                'image_count': len(p0.get_images(full=True))
                            }
                except Exception as dbg_err:
                    raw_page1_info = {'error': str(dbg_err)}

                debug_package = {
                    'results': page1_results,
                    'raw_page1': raw_page1_info
                }

                # Optionally embed colour-pair summary for page-1 so support
                # tickets can be diagnosed without rerunning the whole app.
                try:
                    pair_df_dbg, clusters_rgb_dbg = summarise_colour_pairs(page1_results)
                    if not pair_df_dbg.empty:
                        debug_package['colour_pairs'] = pair_df_dbg.to_dict(orient='records')
                        debug_package['colour_clusters'] = {str(cid): list(rgb) for cid, rgb in clusters_rgb_dbg.items()}
                except Exception as _dbg_col_err:
                    debug_package['colour_pairs_error'] = str(_dbg_col_err)

                debug_json = json.dumps(debug_package, indent=2)
                st.download_button("🐞 Download page-1 debug package", debug_json, file_name="debug_page1.json")

                # -------------------------------------------------------------
                # Offer outlined-PDF download (page-1 only) so the user can
                # inspect what mutool produced in Illustrator. Only show the
                # button if the preprocessing step actually changed the bytes
                # (which means mutool is present and succeeded).
                # -------------------------------------------------------------
                try:
                    with fitz.open(stream=uploaded_file.getvalue(), filetype="pdf") as _orig:
                        orig_first = _orig[0].get_text("rawdict")  # force parsing to ensure valid

                    # If the processed bytes differ from the original we assume
                    # stroke outlining succeeded.
                    outlined_bytes_differs = ENABLE_STROKE_OUTLINE and uploaded_file.getvalue() != file_bytes

                    if outlined_bytes_differs:
                        # Extract first page from *processed* bytes so we get
                        # the outlined shapes.
                        with fitz.open(stream=file_bytes, filetype="pdf") as _doc_proc:
                            single_page_doc = fitz.open()
                            single_page_doc.insert_pdf(_doc_proc, from_page=0, to_page=0)
                            buf = io.BytesIO()
                            single_page_doc.save(buf)
                            buf.seek(0)
                            st.download_button(
                                "📐 Download outlined page-1 (for Illustrator)",
                                buf.getvalue(),
                                file_name="page1_outlined.pdf",
                                mime="application/pdf"
                            )
                    else:
                        pass  # Hide this message
                except Exception as _outline_dbg_err:
                    st.info(f"Cannot offer outlined page export: {_outline_dbg_err}")
            except Exception:
                pass

    except Exception as e:
        st.error(f"Error processing PDF file: {str(e)}")

# ---------------------------------------------------------------------------
# Colour-pair summarisation and overview helpers (define ONCE, before all uses)
# ---------------------------------------------------------------------------

def rgb_to_hex(rgb):
    return '#{:02X}{:02X}{:02X}'.format(*rgb)

def export_colour_summary_excel(summary_df):
    """Export color pair summary to Excel with formatting.
    
    Parameters
    ----------
    summary_df : DataFrame
        Color pair summary with standardized columns
    """
    import io
    output = io.BytesIO()
    
    # Prepare data for Excel
    excel_df = summary_df.copy()
    excel_df = excel_df[[
        'text_hex', 'bg_hex',      # Hex codes
        'count',                    # Occurrence count
        'worst_ratio',             # Contrast ratios
        'best_ratio',
        'passes_aa',               # WCAG compliance
        'sample_text'              # Example text
    ]]
    
    # Write to Excel with formatting
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Write data
        excel_df.to_excel(
            writer, 
            sheet_name='Colour Summary',
            index=False,
            header=[
                'Text Color',        # text_hex
                'Background Color',  # bg_hex
                'Occurrences',       # count
                'Worst Ratio',       # worst_ratio
                'Best Ratio',        # best_ratio
                'WCAG AA Pass',      # passes_aa
                'Sample Text'        # sample_text
            ]
        )
        
        workbook = writer.book
        worksheet = writer.sheets['Colour Summary']
        
        # Column widths
        worksheet.set_column('A:A', 15)  # Text Color
        worksheet.set_column('B:B', 15)  # Background Color
        worksheet.set_column('C:C', 12)  # Occurrences
        worksheet.set_column('D:E', 12)  # Ratios
        worksheet.set_column('F:F', 12)  # WCAG AA
        worksheet.set_column('G:G', 50)  # Sample Text
        
        # Formats
        header_fmt = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'border': 1
        })
        num_fmt = workbook.add_format({'num_format': '0.00'})
        
        # Apply formats
        for col in ['D', 'E']:  # Ratio columns
            worksheet.set_column(f'{col}:{col}', 12, num_fmt)
            
        # Add color swatches
        for row, (_, data) in enumerate(excel_df.iterrows(), start=1):
            # Text color swatch
            text_fmt = workbook.add_format({
                'bg_color': data['text_hex'],
                'border': 1
            })
            worksheet.write(row, 0, data['text_hex'], text_fmt)
            
            # Background color swatch
            bg_fmt = workbook.add_format({
                'bg_color': data['bg_hex'],
                'border': 1
            })
            worksheet.write(row, 1, data['bg_hex'], bg_fmt)
        
        # Add autofilter
        worksheet.autofilter(0, 0, len(excel_df), len(excel_df.columns)-1)
        
    output.seek(0)
    return output.getvalue()

def summarise_colour_pairs(data, rgb_thresh=30):
    """Group similar foreground/background colours and aggregate stats.
    
    Parameters
    ----------
    data : DataFrame or list
        Input data containing color pairs and contrast information
    rgb_thresh : int
        RGB distance threshold for color clustering
        
    Returns
    -------
    summary : DataFrame
        Standardized color pair summary with consistent columns
    clusters : dict
        Mapping of cluster IDs to RGB values
    """
    import pandas as pd
    import numpy as np
    
    # Convert input to DataFrame with consistent column names
    if isinstance(data, pd.DataFrame):
        df = data.copy()
        if "color" in df.columns and "bgcolor" in df.columns:
            df = df.rename(columns={"color": "fg_rgb", "bgcolor": "bg_rgb"})
        if "fg_rgb" not in df.columns or "bg_rgb" not in df.columns:
            raise ValueError("DataFrame must have fg_rgb and bg_rgb columns")
    elif isinstance(data, list):
        rows = []
        for blk in data:
            fg = blk.get("color")
            bg = blk.get("bgcolor")
            if fg is None or bg is None:
                continue
            rows.append({
                "fg_rgb": fg,
                "bg_rgb": bg,
                "contrast_ratio": blk.get("contrast_ratio", 0.0),
                "text": blk.get("text", ""),
            })
        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(), {}
    else:
        raise ValueError("Input must be a DataFrame or list of dicts")

    # Convert RGB values to integers for clustering
    df["fg_int"] = df["fg_rgb"].apply(_rgb_float_to_int)
    df["bg_int"] = df["bg_rgb"].apply(_rgb_float_to_int)
    
    # Cluster similar colors
    def cluster_colors(arr):
        clusters = []
        labels = np.full(len(arr), -1)
        for i, color in enumerate(arr):
            found = False
            for j, c in enumerate(clusters):
                if np.linalg.norm(np.array(color) - np.array(c)) <= rgb_thresh:
                    labels[i] = j
                    found = True
                    break
            if not found:
                clusters.append(color)
                labels[i] = len(clusters) - 1
        return np.array(clusters), labels

    # Cluster FG and BG colors separately
    fg_arr = np.array(df["fg_int"].tolist())
    bg_arr = np.array(df["bg_int"].tolist())
    fg_clusters, fg_labels = cluster_colors(fg_arr)
    bg_clusters, bg_labels = cluster_colors(bg_arr)
    
    # Add cluster labels to DataFrame
    df["fg_cluster"] = fg_labels
    df["bg_cluster"] = bg_labels
    
    # Group by cluster pairs and aggregate stats
    summary = df.groupby(["fg_cluster", "bg_cluster"]).agg(
        text_rgb=("fg_int", "first"),  # Representative text color
        bg_rgb=("bg_int", "first"),    # Representative background color
        occurrences=("contrast_ratio", "count"),
        worst_ratio=("contrast_ratio", "min"),
        best_ratio=("contrast_ratio", "max"),
        sample_text=("text", lambda x: next((t for t in x if t), ""))  # First non-empty text
    ).reset_index()
    
    # Add hex codes and WCAG AA pass/fail
    summary["text_hex"] = summary["text_rgb"].apply(rgb_to_hex)
    summary["bg_hex"] = summary["bg_rgb"].apply(rgb_to_hex)
    summary["wcag_aa"] = summary["worst_ratio"] >= 4.5
    
    # Sort by worst contrast ratio (ascending) so failures appear first
    summary = summary.sort_values("worst_ratio")
    
    # Return standardized column names
    summary = summary.rename(columns={
        "text_rgb": "fg_rgb",
        "occurrences": "count",
        "wcag_aa": "passes_aa"
    })
    
    return summary, {i: tuple(rgb) for i, rgb in enumerate(fg_clusters)}

def _build_simple_pdf():
    """Return a fresh FPDF instance with sensible defaults."""
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(True, margin=20)
    pdf.set_margins(15, 20, 15)
    pdf.add_page()
    pdf.set_font('helvetica', '', 8)
    return pdf

def generate_colour_matrix_pdf(pair_df, clusters_rgb):
    """Create a one-page matrix PDF (bytes) visualising FG × BG clusters."""
    if pair_df.empty:
        return None

    fg_ids = sorted(pair_df["fg_cluster"].unique())
    bg_ids = sorted(pair_df["bg_cluster"].unique())

    pdf = _build_simple_pdf()

    cell = 8  # mm
    start_x = pdf.l_margin + cell  # leave top-left cell for labels
    start_y = pdf.t_margin + cell

    # Column labels (BG colours)
    pdf.set_font('helvetica', 'B', 6)
    for col_idx, bg_c in enumerate(bg_ids):
        bg_rgb = clusters_rgb[bg_c]
        x = start_x + col_idx * cell
        y = pdf.t_margin
        pdf.set_fill_color(*bg_rgb)
        pdf.rect(x, y, cell, cell, 'F')
    # Row labels (FG colours)
    for row_idx, fg_c in enumerate(fg_ids):
        fg_rgb = clusters_rgb[fg_c]
        x = pdf.l_margin
        y = start_y + row_idx * cell
        pdf.set_fill_color(*fg_rgb)
        pdf.rect(x, y, cell, cell, 'F')

    pdf.set_font('helvetica', '', 6)
    # Matrix cells
    for row_idx, fg_c in enumerate(fg_ids):
        for col_idx, bg_c in enumerate(bg_ids):
            x = start_x + col_idx * cell
            y = start_y + row_idx * cell
            pair = pair_df[(pair_df['fg_cluster'] == fg_c) & (pair_df['bg_cluster'] == bg_c)]
            if pair.empty:
                continue
            bg_rgb = clusters_rgb[bg_c]
            fg_rgb = clusters_rgb[fg_c]
            ratio = pair.iloc[0]['worst_ratio']

            pdf.set_fill_color(*bg_rgb)
            pdf.rect(x, y, cell, cell, 'F')

            # Draw "T" or dot to indicate presence
            pdf.set_text_color(*fg_rgb)
            pdf.set_xy(x, y)
            pdf.cell(cell, cell, 'T', align='C')

            # Border highlight if AA fails
            if ratio < 4.5:
                pdf.set_draw_color(255, 0, 0)
                pdf.rect(x, y, cell, cell)

    pdf.set_text_color(0)
    pdf.set_draw_color(0)

    try:
        pdf_bytes = pdf.output(dest='S')
        return bytes(pdf_bytes) if isinstance(pdf_bytes, (bytes, bytearray)) else pdf_bytes.encode('latin1')
    except UnicodeEncodeError:
        # If encoding fails, create a fallback PDF
        pdf_fallback = _build_simple_pdf()
        pdf_fallback.set_font('helvetica', 'B', 12)
        pdf_fallback.cell(0, 8, 'Colour Matrix', ln=True)
        pdf_fallback.ln(2)
        pdf_fallback.set_font('helvetica', '', 10)
        pdf_fallback.cell(0, 8, 'Error: Unicode encoding issue prevented matrix generation.', ln=True)
        fallback_bytes = pdf_fallback.output(dest='S')
        return bytes(fallback_bytes) if isinstance(fallback_bytes, (bytes, bytearray)) else fallback_bytes.encode('latin1')

def generate_swatch_overview_pdf(pair_df):
    """Generate a compact table-style PDF listing each colour pair.
    
    Parameters
    ----------
    pair_df : DataFrame
        Color pair summary with standardized columns
    """
    pdf = _build_simple_pdf()
    pdf.set_font('helvetica', 'B', 12)
    pdf.cell(0, 8, 'Colour Pair Overview', ln=True)
    pdf.ln(2)

    # Table headers
    headers = [
        'Text Color',
        'Background',
        'Count',
        'Contrast',
        'WCAG AA',
        'Sample Text'
    ]
    col_w = [20, 20, 15, 15, 15, 100]  # Column widths in mm
    
    # Header row
    pdf.set_font('helvetica', 'B', 8)
    for h, w in zip(headers, col_w):
        pdf.cell(w, 6, h, 1, 0, 'C')
    pdf.ln()

    # Data rows
    pdf.set_font('helvetica', '', 7)
    for _, row in pair_df.iterrows():
        # Text color swatch + hex
        pdf.set_fill_color(*row['fg_rgb'])
        pdf.cell(col_w[0], 5, row['text_hex'], 1, 0, 'C', True)
        
        # Background color swatch + hex
        pdf.set_fill_color(*row['bg_rgb'])
        pdf.cell(col_w[1], 5, row['bg_hex'], 1, 0, 'C', True)
        
        # Count
        pdf.cell(col_w[2], 5, str(row['count']), 1, 0, 'C')
        
        # Contrast ratio
        ratio_text = f"{row['worst_ratio']:.2f}"
        if row['best_ratio'] > row['worst_ratio']:
            ratio_text += f" - {row['best_ratio']:.2f}"
        pdf.cell(col_w[3], 5, ratio_text, 1, 0, 'C')
        
        # WCAG AA status
        pdf.cell(col_w[4], 5, "Pass" if row['passes_aa'] else "Fail", 1, 0, 'C')
        
        # Sample text (truncated if needed)
        txt = clean_text_for_pdf(row['sample_text'])
        if len(txt) > 50:
            txt = txt[:47] + '...'
        
        # Extra safety: ensure the text can be encoded in latin-1
        try:
            txt.encode('latin-1')
        except UnicodeEncodeError:
            # If text still contains problematic characters, replace them
            txt = txt.encode('ascii', errors='replace').decode('ascii')
        
        pdf.cell(col_w[5], 5, txt, 1, 0)
        pdf.ln()

    try:
        pdf_bytes = pdf.output(dest='S')
        return bytes(pdf_bytes) if isinstance(pdf_bytes, (bytes, bytearray)) else pdf_bytes.encode('latin1')
    except UnicodeEncodeError as e:
        # If there's still an encoding error, create a minimal PDF with error message
        pdf_fallback = _build_simple_pdf()
        pdf_fallback.set_font('helvetica', 'B', 12)
        pdf_fallback.cell(0, 8, 'Colour Pair Overview', ln=True)
        pdf_fallback.ln(2)
        pdf_fallback.set_font('helvetica', '', 10)
        pdf_fallback.cell(0, 8, 'Error: Could not encode some Unicode characters in the data.', ln=True)
        pdf_fallback.cell(0, 8, 'Please try exporting to Excel or CSV format instead.', ln=True)
        fallback_bytes = pdf_fallback.output(dest='S')
        return bytes(fallback_bytes) if isinstance(fallback_bytes, (bytes, bytearray)) else fallback_bytes.encode('latin1')

# ---------------------------------------------------------------------------
# Utility: Hex to RGB (for colour swatches, etc.)
# ---------------------------------------------------------------------------
def hex_to_rgb(hex_color):
    """Convert hex string (e.g. '#AABBCC' or 'AABBCC') to (r, g, b) tuple."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join([c*2 for c in hex_color])
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def _rgb_float_to_int(rgb_f):
    """Convert an (r,g,b) triple of floats 0–1 to ints 0–255."""
    return tuple(max(0, min(255, int(round(c * 255)))) for c in rgb_f)

# Generate colour-pair summary table for download (CSV)
pair_df, clusters_rgb = None, None
if "contrast_df" in st.session_state and not st.session_state["contrast_df"].empty:
    try:
        pair_df, clusters_rgb = summarise_colour_pairs(st.session_state["contrast_df"])
    except Exception as e:
        pair_df, clusters_rgb = None, None

if pair_df is not None and not pair_df.empty:
    import io
    csv_buf = io.StringIO()
    pair_df.to_csv(csv_buf, index=False)
    csv_buf.seek(0)
    with col1:
        st.download_button(
            "🟦 Download Colour-pair Summary (CSV)",
            csv_buf.getvalue(),
            file_name="colour_pair_summary.csv",
            mime="text/csv"
        )

# Show page previews with contrast overlay if enabled
if show_heatmap:
    with st.expander("Page Previews with Contrast Overlay", expanded=True):
        st.markdown("""
            🟩 Green: Passes WCAG AAA  
            🟨 Yellow: Passes WCAG AA  
            🟥 Red: Fails WCAG AA
        """)
        preview_container = st.container()
        _, col, _ = st.columns([0.15, 0.7, 0.15])
        if st.session_state.get('text_blocks_by_page'):
            preview_progress = st.progress(0, text="Generating previews...")
            total_previews = len(st.session_state['text_blocks_by_page'])
            for idx, (page_num, text_blocks) in enumerate(st.session_state['text_blocks_by_page'].items()):
                progress = (idx + 1) / total_previews
                preview_progress.progress(progress, f"Generating preview {idx + 1} of {total_previews}")
                with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                    page = doc[page_num]
                    try:
                        overlay_image = create_contrast_overlay(page, text_blocks)
                        with col:
                            st.image(overlay_image, caption=f"Page {page_num + 1}", width='stretch')
                    except Exception as preview_err:
                        st.write(f"Preview error on page {page_num+1}: {preview_err}")
            preview_progress.empty()

with st.expander('Colour-pair summary table', expanded=True):
    st.subheader('Colour-pair summary table')
    
    # Get summary data
    summary_df = None
    if "contrast_df" in st.session_state and not st.session_state["contrast_df"].empty:
        summary_df, _ = summarise_colour_pairs(st.session_state["contrast_df"])
    
    # Filter options
    show_fails_only = st.checkbox('Show only failing colour pairs', value=False, key='show_fails_only_summary')
    
    # Display table
    filtered_df = summary_df.copy() if summary_df is not None else None
    if filtered_df is not None:
        if show_fails_only:
            filtered_df = filtered_df[~filtered_df['passes_aa']]
            
        if filtered_df.empty:
            st.info('No failing colour pairs found.' if show_fails_only else 'No colour-pair statistics available for this document.')
        else:
            # Prepare display columns
            display_df = filtered_df[[
                'text_hex',      # Text color hex
                'bg_hex',        # Background color hex
                'count',         # Occurrences
                'worst_ratio',   # Contrast ratios
                'best_ratio',
                'passes_aa',     # WCAG compliance
                'sample_text'    # Example text
            ]].copy()
            
            # Rename columns for display
            display_df.columns = [
                'Text Color',
                'Background Color',
                'Occurrences',
                'Worst Ratio',
                'Best Ratio',
                'WCAG AA Pass',
                'Sample Text'
            ]
            
            # Show the table
            st.dataframe(display_df)
            
            # Add download buttons in columns
            col1, col2, col3 = st.columns(3)
            
            # Excel export
            with col1:
                excel_bytes = export_colour_summary_excel(filtered_df)
                st.download_button(
                    "📊 Download Excel Summary",
                    excel_bytes,
                    file_name="colour_summary.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            # PDF Swatch Overview export
            with col2:
                pdf_bytes = generate_swatch_overview_pdf(filtered_df)
                st.download_button(
                    "🎨 Download PDF Overview",
                    pdf_bytes,
                    file_name="colour_overview.pdf",
                    mime="application/pdf"
                )
            
            # CSV export
            with col3:
                csv_buf = io.StringIO()
                display_df.to_csv(csv_buf, index=False)
                csv_buf.seek(0)
                st.download_button(
                    "📄 Download CSV Summary",
                    csv_buf.getvalue(),
                    file_name="colour_summary.csv",
                    mime="text/csv"
                )
    else:
        st.info('No colour-pair statistics available. Please upload a PDF document to analyze.')

# =====================================================================================
# MEMORY CLEANUP: Clear detailed data after all UI has been rendered
# =====================================================================================
# After all reports, displays, and exports are generated, we can optionally
# clear detailed data to free memory. The data is kept during the session for
# user interaction, but will be automatically cleared when:
# 1. A new file is uploaded (already implemented)
# 2. User clicks "Clear All Analysis Data" button (already implemented)
# 3. Session ends
#
# Note: We keep summary_stats (lightweight) for reference, but detailed
# contrast_results, text_blocks_by_page, and contrast_df are cleared on new file upload.