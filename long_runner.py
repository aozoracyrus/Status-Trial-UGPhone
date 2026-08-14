import os
import json
import time
import re
import requests
import threading
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

# =====================================================================
# CẤU HÌNH
# =====================================================================
URL = "https://hanaminikata.com/status_trial_ugphone"
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
ROLE_PING_ID = os.environ.get('ROLE_PING_ID')

DURATION_MINUTES = 345
CHECK_INTERVAL = 60
PING_AUTO_DELETE = 300
BROWSER_LIFETIME_MINUTES = 60  # ✅ Restart browser mỗi 60 phút (trước khi nó chết)

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

BROWSER_DEAD_KEYWORDS = [
    'httpconnectionpool', 'localhost', 'timeout', 'read timeout',
    'failed to execute', 'invalid selector', 'session info',
    'target closed', 'connection refused', 'browser has been closed',
    'no such window', 'no target', 'target page, context or browser'
]

# =====================================================================
# GIỜ 24H CHUẨN
# =====================================================================
MONTHS = {'January':'01','February':'02','March':'03','April':'04','May':'05','June':'06',
          'July':'07','August':'08','September':'09','October':'10','November':'11','December':'12'}

def get_time_24h():
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
        return now.strftime("%H:%M ngày %d/%m/%Y")
    except Exception:
        pass
    try:
        res = requests.get("https://time.is/Vietnam", timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
        t = res.text
        hh = mm = None
        m = re.search(r'id="clock"[^>]*>(\d{1,2}):(\d{2})', t)
        ampm = re.search(r'id="ampm"[^>]*>(am|pm)', t)
        if m:
            h, mm = int(m.group(1)), m.group(2)
            if ampm:
                if ampm.group(1) == 'pm' and h != 12: h += 12
                if ampm.group(1) == 'am' and h == 12: h = 0
            hh = h
        d = re.search(r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s*(\w+)\s+(\d{1,2}),\s*(\d{4})', t)
        if hh is not None and d:
            return f"{str(hh).zfill(2)}:{mm} ngày {str(int(d.group(2))).zfill(2)}/{MONTHS.get(d.group(1), '??')}/{d.group(3)}"
    except Exception:
        pass
    now = datetime.now(timezone.utc) + timedelta(hours=7)
    return now.strftime("%H:%M ngày %d/%m/%Y")

def get_hhmm():
    return get_time_24h().split(' ngày')[0]

def seconds_until_next_minute():
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    except Exception:
        now = datetime.now(timezone.utc) + timedelta(hours=7)
    next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return max(0, (next_minute - now).total_seconds())

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def is_browser_dead_error(error_msg):
    msg = str(error_msg).lower()
    return any(keyword in msg for keyword in BROWSER_DEAD_KEYWORDS)

# =====================================================================
# BROWSER CLASSES (Camoufox ưu tiên vì ổn định hơn)
# =====================================================================
class CamoufoxBrowser:
    def __init__(self):
        from camoufox.sync_api import Camoufox
        self.cm = Camoufox(headless=True, block_images=True)
        self.browser = self.cm.__enter__()
        self.page = self.browser.new_page()
        self.name = "Camoufox"
        self.started_at = time.time()

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
    """✅ Ưu tiên Camoufox (ổn định hơn trong long-run)"""
    if prefer_camoufox:
        try:
            b = CamoufoxBrowser()
            b.open_page()
            # ✅ Sleep 10s để browser ổn định hoàn toàn
            time.sleep(10)
            print(f"✅ Đã mở browser: {b.name}")
            return b
        except Exception as e:
            print(f"❌ Lỗi Camoufox: {e}")
    
    # Fallback sang SeleniumBase
    try:
        b = SeleniumBaseBrowser()
        b.open_page()
        time.sleep(10)
        print(f"✅ Đã mở browser: {b.name}")
        return b
    except Exception as e:
        print(f"❌ Lỗi SeleniumBase: {e}")
        return None


def proactive_restart(browser, reason="định kỳ"):
    """✅ Proactive restart: restart trước khi browser chết"""
    print(f"🔄 Proactive restart ({reason})...")
    
    if browser:
        try: browser.close()
        except Exception: pass
    
    time.sleep(15)  # Chờ 15s để giải phóng hoàn toàn
    
    new_browser = start_browser(prefer_camoufox=True)
    if new_browser:
        wait_cloudflare(new_browser)
        time.sleep(5)  # Sleep thêm 5s để ổn định
        print(f"✅ Browser {new_browser.name} đã restart thành công")
    return new_browser


def emergency_restart(browser, consecutive_failures):
    """Emergency restart: khi browser chết bất ngờ"""
    wait_time = 3 if consecutive_failures <= 2 else (15 if consecutive_failures <= 5 else 30)
    print(f"💀 Emergency restart (lần {consecutive_failures}, chờ {wait_time}s)...")
    
    if browser:
        try: browser.close()
        except Exception: pass
    
    time.sleep(wait_time)
    
    # Switch browser nếu restart quá nhiều
    prefer_camoufox = consecutive_failures <= 5
    if consecutive_failures > 5:
        print("⚠️ Restart quá nhiều, switch browser...")
        prefer_camoufox = not (browser.name == "Camoufox" if browser else True)
    
    new_browser = start_browser(prefer_camoufox)
    if new_browser:
        wait_cloudflare(new_browser)
        time.sleep(5)
        print(f"✅ Browser {new_browser.name} đã emergency restart thành công")
    return new_browser


def wait_cloudflare(browser, timeout=90):
    start = time.time()
    while time.time() - start < timeout:
        try:
            html = browser.get_html()
        except Exception:
            time.sleep(3)
            continue
        if "just a moment" not in html.lower():
            return True
        print("⏳ Đang chờ Cloudflare xác minh...")
        time.sleep(5)
    return False


def recover_cloudflare(browser):
    print("⚠️ Cloudflare xuất hiện lại, đang khôi phục...")
    if not wait_cloudflare(browser, 90):
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
# MAIN LOOP (Proactive Restart Strategy)
# =====================================================================
def main():
    print(f"🏁 Bắt đầu relay {DURATION_MINUTES} phút (Proactive Restart mỗi {BROWSER_LIFETIME_MINUTES}p)...")
    start_time = time.time()

    msg_id, prev_state = load_state()
    print(f"📂 Message ID hiện tại: {msg_id}")

    last_regions = prev_state if prev_state else {c: False for c in REGIONS}
    check_count = 0
    restart_count = 0
    consecutive_failures = 0
    next_check = time.time()
    next_footer = time.time() + seconds_until_next_minute()
    next_proactive_restart = time.time() + (BROWSER_LIFETIME_MINUTES * 60)  # ✅ Proactive restart timer

    browser = start_browser(prefer_camoufox=True)
    if browser and not wait_cloudflare(browser):
        print("⚠️ Cloudflare chưa qua")

    while (time.time() - start_time) / 60 < DURATION_MINUTES:
        # ✅ PROACTIVE RESTART: Restart browser định kỳ trước khi nó chết
        if time.time() >= next_proactive_restart:
            browser_age = (time.time() - browser.started_at) / 60 if browser else 0
            print(f"⏰ Browser đã chạy {int(browser_age)} phút, proactive restart...")
            browser = proactive_restart(browser, "định kỳ")
            restart_count += 1
            consecutive_failures = 0
            next_proactive_restart = time.time() + (BROWSER_LIFETIME_MINUTES * 60)
            if browser is None:
                print("❌ Proactive restart fail, đợi 1 phút thử lại...")
                time.sleep(60)
                continue

        if time.time() >= next_check:
            check_count += 1
            check_success = False
            
            try:
                # Health check trước khi check
                if browser is None or not browser.is_alive():
                    print(f"💀 Browser đã chết sau {int((time.time()-browser.started_at)/60)} phút")
                    consecutive_failures += 1
                    browser = emergency_restart(browser, consecutive_failures)
                    restart_count += 1
                    if browser is None:
                        print(f"🔄 Check lần {check_count}: ❌ Không khởi động lại được browser")
                        next_check = max(next_check + CHECK_INTERVAL, time.time())
                        continue

                # CÁCH 1: XHR đồng bộ
                html = None
                via = "XHR"
                try:
                    html = browser.fetch_fresh_html()
                except Exception as e:
                    error_str = str(e)
                    if is_browser_dead_error(error_str):
                        print(f"💀 XHR phát hiện browser chết: {error_str[:80]}...")
                        consecutive_failures += 1
                        browser = emergency_restart(browser, consecutive_failures)
                        restart_count += 1
                        # Thử lại XHR với browser mới
                        try:
                            html = browser.fetch_fresh_html()
                        except Exception:
                            html = None
                    else:
                        print(f"⚠️ XHR lỗi: {e}")

                # Nếu dính CF → khôi phục
                if html and "just a moment" in html.lower():
                    html = recover_cloudflare(browser)
                    if html is None:
                        consecutive_failures += 1
                        browser = emergency_restart(browser, consecutive_failures)
                        restart_count += 1
                        try:
                            html = browser.fetch_fresh_html()
                        except Exception:
                            html = None

                # CÁCH 2: DOM fallback
                if not html or 'status-card' not in html:
                    via = "DOM"
                    try:
                        browser.click_refresh()
                        time.sleep(4)
                        html = browser.get_html()
                    except Exception as e:
                        error_str = str(e)
                        if is_browser_dead_error(error_str):
                            print(f"💀 DOM phát hiện browser chết: {error_str[:80]}...")
                            consecutive_failures += 1
                            browser = emergency_restart(browser, consecutive_failures)
                            restart_count += 1
                            try:
                                html = browser.fetch_fresh_html()
                            except Exception:
                                html = None
                        else:
                            print(f"⚠️ DOM lỗi: {e}")

                    if html and "just a moment" in html.lower():
                        html = recover_cloudflare(browser)
                        if html is None:
                            consecutive_failures += 1
                            browser = emergency_restart(browser, consecutive_failures)
                            restart_count += 1

                # Parse kết quả
                if html and 'status-card' in html:
                    regions = parse_html(html)
                    check_and_ping(regions, prev_state)
                    prev_state = regions
                    last_regions = regions
                    msg_id = push_embed(regions, msg_id)
                    save_state(msg_id, regions)
                    ket_qua = ", ".join(f"{c}: {bool(regions.get(c))}" for c in ['SG', 'HK', 'JP', 'DE', 'US'])
                    print(f"🔄 Check lần {check_count} [{get_hhmm()}] ({via}): {ket_qua}")
                    check_success = True
                    consecutive_failures = 0
                else:
                    print(f"🔄 Check lần {check_count}: ❌ Chưa lấy được dữ liệu")
            except Exception as e:
                print(f"🔄 Check lần {check_count}: ❌ Lỗi tổng: {e}")
                consecutive_failures += 1
                browser = emergency_restart(browser, consecutive_failures)
                restart_count += 1

            next_check = max(next_check + CHECK_INTERVAL, time.time())

        # FOOTER ĐÚNG GIÂY 00
        if time.time() >= next_footer:
            msg_id = push_embed(last_regions, msg_id)
            print(f"🕐 Footer cập nhật lúc {get_hhmm()}:00 (restart: {restart_count}, consecutive: {consecutive_failures})")
            next_footer = time.time() + seconds_until_next_minute()

        time.sleep(1)

    print(f"⏰ Hết 345 phút. Bàn giao... (browser đã restart {restart_count} lần)")
    if browser:
        browser.close()

if __name__ == "__main__":
    main()
