import os
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

# =====================================================================
# CẤU HÌNH
# =====================================================================
URL = "https://hanaminikata.com/status_trial_ugphone"
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
ROLE_PING_ID = os.environ.get('ROLE_PING_ID')

DURATION_MINUTES = 345   # Chạy 5h45p rồi bàn giao
CHECK_INTERVAL = 60      # 1 phút / 1 lần bấm "Làm mới"
FOOTER_INTERVAL = 30     # Refresh giờ footer mỗi 30s

DATA_DIR = "data"
MSG_ID_FILE = os.path.join(DATA_DIR, "message_id.txt")
PREV_STATE_FILE = os.path.join(DATA_DIR, "prev_state.json")

REGIONS = {
    'SG': {'name': 'Singapore', 'flag': '🇸🇬'},
    'HK': {'name': 'Hong Kong', 'flag': '🇭🇰'},
    'JP': {'name': 'Japan', 'flag': '🇯🇵'},
    'DE': {'name': 'Germany', 'flag': '🇩🇪'},
    'US': {'name': 'America', 'flag': '🇺🇸'}
}

def get_vn_time_str():
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    except Exception:
        now = datetime.now(timezone.utc) + timedelta(hours=7)
    return now.strftime("%H:%M ngày %d/%m/%Y")

def get_hhmm():
    return get_vn_time_str().split(' ngày')[0]

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

# =====================================================================
# 2 LOẠI BROWSER (GIỮ MỞ SUỐT 345 PHÚT - KHÔNG MỞ LẠI MỖI LẦN)
# =====================================================================
class SeleniumBaseBrowser:
    """Chiến lược 1: SeleniumBase UC Mode"""
    def __init__(self):
        from seleniumbase import Driver
        self.driver = Driver(uc=True, headless=True)
        self.name = "SeleniumBase UC"

    def open_page(self):
        self.driver.uc_open_with_reconnect(URL, reconnect_time=7)

    def click_refresh(self):
        """Bấm nút Làm mới giống người thật"""
        try:
            self.driver.click("button.refresh-btn", timeout=5)
        except Exception:
            try:
                self.driver.execute_script("refreshStatus()")
            except Exception:
                self.driver.get(URL)

    def get_html(self):
        return self.driver.page_source

    def close(self):
        try: self.driver.quit()
        except Exception: pass


class CamoufoxBrowser:
    """Chiến lược 2: Camoufox (dự phòng)"""
    def __init__(self):
        from camoufox.sync_api import Camoufox
        self.cm = Camoufox(headless=True, block_images=True)
        self.browser = self.cm.__enter__()
        self.page = self.browser.new_page()
        self.name = "Camoufox"

    def open_page(self):
        self.page.goto(URL, wait_until="domcontentloaded", timeout=45000)

    def click_refresh(self):
        try:
            self.page.click("button.refresh-btn", timeout=5000)
        except Exception:
            try:
                self.page.evaluate("refreshStatus()")
            except Exception:
                self.page.goto(URL, wait_until="domcontentloaded", timeout=45000)

    def get_html(self):
        return self.page.content()

    def close(self):
        try: self.cm.__exit__(None, None, None)
        except Exception: pass


def start_browser():
    """Mở browser 1 lần duy nhất"""
    try:
        b = SeleniumBaseBrowser()
        b.open_page()
        print(f"✅ Đã mở browser: {b.name}")
        return b
    except Exception as e:
        print(f"❌ Lỗi SeleniumBase: {e}")
    try:
        b = CamoufoxBrowser()
        b.open_page()
        print(f"✅ Đã mở browser: {b.name}")
        return b
    except Exception as e:
        print(f"❌ Lỗi Camoufox: {e}")
        return None


def wait_cloudflare(browser, timeout=90):
    """Đợi xác minh Cloudflare xong (trang hết 'just a moment')"""
    start = time.time()
    while time.time() - start < timeout:
        html = browser.get_html()
        if "just a moment" not in html.lower():
            return True
        print("⏳ Đang chờ Cloudflare xác minh...")
        time.sleep(5)
    return False

# =====================================================================
# PARSE + DISCORD (giữ nguyên)
# =====================================================================
def parse_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    regions = {}
    for code, info in REGIONS.items():
        cards = soup.find_all('div', class_='status-card')
        found = False
        for card in cards:
            if info['name'].lower() in card.get_text().lower():
                text = card.get_text().lower()
                regions[code] = 'có máy' in text or 'đang còn máy' in text
                found = True
                break
        if not found:
            regions[code] = False
    return regions

def load_state():
    msg_id = None
    prev_state = {}
    if os.path.exists(MSG_ID_FILE):
        with open(MSG_ID_FILE, 'r') as f:
            msg_id = f.read().strip()
    if os.path.exists(PREV_STATE_FILE):
        try:
            with open(PREV_STATE_FILE, 'r') as f:
                prev_state = json.load(f)
        except Exception: pass
    return msg_id, prev_state

