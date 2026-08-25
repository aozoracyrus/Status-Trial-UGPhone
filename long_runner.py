import os
import json
import time
import re
import requests
import threading
import subprocess
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
TIME_CACHE_SECONDS = 30

# ✅ FIX: Tách biệt lifetime cho từng browser
CAMOUFOX_LIFETIME_MINUTES = 999  # Camoufox KHÔNG proactive restart (gần như vô hạn)
SELENIUM_LIFETIME_MINUTES = 120  # SeleniumBase restart mỗi 120 phút

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
    'no such window', 'no target', 'target page, context or browser',
    'official/stable is not installed'
]

# =====================================================================
# GIỜ 24H CHUẨN (có cache)
# =====================================================================
MONTHS = {'January':'01','February':'02','March':'03','April':'04','May':'05','June':'06',
          'July':'07','August':'08','September':'09','October':'10','November':'11','December':'12'}

_time_cache = {'time': None, 'last_fetch': 0}

def get_time_24h():
    now = time.time()
    if now - _time_cache['last_fetch'] < TIME_CACHE_SECONDS and _time_cache['time']:
        return _time_cache['time']
    
    result = None
    try:
        from zoneinfo import ZoneInfo
        vn_now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
        result = vn_now.strftime("%H:%M ngày %d/%m/%Y")
    except Exception:
        pass
    
    if result is None:
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
                result = f"{str(hh).zfill(2)}:{mm} ngày {str(int(d.group(2))).zfill(2)}/{MONTHS.get(d.group(1), '??')}/{d.group(3)}"
        except Exception:
            pass
    
    if result is None:
        now_dt = datetime.now(timezone.utc) + timedelta(hours=7)
        result = now_dt.strftime("%H:%M ngày %d/%m/%Y")
    
    _time_cache['time'] = result
    _time_cache['last_fetch'] = now
    return result

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

