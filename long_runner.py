import os
import json
import time
import re
import requests
import threading
import subprocess
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import pytz

# =====================================================================
# CẤU HÌNH
# =====================================================================
URL = "https://hanaminikata.com/status_trial_ugphone"
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
ROLE_PING_ID = os.environ.get('ROLE_PING_ID')

DURATION_MINUTES = 345
PING_AUTO_DELETE = 300

CAMOUFOX_LIFETIME_MINUTES = 999   # Camoufox KHÔNG proactive restart
SELENIUM_LIFETIME_MINUTES = 120   # SeleniumBase restart mỗi 120 phút

DATA_DIR = "data"
MSG_ID_FILE = os.path.join(DATA_DIR, "message_id.txt")
PREV_STATE_FILE = os.path.join(DATA_DIR, "prev_state.json")

REGIONS = {
    'SG': {'name': 'Singapore', 'flag': '🇸🇬'},
    'HK': {'name': 'Hong Kong', 'flag': '🇭'},
    'JP': {'name': 'Japan', 'flag': '🇯🇵'},
    'DE': {'name': 'Germany', 'flag': '🇩🇪'},
    'US': {'name': 'America', 'flag': '🇺🇸'}
}

BROWSER_DEAD_KEYWORDS = [
    'httpconnectionpool', 'localhost', 'timeout', 'read timeout',
    'failed to execute', 'invalid selector', 'session info',
    'target closed', 'connection refused', 'browser has been closed',
    'no such window', 'no target', 'target page, context or browser',
    'official/stable is not installed'
]

# ✅ Giờ Việt Nam bằng pytz - KHÔNG cache, KHÔNG time.is (luôn chính xác)
tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')

def get_time_24h():
    return datetime.now(tz_vn).strftime("%H:%M ngày %d/%m/%Y")

def get_hhmm():
    return datetime.now(tz_vn).strftime("%H:%M")

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def is_browser_dead_error(error_msg):
    msg = str(error_msg).lower()
    return any(keyword in msg for keyword in BROWSER_DEAD_KEYWORDS)

