import time
import random
import re
import streamlit as st
from playwright.sync_api import sync_playwright

from .geocoder import get_coordinates_cached
from .email_finder import extract_email_from_website_in_new_tab
from utils.text_helpers import clean_text, is_chain, is_blacklisted_email

def playwright_scrape_single(kw, loc, ctr, limit, extract_email=False, email_blacklist=None, chain_blacklist=None):
    """Scrape satu kota menggunakan Playwright."""
    results = []
    full_location = f"{loc}, {ctr}"
    
    coords = get_coordinates_cached(full_location)
    if coords is None:
        st.warning(f"⚠️ Lewati: {full_location} (koordinat tidak ditemukan)")
        return []

    lat, lng = coords
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        
        try:
            # Memastikan pencarian lebih spesifik dengan menyertakan nama kota
            search_query = f"{kw} di {loc}".replace(' ', '+')
            zoom = 12
            url = f"https://www.google.com/maps/search/{search_query}/@{lat},{lng},{zoom}z"
            page.goto(url, wait_until="domcontentloaded")
            time.sleep(random.uniform(5, 8))

            # Handle scrolling feed
            try:
                panel = page.locator('//div[contains(@role, "feed")]')
                if panel.count() > 0:
                    last_height = panel.evaluate("el => el.scrollHeight")
                    scroll_count = 0
                    max_scrolls = 8
                    
                    while scroll_count < max_scrolls:
                        panel.evaluate("el => el.scrollTop = el.scrollHeight")
                        time.sleep(random.uniform(2.0, 3.0))
                        
                        new_height = panel.evaluate("el => el.scrollHeight")
                        if new_height == last_height:
                            break
                        last_height = new_height
                        scroll_count += 1
            except Exception as e:
                st.warning(f"⚠️ Scroll feed gagal: {str(e)}")

            # Kumpulkan URLs
            urls = []
            articles = page.locator('//div[contains(@role, "article")]').all()
            for card in articles[:limit]:
                try:
                    # Cari semua a tag di dalam card
                    links = card.locator('a').all()
                    for lnk in links:
                        href = lnk.get_attribute("href")
                        if href and "/maps/place/" in href:
                            urls.append(href)
                            break
                        elif href and "google.com/maps" in href:
                            urls.append(href)
                            break
                except:
                    pass

            # Kunjungi setiap URL
            for gmaps_url in urls:
                if not gmaps_url or "google.com/maps" not in gmaps_url:
                    continue
                    
                try:
                    page.goto(gmaps_url, wait_until="domcontentloaded")
                    time.sleep(random.uniform(3.5, 5.0))

                    # Judul
                    page_title = page.title()
                    raw_name = page_title.split(' - Google Maps')[0] if ' - Google Maps' in page_title else "N/A"
                    if raw_name == "N/A" or raw_name == "Google Maps":
                        h1 = page.locator('h1').first
                        if h1.count() > 0:
                            raw_name = h1.inner_text()
                    
                    # Alamat
                    addr_btn = page.locator('button[data-item-id="address"]')
                    raw_address = addr_btn.inner_text() if addr_btn.count() > 0 else "N/A"
                    
                    # Telepon
                    raw_phone = "N/A"
                    for tooltip in ["telepon", "phone"]:
                        phone_btn = page.locator(f'//button[contains(@data-tooltip, "{tooltip}")]')
                        if phone_btn.count() > 0:
                            raw_phone = phone_btn.first.inner_text()
                            break

                    # Website
                    website = "N/A"
                    web_btn = page.locator('a[data-item-id="authority"]')
                    if web_btn.count() > 0:
                        website = web_btn.first.get_attribute("href") or "N/A"

                    name = clean_text(raw_name)
                    address = clean_text(raw_address)
                    phone = clean_text(raw_phone)

                    # Extract Email in new tab via Playwright context
                    email = "N/A"
                    if extract_email and website != "N/A":
                        email = extract_email_from_website_in_new_tab(context, website)

                    # Rating
                    rating = "N/A"
                    try:
                        star_elements = page.locator('//span[contains(@aria-label, "stars") or contains(@aria-label, "bintang")]').all()
                        for el in star_elements:
                            rating_text = el.get_attribute("aria-label")
                            if rating_text:
                                match = re.search(r'([\d,.]+)', rating_text)
                                if match:
                                    rating = match.group(1).replace(',', '.')
                                    break
                        if rating == "N/A":
                            img_stars = page.locator('div[role="img"][aria-label*="stars"], div[role="img"][aria-label*="bintang"]')
                            if img_stars.count() > 0:
                                match = re.search(r'([\d,.]+)', img_stars.first.get_attribute("aria-label"))
                                if match:
                                    rating = match.group(1).replace(',', '.')
                    except:
                        pass
                    
                    # Review Count
                    review_count = "N/A"
                    try:
                        rev_els = page.locator('//span[contains(@aria-label, "review") or contains(@aria-label, "ulasan") or contains(text(), "review") or contains(text(), "ulasan")]').all()
                        if not rev_els:
                             rev_els = page.locator('button').all()
                             
                        for el in rev_els:
                            text = el.inner_text() or el.get_attribute("aria-label") or ""
                            match = re.search(r'[\(·]?\s*([\d.,]+)\s*[\)]?\s*(?:reviews?|ulasan)', text, re.IGNORECASE)
                            if match:
                                review_count = match.group(1).replace('.', '').replace(',', '')
                                break
                            match2 = re.search(r'([\d.,]+)\s*(?:reviews?|ulasan)', text, re.IGNORECASE)
                            if match2:
                                review_count = match2.group(1).replace('.', '').replace(',', '')
                                break
                    except:
                        pass

                    # Latitude & Longitude
                    lat_detail, lng_detail = "N/A", "N/A"
                    try:
                        current_url = page.url
                        match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', current_url)
                        if match:
                            lat_detail, lng_detail = match.group(1), match.group(2)
                    except:
                        pass

                    if chain_blacklist and is_chain(name, chain_blacklist):
                        continue

                    if extract_email and email_blacklist and is_blacklisted_email(email, email_blacklist):
                        email = "N/A"

                    results.append({
                        "Business Name": name,
                        "Full Address": address,
                        "Website": website,
                        "Phone": phone, 
                        "Emails": email,
                        "Category": kw.title(),
                        "Rating": rating,
                        "Review Counts": review_count,
                        "Latitude": lat_detail,
                        "Longitude": lng_detail,
                        "City": loc.title(),
                        "Country": ctr.title(),
                        "Google Maps URL": gmaps_url
                    })
                except Exception as e:
                    continue
        finally:
            browser.close()
            
    return results
