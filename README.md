# RN Contrast Checker

A professional Streamlit web application for analyzing color contrast compliance in PDF documents according to WCAG 2.1 guidelines.

![RN Contrast Checker](assets/logo%20studio.png)

## Features

### 🎯 **Core Functionality**
- **PDF Contrast Analysis**: Automatically detects and analyzes text-background color combinations
- **WCAG 2.1 Compliance**: Evaluates contrast ratios against AA and AAA standards
- **Visual Heatmaps**: Color-coded overlay showing contrast issues across PDF pages
- **Multiple Export Formats**: Generate detailed reports in PDF and CSV formats

### 🔐 **Authentication System**
- **Google Sheets Integration**: User management through Google Sheets
- **Profile Images**: Dynamic user avatars from Google Drive or GitHub
- **Secure Login**: Password-protected access with user profiles

### 📊 **Analysis Capabilities**
- **Text Size Detection**: Identifies large vs normal text for appropriate thresholds
- **Pixel Sampling**: Advanced background color detection using rasterized content
- **Metadata Parsing**: Extracts color information from PDF structure
- **Bounding Box Visualization**: Shows exact locations of contrast issues

### 🎨 **Professional UI**
- **Studio Mode**: Clean, professional interface design
- **Responsive Layout**: Works seamlessly on desktop and tablet devices
- **Theme Awareness**: Supports light and dark themes
- **Custom Branding**: Purple accent colors (#2b1e66) for consistent brand identity

## Quick Start

### Local Development

1. **Clone the repository:**
   ```bash
   git clone https://github.com/[your-username]/rn-contrast-checker.git
   cd rn-contrast-checker
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up Google Sheets authentication:**
   - Create a Google Service Account
   - Download the credentials JSON file
   - Add credentials to `.streamlit/secrets.toml` (see setup section below)

4. **Run the application:**
   ```bash
   streamlit run rn_contrast_checker_app.py
   ```

### Streamlit Cloud Deployment

1. **Fork/Upload** this repository to GitHub
2. **Connect** your GitHub account to [Streamlit Cloud](https://share.streamlit.io/)
3. **Deploy** by selecting your repository
4. **Configure secrets** in the Streamlit Cloud dashboard (see secrets section below)

## Configuration

### Google Sheets Setup

1. **Create a Google Service Account:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing
   - Enable Google Sheets API
   - Create service account credentials

2. **Set up user management sheet:**
   - Create a Google Sheet with columns: `Name`, `Email`, `Password`, `Profile Image`
   - Share the sheet with your service account email (Editor permissions)

3. **Configure secrets** in `.streamlit/secrets.toml`:
   ```toml
   private_key_id = "your_private_key_id"
   private_key = """-----BEGIN PRIVATE KEY-----
   your_private_key_content
   -----END PRIVATE KEY-----"""
   client_id = "your_client_id"
   project_id = "your_project_id"
   client_email = "your_service_account_email"
   ```

## File Structure

```
rn-contrast-checker/
├── rn_contrast_checker_app.py    # Main application file
├── requirements.txt               # Python dependencies
├── README.md                     # This file
├── .gitignore                    # Git ignore rules
├── assets/                       # Static assets
│   ├── logo studio.png          # Studio mode logo
│   ├── logo sparkle.png         # Theme-aware logo
│   ├── Contrast Checker Icon.png # App icon
│   └── *.ttf                    # Font files
└── .streamlit/
    ├── config.toml              # Streamlit configuration
    └── secrets.toml             # Authentication secrets (not in repo)
```

## Dependencies

- **Streamlit** (>=1.31.0) - Web application framework
- **PyMuPDF** (>=1.23.0) - PDF processing and text extraction
- **Pillow** (>=11.2.1) - Image processing for pixel sampling
- **colormath** (>=3.0.0) - Color space conversions and contrast calculations
- **gspread** (>=5.12.0) - Google Sheets integration
- **google-auth** (>=2.23.0) - Google API authentication
- **pandas** (>=2.2.2) - Data manipulation for reports
- **numpy** (>=2.2.6) - Numerical operations
- **matplotlib** (>=3.10.3) - Visualization
- **fpdf** (>=1.7.2) - PDF report generation

## Usage

### 1. **Login**
- Select your name from the dropdown
- Enter your password
- Click "Sign In"

### 2. **Upload PDF**
- Drag and drop a PDF file or click to browse
- Supported formats: PDF files up to 200MB

### 3. **Analysis**
- The app automatically processes your PDF
- View real-time progress updates
- Review contrast analysis results

### 4. **Results**
- **Summary**: Overview of contrast issues found
- **Heatmap**: Visual overlay showing problem areas
- **Details Table**: Comprehensive list of all text elements
- **Reports**: Export results as PDF or CSV

### 5. **Export Options**
- **PDF Report**: Professional summary with recommendations
- **CSV Data**: Detailed data for further analysis
- **Color Matrix**: Visual representation of color combinations

## WCAG 2.1 Standards

The application evaluates contrast ratios according to:

- **AA Standard**: Minimum 4.5:1 for normal text, 3:1 for large text
- **AAA Standard**: Minimum 7:1 for normal text, 4.5:1 for large text
- **Large Text**: 18pt+ or 14pt+ bold text

## Technical Details

### Contrast Analysis Engine
- **Color Detection**: Multi-method approach using PDF metadata and pixel sampling
- **Text Classification**: Automatic font size analysis for appropriate thresholds
- **Fallback Systems**: Robust error handling with multiple detection methods
- **Unicode Support**: Handles international characters and special symbols

### Performance
- **Efficient Processing**: Optimized for large PDF files
- **Memory Management**: Streaming processing to handle large documents
- **Caching**: Smart caching to improve repeat analysis performance

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Support

For support, email [your-email] or create an issue in this repository.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Built with ❤️ by Real Nation** 