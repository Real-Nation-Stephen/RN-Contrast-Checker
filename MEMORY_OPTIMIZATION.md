# Memory Optimization Guide

## Problem
The app was experiencing memory crashes on Streamlit Cloud due to:
- Large PDF analysis results stored in session state
- Data accumulating across multiple file uploads
- No cleanup mechanism for old data
- Duplicate data structures being created

## Solutions Implemented

### 1. Automatic Memory Cleanup ✅
- **What it does**: Automatically clears old analysis data when a new file is uploaded
- **Location**: Triggered when file hash changes (line ~1999)
- **Benefit**: Prevents memory buildup from multiple file analyses in the same session

### 2. Manual Clear Button ✅
- **What it does**: Adds a "Clear All Analysis Data" button in the sidebar
- **Location**: Sidebar under "Memory Settings"
- **Benefit**: Users can manually free memory at any time

### 3. Google Sheets Archive (Optional) ✅
- **What it does**: Optionally saves analysis results to Google Sheets as a backup/archive
- **Location**: Toggle in sidebar "Use Google Sheets for data storage"
- **Benefit**: 
  - Creates a backup of results outside of memory
  - Can be used for historical tracking
  - Reduces reliance on session state for long-term storage

### 4. Optimized Data Storage ✅
- **What it does**: Prevents unnecessary rebuilding of `text_blocks_by_page`
- **Location**: Line ~2030
- **Benefit**: Eliminates duplicate data structures, reducing memory footprint

## Usage Recommendations

### For Streamlit Cloud Deployment

1. **Enable Google Sheets Storage** (Recommended)
   - Toggle "Use Google Sheets for data storage" in the sidebar
   - This creates backups and reduces memory pressure
   - Results are still kept in memory for current session display

2. **Clear Data Between Large Files**
   - Use the "Clear All Analysis Data" button after processing large PDFs
   - This frees memory before processing the next file

3. **Monitor Memory Usage**
   - Streamlit Cloud shows memory usage in the dashboard
   - If you see warnings, use the clear button more frequently

### For Local Development

- Memory is less of a concern locally (your machine's RAM is the limit)
- You can disable Google Sheets storage if you don't need archiving
- The automatic cleanup still works and helps with performance

## Technical Details

### Memory Cleanup Function
```python
def clear_analysis_data():
    """Clear all analysis-related data from session state to free memory"""
    data_keys = [
        'contrast_results',
        'pdf_results', 
        'text_blocks_by_page',
        'contrast_df',
        'current_file_hash'
    ]
    for key in data_keys:
        if key in st.session_state:
            del st.session_state[key]
    import gc
    gc.collect()
```

### When Cleanup Happens
- Automatically when a new file (different hash) is uploaded
- Manually when user clicks "Clear All Analysis Data" button
- On logout (authentication data is cleared)

### Google Sheets Integration
- Creates a sheet named "RN_Contrast_Checker_Results"
- Each analysis gets its own worksheet named "Results_{hash}"
- Requires Google Service Account credentials in secrets.toml
- Falls back to session state if sheets save fails

## Future Improvements (Optional)

1. **Streaming Results**: Process and display results page-by-page instead of storing all at once
2. **Compression**: Compress large data structures before storing in session state
3. **Pagination**: Only load current page's data into memory
4. **Database Backend**: Use a proper database (SQLite, PostgreSQL) instead of session state
5. **Result Expiration**: Automatically clear results older than X minutes

## Monitoring

To monitor memory usage on Streamlit Cloud:
1. Go to your app's dashboard
2. Check the "Memory" section
3. Look for warnings or errors
4. Use clear button if memory usage is high

## Troubleshooting

### Still Getting Memory Errors?

1. **Check file sizes**: Very large PDFs (>100MB) may still cause issues
2. **Process one file at a time**: Don't upload multiple files in quick succession
3. **Use Google Sheets**: Enable the archive feature to offload data
4. **Clear frequently**: Use the clear button after each analysis
5. **Consider upgrading**: Streamlit Cloud Pro has higher memory limits

### Google Sheets Not Working?

1. Check that secrets.toml has valid Google Service Account credentials
2. Verify the service account has access to Google Sheets API
3. Check that the sheet "RN_Contrast_Checker_Results" exists or can be created
4. Look for error messages in the app - it will fall back to session state if sheets fails

