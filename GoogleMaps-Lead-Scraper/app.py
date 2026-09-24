import streamlit as st
import pandas as pd
import io
import concurrent.futures
import asyncio
import sys

# Fix Playwright NotImplementedError on Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from utils.constants import COUNTRY_CITIES, DEFAULT_EMAIL_BLACKLIST, DEFAULT_CHAIN_KEYWORDS
from utils.text_helpers import normalize_country_name, is_chain, is_blacklisted_email
from core.scraper import playwright_scrape_single
from core.geocoder import get_coordinates_cached

# Inisialisasi blacklists di session state jika belum ada
if "email_blacklist" not in st.session_state:
    st.session_state.email_blacklist = DEFAULT_EMAIL_BLACKLIST.copy()

if "chain_blacklist" not in st.session_state:
    st.session_state.chain_blacklist = list(DEFAULT_CHAIN_KEYWORDS)

# --- UI SETUP ---
st.set_page_config(page_title="MScrape", layout="wide", page_icon="🚀")
st.title("🚀 G-Maps Scraper (Global + Target Total, Paralel)")

with st.sidebar:
    st.header("📍 Konfigurasi")

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

        max_workers = st.slider(
            "🧵 Jumlah Browser Paralel",
            min_value=2, max_value=8, value=5,
            help="Lebih banyak = lebih cepat, tapi lebih gampang kena block Google."
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

        st.subheader("⭐ Filter Rating & Review Count")
        enable_rating_filter = st.checkbox("Aktifkan filter rating", value=False)
        rc1, rc2 = st.columns(2)
        with rc1:
            min_rating = st.number_input(
                "Rating Min", min_value=0.0, max_value=5.0, value=0.0, step=0.1,
                disabled=not enable_rating_filter
            )
        with rc2:
            max_rating = st.number_input(
                "Rating Max", min_value=0.0, max_value=5.0, value=5.0, step=0.1,
                disabled=not enable_rating_filter
            )

        enable_review_filter = st.checkbox("Aktifkan filter jumlah review", value=False)
        rv1, rv2 = st.columns(2)
        with rv1:
            min_reviews = st.number_input(
                "Jumlah Review Min", min_value=0, value=0, step=10,
                disabled=not enable_review_filter
            )
        with rv2:
            max_reviews = st.number_input(
                "Jumlah Review Max", min_value=0, value=10000, step=100,
                disabled=not enable_review_filter
            )

        st.caption("Listing dengan rating/review 'N/A' otomatis dibuang kalau filter terkait diaktifkan.")

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

# --- RUN SCRAPE (PARALEL) ---
if btn_run:
    email_blacklist = st.session_state.email_blacklist
    chain_blacklist = st.session_state.chain_blacklist

    st.sidebar.success(f"✅ Filter aktif: {len(email_blacklist)} email patterns, {len(chain_blacklist)} chain keywords")

    keywords = [k.strip() for k in keyword_input.split("\n") if k.strip()]
    if not keywords or not country.strip():
        st.warning("⚠️ Isi minimal satu niche dan negara!")
        st.stop()

    normalized_country = normalize_country_name(country)

    # --- tentukan daftar kota ---
    if scrape_mode == "Satu Kota":
        if not location.strip():
            st.warning("⚠️ Isi City!")
            st.stop()
        target_cities = [location]
        target = max_res_per_city
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
        target_cities = cities
        target = total_target

    # --- geocode SEMUA kota di MAIN THREAD (session_state cuma boleh diakses di sini) ---
    with st.spinner("📍 Geocoding lokasi..."):
        location_coords = {}
        for loc_name in target_cities:
            coords = get_coordinates_cached(f"{loc_name}, {country}")
            if coords is None:
                st.warning(f"⚠️ Lewati: {loc_name} (koordinat tidak ditemukan)")
            location_coords[loc_name] = coords

    valid_cities = [c for c in target_cities if location_coords.get(c) is not None]
    if not valid_cities:
        st.error("❌ Tidak ada kota dengan koordinat valid.")
        st.stop()

    # --- bangun task queue: (city, keyword, limit, lat, lng) ---
    if scrape_mode == "Satu Kota":
        lat, lng = location_coords[location]
        per_kw_limit = max_res_per_city // len(keywords) or 1
        task_queue = [(location, kw, per_kw_limit, lat, lng) for kw in keywords]
    else:
        task_queue = []
        for city in valid_cities:
            lat, lng = location_coords[city]
            for kw in keywords:
                task_queue.append((city, kw, max_per_city, lat, lng))

        st.info(f"🌍 {len(valid_cities)} kota × {len(keywords)} niche, paralel {max_workers} browser, target {target}.")
        if extract_email:
            st.warning("📧 Email extraction aktif — proses akan lebih lama & hasil email tergantung website.")

    all_results = []
    blocked_count = 0
    progress_bar = st.progress(0)
    status_text = st.empty()

    idx = 0
    futures = {}

    def submit_next(executor):
        global idx
        if idx < len(task_queue):
            c, k, lim, lat, lng = task_queue[idx]
            fut = executor.submit(
                playwright_scrape_single, k, c, country, lim, lat, lng,
                extract_email, email_blacklist, chain_blacklist
            )
            futures[fut] = (c, k)
            idx += 1

    n_workers = min(max_workers, len(task_queue))
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as executor:
        for _ in range(n_workers):
            submit_next(executor)

        while futures:
            done, _ = concurrent.futures.wait(futures.keys(), return_when=concurrent.futures.FIRST_COMPLETED)
            for fut in done:
                city, kw = futures.pop(fut)
                try:
                    result = fut.result()
                    if result.get("blocked"):
                        blocked_count += 1
                        status_text.write(f"🚫 KEBLOCK: {city} | {kw} (total block: {blocked_count})")
                    all_results.extend(result.get("data", []))
                except Exception as e:
                    status_text.write(f"⚠️ Error {city} | {kw}: {e}")

                status_text.write(f"✅ {city} | {kw} — total terkumpul: {len(all_results)}/{target}")
                progress_bar.progress(min(len(all_results) / target, 1.0))

                if len(all_results) >= target:
                    futures.clear()
                    break

                submit_next(executor)

    status_text.write("✅ Selesai!")
    if blocked_count > 0:
        st.warning(f"🚫 {blocked_count} request kena block Google. Coba turunin jumlah browser paralel atau pakai proxy.")

    if all_results:
        df = pd.DataFrame(all_results)
        df.drop_duplicates(subset=["Business Name", "Full Address"], keep="first", inplace=True)

        # --- filter rating & jumlah review ---
        count_before_quality_filter = len(df)
        if enable_rating_filter:
            rating_numeric = pd.to_numeric(df["Rating"], errors="coerce")
            df = df[rating_numeric.between(min_rating, max_rating)]
        if enable_review_filter:
            review_numeric = pd.to_numeric(df["Review Counts"], errors="coerce")
            df = df[review_numeric.between(min_reviews, max_reviews)]
        quality_filtered_count = count_before_quality_filter - len(df)

        df = df.head(target)
        df.reset_index(drop=True, inplace=True)

        chain_filtered_count = sum(1 for name in df["Business Name"] if is_chain(name, chain_blacklist))
        email_filtered_count = sum(1 for email in df["Emails"] if is_blacklisted_email(email, email_blacklist))

        st.success(f"🏆 Total {len(df)} data unik siap cair!")
        st.info(f"📊 Statistik Filter: {chain_filtered_count} chain diabaikan, {email_filtered_count} email di-blacklist")
        if enable_rating_filter or enable_review_filter:
            st.info(f"⭐ {quality_filtered_count} data dibuang karena di luar rentang rating/review yang ditentukan")

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