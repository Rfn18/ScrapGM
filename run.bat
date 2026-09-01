@echo off
echo ==============================================
echo 🚀 Memulai MScrape: Google Maps Scraper...
echo ==============================================

echo [1/3] Memeriksa dan menginstal library yang dibutuhkan...
pip install -r requirements.txt
echo [2/3] Menginstal Chromium untuk Playwright...
playwright install chromium

echo.
echo [3/3] Menjalankan Aplikasi Web...
cd GoogleMaps-Lead-Scraper
streamlit run app.py
pause
