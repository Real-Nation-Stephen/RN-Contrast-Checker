# Quick Start Guide

## 🚀 Running Locally (Right Now)

### Mac/Linux:
```bash
./run_local.sh
```

### Windows:
```bash
run_local.bat
```

That's it! The script will:
- Set up everything automatically
- Install dependencies
- Start the app
- Open it in your browser

The app will be available at `http://localhost:8501`

---

## 💾 Memory Optimization Features

### New Features Added:

1. **Automatic Cleanup** ✅
   - Old data is automatically cleared when you upload a new file
   - Prevents memory buildup

2. **Manual Clear Button** ✅
   - Look in the sidebar for "Memory Settings"
   - Click "Clear All Analysis Data" to free memory anytime

3. **Google Sheets Archive** ✅ (Optional)
   - Toggle "Use Google Sheets for data storage" in sidebar
   - Saves results to Google Sheets as backup
   - Helps reduce memory pressure on Streamlit Cloud

4. **Optimized Storage** ✅
   - Eliminated duplicate data structures
   - More efficient memory usage

---

## 📋 For Streamlit Cloud Deployment

### Recommended Settings:

1. **Enable Google Sheets Storage**
   - Go to sidebar → Memory Settings
   - Check "Use Google Sheets for data storage"
   - This creates backups and reduces memory usage

2. **Clear Data Regularly**
   - After processing large PDFs, click "Clear All Analysis Data"
   - This prevents memory from accumulating

3. **Monitor Memory**
   - Check Streamlit Cloud dashboard for memory usage
   - Use clear button if you see warnings

---

## 🔧 Troubleshooting

### Port Already in Use?
```bash
streamlit run rn_contrast_checker_app.py --server.port 8502
```

### Authentication Issues?
- For local testing, you can temporarily disable authentication
- Or set up `.streamlit/secrets.toml` with your Google credentials

### Still Having Memory Issues?
1. Enable Google Sheets storage
2. Clear data after each large file
3. Process one file at a time
4. Consider upgrading Streamlit Cloud plan

---

## 📚 More Information

- **Local Run Details**: See `LOCAL_RUN_INSTRUCTIONS.md`
- **Memory Optimization**: See `MEMORY_OPTIMIZATION.md`
- **Full Documentation**: See `README.md`

---

## ✅ What's Fixed

- ✅ Automatic memory cleanup when new file uploaded
- ✅ Manual clear button for freeing memory
- ✅ Google Sheets integration for archiving results
- ✅ Optimized data storage (no duplicates)
- ✅ Local run scripts for easy setup
- ✅ Better memory management overall

The app should now run much more reliably on Streamlit Cloud without memory crashes!