def save_state(msg_id, regions):
    ensure_data_dir()
    with open(MSG_ID_FILE, 'w') as f:
        f.write(str(msg_id))
    with open(PREV_STATE_FILE, 'w') as f:
        json.dump(regions, f)

def build_embed(regions):
    any_in_stock = any(regions.get(c) for c in REGIONS)
    color = 0x57f287 if any_in_stock else 0xed4245
    fields = []
    for code, info in REGIONS.items():
        status = "🟢 Còn máy" if regions.get(code) else "🔴 Hết máy"
        fields.append({"name": f"{info['flag']} {info['name']}", "value": status, "inline": True})
    return {
        "title": "📱 Trạng thái UGPhone Trial",
        "color": color,
        "fields": fields,
        "footer": {"text": f"Uptime: {get_vn_time_str()}"}
    }

def push_embed(regions, msg_id=None):
    if not WEBHOOK_URL: return None
    payload = {"embeds": [build_embed(regions)]}
    if msg_id:
        try:
            res = requests.patch(f"{WEBHOOK_URL}/messages/{msg_id}", json=payload)
            if res.status_code == 200:
                return msg_id
        except Exception: pass
    try:
        res = requests.post(f"{WEBHOOK_URL}?wait=true", json=payload)
        if res.status_code == 200:
            return res.json().get("id")
    except Exception: pass
    return msg_id

def check_and_ping(regions, prev_state):
    if not ROLE_PING_ID or not WEBHOOK_URL: return
    new_stock = [REGIONS[c]['name'] for c, v in regions.items() if v and not prev_state.get(c, False)]
    if new_stock:
        try:
            requests.post(WEBHOOK_URL, json={"content": f"<@&{ROLE_PING_ID}> 🎉 Server **{', '.join(new_stock)}** vừa có máy!"})
        except Exception: pass

# =====================================================================
# MAIN LOOP - QUY TRÌNH B1 → B9 CỦA ANH
# =====================================================================
def main():
    print(f"🏁 Bắt đầu relay {DURATION_MINUTES} phút (chế độ giữ browser mở)...")
    start_time = time.time()

    msg_id, prev_state = load_state()
    print(f"📂 Message ID hiện tại: {msg_id}")

    last_regions = prev_state if prev_state else {c: False for c in REGIONS}
    check_count = 0
    next_check = time.time()                   # Check ngay
    next_footer = time.time() + FOOTER_INTERVAL

    # B1-B4: Mở browser + xác minh Cloudflare 1 LẦN
    browser = start_browser()
    if browser and not wait_cloudflare(browser):
        print("⚠️ Cloudflare chưa qua, sẽ thử lại trong loop")

    while (time.time() - start_time) / 60 < DURATION_MINUTES:
        now = time.time()

        # ---------------- CHECK MỖI 1 PHÚT ----------------
        if now >= next_check:
            check_count += 1
            try:
                # Nếu browser chết → mở lại (B1-B4 lại từ đầu)
                if browser is None:
                    browser = start_browser()
                    if browser:
                        wait_cloudflare(browser)

                if browser:
                    # ⚠ Nếu bị CF chặn lại (server restart) → xác minh lại
                    html = browser.get_html()
                    if "just a moment" in html.lower():
                        print("⚠️ Cloudflare xuất hiện lại, chờ xác minh...")
                        if not wait_cloudflare(browser, 60):
                            browser.close()
                            browser = None
                            raise Exception("CF block kéo dài")

                    # B8: Bấm nút "Làm mới"
                    browser.click_refresh()
                    time.sleep(3)  # Đợi data tải lại

                    # B5: Đọc trạng thái
                    html = browser.get_html()
                    regions = parse_html(html)

                    check_and_ping(regions, prev_state)
                    prev_state = regions
                    last_regions = regions
                    msg_id = push_embed(regions, msg_id)
                    save_state(msg_id, regions)

                    ket_qua = ", ".join(f"{c}: {bool(regions.get(c))}" for c in ['SG', 'HK', 'JP', 'DE', 'US'])
                    print(f"🔄 Check lần {check_count} [{get_hhmm()}]: {ket_qua}")
                else:
                    print(f"🔄 Check lần {check_count}: ❌ Không mở được browser")
            except Exception as e:
                print(f"🔄 Check lần {check_count}: ❌ Lỗi: {e}")
                try:
                    if browser: browser.close()
                except Exception: pass
                browser = None

            # Đặt mốc phút tiếp theo (chuẩn 60s)
            next_check = max(next_check + CHECK_INTERVAL, time.time())

        # ---------------- REFRESH FOOTER 30s ----------------
        if time.time() >= next_footer:
            msg_id = push_embed(last_regions, msg_id)
            next_footer = time.time() + FOOTER_INTERVAL

        time.sleep(2)

    print("⏰ Hết 345 phút. Bàn giao cho runner kế tiếp...")
    if browser:
        browser.close()

if __name__ == "__main__":
    main()