# ✅ FIX: Hàm đảm bảo Camoufox đã được cài đặt
def ensure_camoufox_installed():
    """Đảm bảo Camoufox browser đã được fetch trước khi dùng"""
    try:
        result = subprocess.run(
            ['python', '-m', 'camoufox', 'fetch'],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            print("✅ Camoufox đã được cài đặt")
            return True
        else:
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
        # Đảm bảo Camoufox đã được cài trước khi khởi động
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
    
    # Nếu browser cũ là Camoufox → tiếp tục dùng Camoufox
    # Nếu browser cũ là SeleniumBase → tiếp tục dùng SeleniumBase
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
    if consecutive_failures > 5:
        print("⚠️ Restart quá nhiều, switch browser...")
        prefer_camoufox = not (browser.name == "Camoufox" if browser else True)
    
    new_browser = start_browser(prefer_camoufox)
    if new_browser:
        wait_cloudflare(new_browser)
        time.sleep(5)
        print(f"✅ Browser {new_browser.name} đã emergency restart thành công")
    return new_browser


def wait_cloudflare(browser, timeout=60):
    """✅ FIX: Giảm timeout xuống 60s, chỉ in log mỗi 15s"""
    start = time.time()
    last_log_time = 0
    log_interval = 15
    
    while time.time() - start < timeout:
        try:
            html = browser.get_html()
        except Exception:
            time.sleep(3)
            continue
        if "just a moment" not in html.lower():
            return True
        
        now = time.time()
        if now - last_log_time >= log_interval:
            elapsed = int(now - start)
            print(f"⏳ Đang chờ Cloudflare xác minh... (đã chờ {elapsed}s)")
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
# MAIN LOOP
# =====================================================================
def main():
    print(f"🏁 Bắt đầu relay {DURATION_MINUTES} phút...")
    print(f"   Camoufox: KHÔNG proactive restart (lifetime: {CAMOUFOX_LIFETIME_MINUTES}p)")
    print(f"   SeleniumBase: Proactive restart mỗi {SELENIUM_LIFETIME_MINUTES}p")
    start_time = time.time()

    msg_id, prev_state = load_state()
    print(f"📂 Message ID hiện tại: {msg_id}")

    last_regions = prev_state if prev_state else {c: False for c in REGIONS}
    check_count = 0
    restart_count = 0
    consecutive_failures = 0
    next_check = time.time()
    next_footer = time.time() + seconds_until_next_minute()

    browser = start_browser(prefer_camoufox=True)
    if browser and not wait_cloudflare(browser):
        print("⚠️ Cloudflare chưa qua")

    # Tính thời điểm proactive restart dựa trên browser hiện tại
    if browser:
        next_proactive_restart = time.time() + (browser.lifetime_minutes * 60)
    else:
        next_proactive_restart = time.time() + (SELENIUM_LIFETIME_MINUTES * 60)

    try:
        while (time.time() - start_time) / 60 < DURATION_MINUTES:
            # ✅ FIX: Chỉ proactive restart nếu KHÔNG phải Camoufox
            if time.time() >= next_proactive_restart and browser:
                if browser.name != "Camoufox":  # Camoufox không proactive restart
                    browser_age = (time.time() - browser.started_at) / 60
                    print(f"⏰ Browser {browser.name} đã chạy {int(browser_age)} phút, proactive restart...")
                    browser = proactive_restart(browser, "định kỳ")
                    restart_count += 1
                    consecutive_failures = 0
                    if browser:
                        next_proactive_restart = time.time() + (browser.lifetime_minutes * 60)
                    else:
                        print("❌ Proactive restart fail, đợi 1 phút thử lại...")
                        time.sleep(60)
                        continue
                else:
                    # Camoufox: reset timer nhưng không restart
                    next_proactive_restart = time.time() + (browser.lifetime_minutes * 60)

            if time.time() >= next_check:
                check_count += 1
                check_success = False
                
                try:
                    if browser is None or not browser.is_alive():
                        print(f"💀 Browser đã chết sau {int((time.time()-browser.started_at)/60) if browser else 0} phút")
                        consecutive_failures += 1
                        browser = emergency_restart(browser, consecutive_failures)
                        restart_count += 1
                        if browser:
                            next_proactive_restart = time.time() + (browser.lifetime_minutes * 60)
                        if browser is None:
                            print(f"🔄 Check lần {check_count}: ❌ Không khởi động lại được browser")
                            next_check = max(next_check + CHECK_INTERVAL, time.time())
                            continue

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
                            if browser:
                                next_proactive_restart = time.time() + (browser.lifetime_minutes * 60)
                            try:
                                html = browser.fetch_fresh_html()
                            except Exception:
                                html = None
                        else:
                            print(f"⚠️ XHR lỗi: {e}")

                    if html and "just a moment" in html.lower():
                        html = recover_cloudflare(browser)
                        if html is None:
                            consecutive_failures += 1
                            browser = emergency_restart(browser, consecutive_failures)
                            restart_count += 1
                            if browser:
                                next_proactive_restart = time.time() + (browser.lifetime_minutes * 60)
                            try:
                                html = browser.fetch_fresh_html()
                            except Exception:
                                html = None

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
                                if browser:
                                    next_proactive_restart = time.time() + (browser.lifetime_minutes * 60)
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
                                if browser:
                                    next_proactive_restart = time.time() + (browser.lifetime_minutes * 60)

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
                    if browser:
                        next_proactive_restart = time.time() + (browser.lifetime_minutes * 60)

                next_check = max(next_check + CHECK_INTERVAL, time.time())

            if time.time() >= next_footer:
                msg_id = push_embed(last_regions, msg_id)
                print(f"🕐 Footer cập nhật lúc {get_hhmm()}:00 (restart: {restart_count}, consecutive: {consecutive_failures})")
                next_footer = time.time() + seconds_until_next_minute()

            time.sleep(1)

        print(f"⏰ Hết 345 phút. Bàn giao... (browser đã restart {restart_count} lần)")
    
    finally:
        # ✅ FIX: Đảm bảo cleanup browser dù có lỗi
        if browser:
            try:
                browser.close()
            except Exception:
                pass

if __name__ == "__main__":
    main()
