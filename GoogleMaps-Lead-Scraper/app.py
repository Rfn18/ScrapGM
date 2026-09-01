import streamlit as st
import pandas as pd
import io
import time
import random
import asyncio
import sys

# Fix Playwright NotImplementedError on Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from utils.constants import COUNTRY_CITIES, DEFAULT_EMAIL_BLACKLIST, DEFAULT_CHAIN_KEYWORDS
from utils.text_helpers import normalize_country_name, is_chain, is_blacklisted_email
from core.scraper import playwright_scrape_single

# Inisialisasi blacklists di session state jika belum ada
if "email_blacklist" not in st.session_state:
    st.session_state.email_blacklist = DEFAULT_EMAIL_BLACKLIST.copy()

if "chain_blacklist" not in st.session_state:
    st.session_state.chain_blacklist = list(DEFAULT_CHAIN_KEYWORDS)

# --- UI SETUP ---
st.set_page_config(page_title="MScrape", layout="wide", page_icon="🚀")
st.title("🚀 G-Maps Scraper (Global + Target Total)")

with st.sidebar:
    st.header("📍 Konfigurasi")
    
    # Tab untuk konfigurasi utama dan filter
    tab1, tab2 = st.tabs(["🔧 Main Settings", "🚫 Filter Settings"])
    
    with tab1:
        keyword_input = st.text_area(
            "Niche Variations (satu per baris)",
            value="cafe\ncoffee shop",
            help="Gunakan variasi untuk dapat lebih banyak data!"
        )
        country = st.text_input("Country", "United States")
        
        extract_email = st.checkbox(
            "🔍 Cari Email di Website (Add-on)",
            value=False,
            help="Email hanya ditemukan di ~15–30% website. Proses lebih lama."
        )
        
        scrape_mode = st.radio("Mode Scraping", ["Satu Kota", "Target Total (Seluruh Negara)"])
        
        if scrape_mode == "Satu Kota":
            location = st.text_input("City", "New York")
            max_res_per_city = st.number_input(
                "Jumlah Data per Kota",
                min_value=1,
                max_value=200,
                value=20,
                step=10,
                help="Google Maps biasanya hanya menampilkan 60–80 listing."
            )
        else:
            total_target = st.number_input(
                "Target Total Data",
                min_value=10,
                value=1000,
                step=100
            )
            max_per_city = st.number_input(
                "Maks Data per Kota",
                min_value=10,
                max_value=100,
                value=60,
                step=10,
                help="Disarankan 60–80 agar sesuai kapasitas Google Maps."
            )
            
            use_builtin = st.checkbox("Gunakan daftar kota bawaan", value=True)
            if not use_builtin:
                cities_input = st.text_area(
                    "Daftar Kota (satu per baris)",
                    value="New York\nLos Angeles\nChicago\nHouston\nPhoenix",
                    height=150
                )
    
    with tab2:
        st.subheader("📧 Email Blacklist")
        st.caption("Email yang mengandung kata-kata berikut akan diabaikan")
        email_blacklist_input = st.text_area(
            "Email Blacklist Patterns (satu per baris)",
            value="\n".join(DEFAULT_EMAIL_BLACKLIST),
            height=200,
            help="Contoh: info@, contact@, support@"
        )
        
        st.subheader("🏪 Chain Restaurant Blacklist")
        st.caption("Restoran yang mengandung kata-kata berikut akan diabaikan")
        chain_blacklist_input = st.text_area(
            "Chain Keywords Blacklist (satu per baris)",
            value="\n".join(sorted(DEFAULT_CHAIN_KEYWORDS)),
            height=250,
            help="Contoh: mcdonald, starbucks, kfc"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Reset ke Default", use_container_width=True):
                st.session_state.email_blacklist = DEFAULT_EMAIL_BLACKLIST.copy()
                st.session_state.chain_blacklist = list(DEFAULT_CHAIN_KEYWORDS)
                st.success("Filter direset ke default!")
                st.rerun()
        
        with col2:
            if st.button("💾 Simpan Filter", use_container_width=True):
                email_patterns = [p.strip() for p in email_blacklist_input.split("\n") if p.strip()]
                chain_keywords = [k.strip() for k in chain_blacklist_input.split("\n") if k.strip()]
                
                st.session_state.email_blacklist = email_patterns
                st.session_state.chain_blacklist = chain_keywords
                st.success("Filter disimpan!")
                st.rerun()

    st.divider()
    
    btn_run = st.button("Gas Scrape Sekarang! 🔥", use_container_width=True)

    if st.button("🗑️ Clear Cache Lokasi", use_container_width=True):
        st.session_state.geocode_cache = {}
        st.success("Cache dibersihkan!")

# --- RUN SCRAPE ---
if btn_run:
    email_blacklist = st.session_state.email_blacklist
    chain_blacklist = st.session_state.chain_blacklist
    
    st.sidebar.success(f"✅ Filter aktif: {len(email_blacklist)} email patterns, {len(chain_blacklist)} chain keywords")
    
    keywords = [k.strip() for k in keyword_input.split("\n") if k.strip()]
    if not keywords or not country.strip():
        st.warning("⚠️ Isi minimal satu niche dan negara!")
    else:
        normalized_country = normalize_country_name(country)
        all_results = []

        if scrape_mode == "Satu Kota":
            if not location.strip():
                st.warning("⚠️ Isi City!")
            else:
                with st.spinner(f"🔍 Scraping di {location}, {country}..."):
                    for kw in keywords:
                        if len(all_results) >= 1000:
                            break
                        final_data = playwright_scrape_single(kw, location, country, max_res_per_city // len(keywords) or 1, extract_email, email_blacklist, chain_blacklist)
                        all_results.extend(final_data)
        else:
            if use_builtin:
                cities = COUNTRY_CITIES.get(normalized_country)
                if not cities:
                    st.error(f"❌ Negara '{country}' belum didukung untuk daftar bawaan.")
                    st.info("Saat ini mendukung: Indonesia, United States, India, Brazil, France, Germany, United Kingdom.")
                    st.stop()
            else:
                cities = [c.strip() for c in cities_input.split("\n") if c.strip()]
                if not cities:
                    st.error("⚠️ Daftar kota kosong!")
                    st.stop()

            st.info(f"🌍 Akan scrape {len(cities)} kota di {country} sampai target {total_target} data tercapai.")
            st.info(f"🛡️ Filter aktif: {len(email_blacklist)} pola email, {len(chain_blacklist)} keyword chain")
            if extract_email:
                st.warning("📧 Email extraction aktif — proses akan lebih lama & hasil email tergantung website.")
            
            all_results = []
            progress_bar = st.progress(0)
            status_text = st.empty()

            for city in cities:
                if len(all_results) >= total_target:
                    break
                for kw in keywords:
                    if len(all_results) >= total_target:
                        break
                    needed = total_target - len(all_results)
                    limit = min(max_per_city, needed, 50)

                    status_text.write(f"📍 {city} | {kw} (butuh {needed} lagi)...")
                    city_data = playwright_scrape_single(kw, city, country, limit, extract_email, email_blacklist, chain_blacklist)
                    all_results.extend(city_data)

                    progress_pct = min(len(all_results) / total_target, 1.0)
                    progress_bar.progress(progress_pct)
                    time.sleep(random.uniform(1, 2))

            status_text.write("✅ Target tercapai atau semua kota selesai!")

        if all_results:
            df = pd.DataFrame(all_results)
            df.drop_duplicates(subset=["Business Name", "Full Address"], keep="first", inplace=True)
            df = df.head(total_target if scrape_mode == "Target Total" else len(df))
            df.reset_index(drop=True, inplace=True)

            chain_filtered_count = sum(1 for name in df["Business Name"] if is_chain(name, chain_blacklist))
            email_filtered_count = sum(1 for email in df["Emails"] if is_blacklisted_email(email, email_blacklist))
            
            st.success(f"🏆 Total {len(df)} data unik siap cair!")
            st.info(f"📊 Statistik Filter: {chain_filtered_count} chain diabaikan, {email_filtered_count} email di-blacklist")
            
            st.dataframe(df, use_container_width=True)

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)

            filename_prefix = f"Leads_{country.replace(' ', '_')}"
            st.download_button(
                label="📥 Download Excel",
                data=output.getvalue(),
                file_name=f"{filename_prefix}_{len(df)}_leads.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("ℹ️ Tidak ada data ditemukan.")
