# Deployment Guide - Streamlit Cloud

This guide walks you through deploying the RN Contrast Checker to Streamlit Cloud.

## Prerequisites

1. **GitHub Account**: Your code should be in a GitHub repository
2. **Google Cloud Account**: For Google Sheets authentication
3. **Streamlit Cloud Account**: Free at [share.streamlit.io](https://share.streamlit.io/)

## Step 1: Prepare Your Repository

Ensure your repository has these files:
- `rn_contrast_checker_app.py` - Main application
- `requirements.txt` - Dependencies
- `assets/` folder with all image and font files
- `.streamlit/config.toml` - Streamlit configuration
- `README.md` - Documentation

**DO NOT** include:
- `.streamlit/secrets.toml` - This contains sensitive data
- `contrast_auth.json` - Service account credentials
- Backup folders or files

## Step 2: Set Up Google Service Account

### 2.1 Create Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the **Google Sheets API**
4. Navigate to **IAM & Admin** > **Service Accounts**
5. Click **Create Service Account**
6. Fill in service account details and create
7. Click on the created service account
8. Go to **Keys** tab > **Add Key** > **Create New Key**
9. Choose **JSON** format and download

### 2.2 Extract Required Information

From the downloaded JSON file, you'll need:
- `private_key_id`
- `private_key` (entire block including begin/end lines)
- `client_id`
- `project_id`
- `client_email`

### 2.3 Set Up Google Sheet

1. Create a Google Sheet with these columns:
   - **Column A**: `Name` (user full names)
   - **Column B**: `Email` (user email addresses)
   - **Column C**: `Password` (plain text passwords)
   - **Column D**: `Profile Image` (URLs to profile images)

2. Share the sheet with your service account email (found in the JSON file)
3. Give **Editor** permissions
4. Copy the Google Sheet ID from the URL

## Step 3: Deploy to Streamlit Cloud

### 3.1 Connect Repository

1. Go to [share.streamlit.io](https://share.streamlit.io/)
2. Sign in with GitHub
3. Click **New app**
4. Select your repository
5. Choose `rn_contrast_checker_app.py` as the main file
6. Click **Deploy**

### 3.2 Configure Secrets

1. In your app dashboard, click **Settings** (gear icon)
2. Click **Secrets**
3. Add the following secrets (replace with your actual values):

```toml
# Google Service Account Credentials
private_key_id = "your_private_key_id_here"
private_key = """-----BEGIN PRIVATE KEY-----
YOUR_COMPLETE_PRIVATE_KEY_HERE
-----END PRIVATE KEY-----"""
client_id = "your_client_id_here"
project_id = "your_project_id_here"
client_email = "your_service_account_email_here"

# Google Sheet Configuration (optional)
# sheet_id = "your_google_sheet_id_here"
```

**Important Notes:**
- Keep the triple quotes around the private key
- Include the complete private key with BEGIN/END lines
- Don't add extra spaces or formatting

### 3.3 Test Deployment

1. Wait for deployment to complete
2. Click **Open app** to test
3. Try logging in with a user from your Google Sheet
4. Upload a test PDF to verify functionality

## Step 4: Custom Domain (Optional)

1. Purchase a domain name
2. In Streamlit Cloud settings, go to **General**
3. Add your custom domain
4. Update your DNS settings as instructed

## Troubleshooting

### Common Issues

**Authentication Errors:**
- Double-check all secrets are correctly formatted
- Ensure Google Sheet is shared with service account email
- Verify Google Sheets API is enabled

**File Upload Issues:**
- Check file size limits in config.toml
- Ensure assets folder is included in repository

**Missing Assets:**
- Verify all files in assets/ folder are committed to repository
- Check file paths are relative (not absolute)

**Deployment Failures:**
- Check requirements.txt for correct package versions
- Review logs in Streamlit Cloud dashboard
- Ensure no local file dependencies

### Debug Mode

To enable debug logging, add this to your secrets:

```toml
# Debug configuration
debug_mode = true
```

## Security Best Practices

1. **Never commit secrets** to your repository
2. **Use strong passwords** in your Google Sheet
3. **Regularly rotate** service account keys
4. **Monitor access logs** in Google Cloud Console
5. **Use HTTPS** for profile image URLs

## Performance Optimization

1. **Image Optimization**: Compress profile images to reduce load times
2. **Caching**: Streamlit automatically caches function results
3. **Resource Limits**: Monitor CPU and memory usage in Streamlit Cloud

## Backup and Recovery

1. **Google Sheet Backup**: Regularly export your user data
2. **Code Backup**: Keep your repository up to date
3. **Service Account**: Keep backup copies of your service account keys

## Support

For deployment issues:
- Check Streamlit Cloud [documentation](https://docs.streamlit.io/streamlit-community-cloud)
- Review app logs in the Streamlit Cloud dashboard
- Contact Streamlit support through their community forum

For authentication issues:
- Verify Google Cloud Console configuration
- Check Google Sheets API quotas and usage
- Review service account permissions 