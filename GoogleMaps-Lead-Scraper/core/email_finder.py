import time
import random
import re

def extract_email_from_website_in_new_tab(context, url):
    if url == "N/A":
        return "N/A"
    page = None
    try:
        # Buka tab baru menggunakan Playwright context
        page = context.new_page()
        
        # Coba halaman utama dulu
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(random.uniform(2.5, 3.5))
        
        # 1. Cari di body text
        body_text = page.locator("body").inner_text()
        emails_found = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', body_text)
        if emails_found:
            page.close()
            return emails_found[0]

        # 2. Cari di tag mailto
        mailto_links = page.locator('//a[contains(@href, "mailto:")]').all()
        for link in mailto_links:
            href = link.get_attribute("href")
            if href and "mailto:" in href:
                email = href.split("mailto:")[-1].split("?")[0].strip()
                if re.match(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$', email):
                    page.close()
                    return email

        # 3. Coba halaman /contact (opsional)
        try:
            contact_url = url.rstrip("/") + "/contact"
            page.goto(contact_url, timeout=10000, wait_until="domcontentloaded")
            time.sleep(random.uniform(2.0, 3.0))
            body_text_contact = page.locator("body").inner_text()
            emails_contact = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', body_text_contact)
            if emails_contact:
                page.close()
                return emails_contact[0]
        except:
            pass

        # Tidak ditemukan
        page.close()
        return "N/A"
    except Exception:
        if page:
            try:
                page.close()
            except:
                pass
        return "N/A"