def ensure_camoufox_installed():
    try:
        result = subprocess.run(
            ['python', '-m', 'camoufox', 'fetch'],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            print("✅ Camoufox đã được cài đặt")
            return True
        print(f"⚠️ Lỗi cài Camoufox: {result.stderr}")
        return False
    except Exception as e:
        print(f"⚠️ Exception khi cài Camoufox: {e}")
        return False

# =====================================================================
# BROWSER CLASSES
# =====================================================================
class CamoufoxBrowser:
    def __init__(self):
        if not ensure_camoufox_installed():
            raise Exception("Không thể cài đặt Camoufox")
        from camoufox.sync_api import Camoufox
        self.cm = Camoufox(headless=True)
        self.browser = self.cm.__enter__()
        self.page = self.browser.new_page()
        self.name = "Camoufox"
        self.started_at = time.time()
        self.lifetime_minutes = CAMOUFOX_LIFETIME_MINUTES

    def open_page(self):
        self.page.goto(URL, wait_until="domcontentloaded", timeout=45000)

    def is_alive(self):
        try:
            _ = self.page.content()
            return True
        except Exception:
            return False

    def fetch_fresh_html(self):
        return self.page.evaluate(
            "async () => { const r = await fetch('/status_trial_ugphone?t=' + Date.now()); return await r.text(); }"
        )

    def click_refresh(self):
        self.page.evaluate(
            "if (typeof refreshStatus === 'function') { refreshStatus(); } "
            "else { var b = document.querySelector('button.refresh-btn'); if (b) { b.click(); } }"
        )

    def get_html(self):
        return self.page.content()

    def close(self):
        try: self.cm.__exit__(None, None, None)
        except Exception: pass


class SeleniumBaseBrowser:
    def __init__(self):
        from seleniumbase import Driver
        self.driver = Driver(uc=True, headless=True)
        self.driver.set_page_load_timeout(20)
        self.driver.set_script_timeout(20)
        self.name = "SeleniumBase UC"
        self.started_at = time.time()
        self.lifetime_minutes = SELENIUM_LIFETIME_MINUTES

    def open_page(self):
        self.driver.uc_open_with_reconnect(URL, reconnect_time=7)

    def is_alive(self):
        try:
            _ = self.driver.page_source
            return True
        except Exception:
            return False

    def fetch_fresh_html(self):
        js = """
        var x = new XMLHttpRequest();
        x.open('GET', arguments[0] + '?t=' + Date.now(), false);
        x.send();
        return x.responseText;
        """
        return self.driver.execute_script(js, URL)

    def click_refresh(self):
        self.driver.execute_script(
            "if (typeof refreshStatus === 'function') { refreshStatus(); } "
            "else { var b = document.querySelector('button.refresh-btn'); if (b) { b.click(); } }"
        )

    def get_html(self):
        return self.driver.page_source

    def close(self):
        try: self.driver.quit()
        except Exception: pass


def start_browser(prefer_camoufox=True):
    if prefer_camoufox:
        try:
            b = CamoufoxBrowser()
            b.open_page()
            time.sleep(10)
            print(f"✅ Đã mở browser: {b.name} (lifetime: {b.lifetime_minutes}p)")
            return b
        except Exception as e:
            print(f"❌ Lỗi Camoufox: {e}")
    try:
        b = SeleniumBaseBrowser()
        b.open_page()
        time.sleep(10)
        print(f"✅ Đã mở browser: {b.name} (lifetime: {b.lifetime_minutes}p)")
        return b
    except Exception as e:
        print(f"❌ Lỗi SeleniumBase: {e}")
        return None


def proactive_restart(browser, reason="định kỳ"):
    print(f"🔄 Proactive restart ({reason})...")
    if browser:
        try: browser.close()
        except Exception: pass
    time.sleep(15)
    prefer_camoufox = (browser.name == "Camoufox" if browser else True)
    new_browser = start_browser(prefer_camoufox)
    if new_browser:
        wait_cloudflare(new_browser)
        time.sleep(5)
        print(f"✅ Browser {new_browser.name} đã restart thành công")
    return new_browser


def emergency_restart(browser, consecutive_failures):
    wait_time = 3 if consecutive_failures <= 2 else (15 if consecutive_failures <= 5 else 30)
    print(f"💀 Emergency restart (lần {consecutive_failures}, chờ {wait_time}s)...")
    if browser:
        try: browser.close()
        except Exception: pass
    time.sleep(wait_time)

    prefer_camoufox = consecutive_failures <= 5
    if consecutive_failures > 5 and browser:
        print("⚠️ Restart quá nhiều, switch browser...")
        prefer_camoufox = not (browser.name == "Camoufox")

    new_browser = start_browser(prefer_camoufox)
    if new_browser:
        wait_cloudflare(new_browser)
        time.sleep(5)
        print(f"✅ Browser {new_browser.name} đã emergency restart thành công")
    return new_browser


def wait_cloudflare(browser, timeout=60):
    start = time.time()
    last_log_time = 0
    while time.time() - start < timeout:
        try:
            html = browser.get_html()
        except Exception:
            time.sleep(3)
            continue
        if "just a moment" not in html.lower():
            return True
        now = time.time()
        if now - last_log_time >= 15:
            print(f"⏳ Đang chờ Cloudflare xác minh... (đã chờ {int(now - start)}s)")
            last_log_time = now
        time.sleep(5)
    return False


def recover_cloudflare(browser):
    print("⚠️ Cloudflare xuất hiện lại, đang khôi phục...")
    if not wait_cloudflare(browser, 60):
        return None
    try:
        browser.open_page()
    except Exception:
        pass
    if not wait_cloudflare(browser, 30):
        return None
    try:
        return browser.fetch_fresh_html()
    except Exception:
        return None


def safe_fetch(browser):
    try:
        return browser.fetch_fresh_html()
    except Exception:
        return None

# =====================================================================
# PARSE + DISCORD
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

def delete_message_after(message_id, delay_seconds):
    def _delete():
        try:
            res = requests.delete(f"{WEBHOOK_URL}/messages/{message_id}")
            if res.status_code == 204:
                print(f"🗑️ Đã tự xóa tin nhắn ping sau {delay_seconds}s")
        except Exception:
            pass
    threading.Timer(delay_seconds, _delete).start()

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
        "footer": {"text": f"Uptime: {get_time_24h()}"}
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
        msg = f"<@&{ROLE_PING_ID}> 🎉 Server **{', '.join(new_stock)}** vừa có máy!"
        try:
            res = requests.post(f"{WEBHOOK_URL}?wait=true", json={"content": msg})
            if res.status_code == 200:
                ping_id = res.json().get("id")
                if ping_id:
                    print(f"🔔 Đã ping role, tự xóa sau {PING_AUTO_DELETE}s")
                    delete_message_after(ping_id, PING_AUTO_DELETE)
        except Exception as e:
            print(f"⚠️ Lỗi gửi ping: {e}")

# =====================================================================
# MAIN LOOP - ĐỒNG BỘ THEO PHÚT THẬT (không trôi, không lệch, không hụt)
# =====================================================================
def main():
    print(f"🏁 Bắt đầu relay {DURATION_MINUTES} phút...")
    print(f"   Camoufox: KHÔNG proactive restart | SeleniumBase: restart mỗi {SELENIUM_LIFETIME_MINUTES}p")
    print(f"   Đồng bộ: pytz + quét 5 lần/giây → check & footer đúng giây :00")
    start_time = time.time()

    msg_id, prev_state = load_state()
    print(f"📂 Message ID hiện tại: {msg_id}")

    last_regions = prev_state if prev_state else {c: False for c in REGIONS}
    check_count = 0
    restart_count = 0
    consecutive_failures = 0
    last_minute_key = None

    browser = start_browser(prefer_camoufox=True)
    if browser and not wait_cloudflare(browser):
        print("⚠️ Cloudflare chưa qua")

    try:
        while (time.time() - start_time) / 60 < DURATION_MINUTES:

            # ---- Proactive restart (chỉ SeleniumBase) ----
            if browser and browser.name != "Camoufox":
                age_min = (time.time() - browser.started_at) / 60
                if age_min >= browser.lifetime_minutes:
                    print(f"⏰ Browser {browser.name} đã chạy {int(age_min)} phút, proactive restart...")
                    browser = proactive_restart(browser, "định kỳ")
                    restart_count += 1
                    consecutive_failures = 0

            # ---- PHÁT HIỆN PHÚT MỚI (đúng giây :00, quét 0.2s) ----
            vn_now = datetime.now(tz_vn)
            minute_key = (vn_now.day, vn_now.hour, vn_now.minute)

            if minute_key != last_minute_key:
                last_minute_key = minute_key
                check_count += 1

                # ================= CHECK =================
                html = None
                via = "XHR"
                try:
                    if browser is None or not browser.is_alive():
                        print("💀 Browser chết (health check)")
                        consecutive_failures += 1
                        browser = emergency_restart(browser, consecutive_failures)
                        restart_count += 1
                        html = safe_fetch(browser) if browser else None
                    else:
                        try:
                            html = browser.fetch_fresh_html()
                        except Exception as e:
                            if is_browser_dead_error(e):
                                print(f"💀 XHR phát hiện browser chết: {str(e)[:80]}...")
                                consecutive_failures += 1
                                browser = emergency_restart(browser, consecutive_failures)
                                restart_count += 1
                                html = safe_fetch(browser) if browser else None
                            else:
                                print(f"⚠️ XHR lỗi: {e}")

                    if html and "just a moment" in html.lower():
                        html = recover_cloudflare(browser)
                        if html is None and browser:
                            consecutive_failures += 1
                            browser = emergency_restart(browser, consecutive_failures)
                            restart_count += 1
                            html = safe_fetch(browser) if browser else None

                    if (not html or 'status-card' not in html) and browser:
                        via = "DOM"
                        try:
                            browser.click_refresh()
                            time.sleep(4)
                            html = browser.get_html()
                        except Exception as e:
                            print(f"⚠️ DOM lỗi: {e}")
                        if html and "just a moment" in html.lower():
                            html = recover_cloudflare(browser)
                except Exception as e:
                    print(f"🔄 Check lần {check_count}: ❌ Lỗi tổng: {e}")
                    consecutive_failures += 1
                    browser = emergency_restart(browser, consecutive_failures)
                    restart_count += 1

                if html and 'status-card' in html:
                    regions = parse_html(html)
                    check_and_ping(regions, prev_state)
                    prev_state = regions
                    last_regions = regions
                    consecutive_failures = 0
                    ket_qua = ", ".join(f"{c}: {bool(regions.get(c))}" for c in ['SG', 'HK', 'JP', 'DE', 'US'])
                    print(f"🔄 Check lần {check_count} [{get_hhmm()}] ({via}): {ket_qua}")
                else:
                    print(f"🔄 Check lần {check_count} [{get_hhmm()}]: ❌ Chưa lấy được dữ liệu")

                # ================= FOOTER (cùng nhịp :00) =================
                msg_id = push_embed(last_regions, msg_id)
                save_state(msg_id, last_regions)
                print(f"🕐 Footer cập nhật lúc {datetime.now(tz_vn).strftime('%H:%M:%S')} (restart: {restart_count}, consecutive: {consecutive_failures})")

            time.sleep(0.2)  # Quét 5 lần/giây → không hụt giây :00

    finally:
        print(f"⏰ Kết thúc relay... (browser đã restart {restart_count} lần)")
        if browser:
            try: browser.close()
            except Exception: pass

if __name__ == "__main__":
    main()
