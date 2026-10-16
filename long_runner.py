import os
import json
import time
import re
import requests
import threading
import subprocess
from datetime import datetime
from bs4 import BeautifulSoup
import pytz

# =====================================================================
# CẤU HÌNH
# =====================================================================
URL = "https://hanaminikata.com/tools/buydevice_ugphone"   # Trang BUY (public)
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
ROLE_PING_ID = os.environ.get('ROLE_PING_ID')

DURATION_MINUTES = 345
PING_AUTO_DELETE = 300
CAMOUFOX_LIFETIME_MINUTES = 999      # Camoufox: KHÔNG proactive restart
SELENIUM_LIFETIME_MINUTES = 120      # SeleniumBase: restart mỗi 120p
FAIL_RESTART_STREAK = 3
FAIL_ALERT_STREAK = 10

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

tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')

def get_time_24h():
    return datetime.now(tz_vn).strftime("%H:%M ngày %d/%m/%Y")

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def is_browser_dead_error(e):
    s = str(e).lower()
    return any(k in s for k in BROWSER_DEAD_KEYWORDS)

def ensure_camoufox_installed():
    try:
        r = subprocess.run(['python', '-m', 'camoufox', 'fetch'],
                           capture_output=True, text=True, timeout=120)
        return r.returncode == 0
    except Exception:
        return False

# =====================================================================
# CHẨN ĐOÁN + PARSE CHẤM MÀU
# =====================================================================
def classify_html(html):
    if not html: return 'none'
    low = html.lower()
    if 'just a moment' in low or 'attention required' in low: return 'cf'
    if ('đăng nhập' in html and 'token' in low) or ('login' in low and 'token' in low): return 'login'
    if any(x in low for x in ['bad gateway', '522', '502 bad', '503', '504 gateway']): return 'server'
    return 'page'

def snippet_of(html):
    t = re.sub(r'<[^>]+>', ' ', html or '')
    t = re.sub(r'\s+', ' ', t).strip()
    return t[:180] if t else '(trống)'

def _stock_of_text(t):
    """True = còn máy, False = hết, None = không rõ"""
    low = t.lower()
    if 'có máy' in low or 'đang còn máy' in low: return True
    if 'hết máy' in low: return False
    if '🟢' in t or '' in t: return True
    if any(k in t for k in ['🔴', '🟥', '🟠', '⚪', '']): return False
    return None

def parse_regions_from_text(text):
    """Đọc 5 khu vực từ một đoạn text dài (option/li/modal body)"""
    chunks = []
    # Tách theo <option> / <li> / div option
    for pattern in [
        r'<option[^>]*>(.*?)</option>',
        r'<li[^>]*>(.*?)</li>',
        r'<div[^>]*class="[^"]*(?:option|item|region|status|server|country)[^"]*"[^>]*>(.*?)</div>',
    ]:
        for m in re.findall(pattern, text or '', re.S | re.I):
            chunks.append(m)
    if not chunks:
        chunks = [text or '']

    regions = {}
    for code, info in REGIONS.items():
        val = None
        for ch in chunks:
            plain = re.sub(r'<[^>]+>', ' ', ch)
            if info['name'].lower() in plain.lower():
                v = _stock_of_text(plain)
                if v is not None:
                    val = v
                    break
        regions[code] = val
    return regions

def regions_complete(regions):
    return regions is not None and all(v is not None for v in regions.values())

# =====================================================================
# JS: MỞ DROPDOWN + ĐỌC OPTIONS (dùng chung cho cả 2 browser)
# =====================================================================
JS_CLICK_DROP = """() => {
  // Thử mở dropdown bằng nhiều selector phổ biến
  const sels = [
    'select',
    '[role="combobox"]',
    '[class*="dropdown-toggle"]',
    '[class*="select-toggle"]',
    '[class*="dropdown"]',
    '[class*="select"]',
    '.server-select',
    '.country-select'
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el) {
      // Thử cả .click() và dispatchEvent để chắc ăn
      try { el.click(); } catch(e) {}
      try {
        el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
        el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
        el.dispatchEvent(new MouseEvent('click', {bubbles:true}));
      } catch(e) {}
      return { clicked: s, tag: el.tagName };
    }
  }
  return null;
}"""

JS_READ_ALL = """() => {
  // Đọc mọi option trong trang, cả <option>, <li>, div option, kể cả phần tử ẩn/modal
  const out = [];
  const sels = [
    'select option',
    '[role="option"]',
    '[role="listbox"] [role="option"]',
    '.dropdown-item',
    '.dropdown-menu *',
    '[class*="option"]',
    '[class*="select-menu"] *',
    '[class*="modal"] *',
    '[class*="popup"] *',
    'li',
  ];
  for (const s of sels) {
    document.querySelectorAll(s).forEach(el => {
      const t = el.textContent;
      if (t && t.trim()) out.push(t.trim());
    });
  }
  return out.join('\\n---SEP---\\n');
}"""

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

    def click_dropdown(self):
        return self.page.evaluate(JS_CLICK_DROP)

    def read_all_options(self):
        return self.page.evaluate(JS_READ_ALL)

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

    def click_dropdown(self):
        return self.driver.execute_script(f"return ({JS_CLICK_DROP})()")

    def read_all_options(self):
        return self.driver.execute_script(f"return ({JS_READ_ALL})()")

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
            time.sleep(8)
            print(f"✅ Đã mở browser: {b.name} (trang buy)")
            return b
        except Exception as e:
            print(f"❌ Lỗi Camoufox: {e}")
    try:
        b = SeleniumBaseBrowser()
        b.open_page()
        time.sleep(8)
        print(f"✅ Đã mở browser: {b.name} (trang buy)")
        return b
    except Exception as e:
        print(f"❌ Lỗi SeleniumBase: {e}")
        return None


def emergency_restart(browser, n):
    wait_time = 3 if n <= 2 else (15 if n <= 5 else 30)
    print(f"💀 Emergency restart (lần {n}, chờ {wait_time}s)...")
    if browser:
        try: browser.close()
        except Exception: pass
    time.sleep(wait_time)
    prefer = n <= 5
    if n > 5 and browser:
        prefer = not (browser.name == "Camoufox")
    nb = start_browser(prefer)
    if nb:
        wait_cloudflare(nb)
        time.sleep(5)
    return nb


def proactive_restart(browser, reason="định kỳ"):
    print(f"🔄 Proactive restart ({reason})...")
    if browser:
        try: browser.close()
        except Exception: pass
    time.sleep(15)
    nb = start_browser(browser.name == "Camoufox" if browser else True)
    if nb:
        wait_cloudflare(nb)
        time.sleep(5)
    return nb


def wait_cloudflare(browser, timeout=60):
    start = time.time()
    last_log = 0
    while time.time() - start < timeout:
        try: html = browser.get_html()
        except Exception:
            time.sleep(3); continue
        if "just a moment" not in html.lower():
            return True
        now = time.time()
        if now - last_log >= 15:
            print(f"⏳ Đang chờ Cloudflare xác minh... (đã chờ {int(now-start)}s)")
            last_log = now
        time.sleep(5)
    return False


# =====================================================================
# 🎯 LOGIC ĐỌC STOCK (MỞ DROPDOWN TRƯỚC → ĐỌC → CHỐT)
# =====================================================================
def read_stock(browser):
    """
    Bước 1: Click mở dropdown
    Bước 2: Đợi modal render (2s)
    Bước 3: Đọc tất cả option/li trong trang
    Bước 4: Parse chấm màu cho từng khu vực
    """
    # BƯỚC 1: Click dropdown
    clicked_info = None
    try:
        clicked_info = browser.click_dropdown()
        if clicked_info:
            print(f"🖱️ Đã click mở dropdown: {clicked_info}")
        else:
            print("⚠️ Không tìm thấy phần tử dropdown nào")
    except Exception as e:
        print(f"⚠️ Lỗi click dropdown: {e}")

    # BƯỚC 2: Đợi modal render
    time.sleep(2)

    # BƯỚC 3: Đọc tất cả option
    options_text = None
    try:
        options_text = browser.read_all_options()
    except Exception as e:
        if is_browser_dead_error(e):
            raise
        print(f"⚠️ Lỗi đọc options: {e}")

    # BƯỚC 4: Parse
    if not options_text:
        print("❌ Không đọc được options")
        return None, 'no-options'

    # Debug: in ra 5 option đầu tiên để anh xem format thật
    first_few = options_text.split('---SEP---')[:5]
    print(f"📋 Đọc được {len(options_text.split('---SEP---'))} chunks. Vài cái đầu:")
    for i, f in enumerate(first_few):
        print(f"   [{i}] {f[:80]}...")

    regions = parse_regions_from_text(options_text)
    if regions_complete(regions):
        return regions, "DROPDOWN"

    # Nếu thiếu, thử parse luôn cả HTML gốc
    try:
        html = browser.get_html()
        state = classify_html(html)
        if state == 'cf':
            return None, 'cf'
        if state == 'login':
            return None, 'login'
        if state == 'server':
            return None, 'server'
        regions2 = parse_regions_from_text(html)
        merged = {c: (regions[c] if regions[c] is not None else regions2.get(c))
                  for c in regions}
        if regions_complete(merged):
            return merged, "DROPDOWN+HTML"
    except Exception as e:
        if is_browser_dead_error(e): raise

    missing = [c for c, v in regions.items() if v is None]
    print(f"❓ Thiếu dữ liệu: {missing}")
    return None, 'incomplete'

# =====================================================================
# DISCORD
# =====================================================================
def load_state():
    msg_id, prev_state = None, {}
    if os.path.exists(MSG_ID_FILE):
        msg_id = open(MSG_ID_FILE).read().strip()
    if os.path.exists(PREV_STATE_FILE):
        try: prev_state = json.load(open(PREV_STATE_FILE))
        except Exception: pass
    return msg_id, prev_state

def save_state(msg_id, regions):
    ensure_data_dir()
    open(MSG_ID_FILE, 'w').write(str(msg_id))
    json.dump(regions, open(PREV_STATE_FILE, 'w'))

def delete_message_after(mid, delay):
    def _d():
        try: requests.delete(f"{WEBHOOK_URL}/messages/{mid}")
        except Exception: pass
    threading.Timer(delay, _d).start()

def build_embed(regions):
    color = 0x57f287 if any(regions.get(c) for c in REGIONS) else 0xed4245
    fields = [{"name": f"{i['flag']} {i['name']}",
               "value": "🟢 Còn máy" if regions.get(c) else "🔴 Hết máy",
               "inline": True} for c, i in REGIONS.items()]
    return {"title": "📱 Trạng thái UGPhone Trial", "color": color,
            "fields": fields, "footer": {"text": f"Uptime: {get_time_24h()}"}}

def push_embed(regions, msg_id=None):
    if not WEBHOOK_URL: return None
    payload = {"embeds": [build_embed(regions)]}
    if msg_id:
        try:
            r = requests.patch(f"{WEBHOOK_URL}/messages/{msg_id}", json=payload)
            if r.status_code == 200: return msg_id
        except Exception: pass
    try:
        r = requests.post(f"{WEBHOOK_URL}?wait=true", json=payload)
        if r.status_code == 200: return r.json().get("id")
    except Exception: pass
    return msg_id

def send_alert(content):
    if not WEBHOOK_URL: return
    try:
        requests.post(WEBHOOK_URL, json={"content": content})
        print(f"🚨 Đã gửi alert: {content[:80]}")
    except Exception: pass

def check_and_ping(regions, prev_state):
    if not ROLE_PING_ID or not WEBHOOK_URL: return
    new_stock = [REGIONS[c]['name'] for c, v in regions.items() if v and not prev_state.get(c, False)]
    if new_stock:
        try:
            r = requests.post(f"{WEBHOOK_URL}?wait=true",
                              json={"content": f"<@&{ROLE_PING_ID}> 🎉 Server **{', '.join(new_stock)}** vừa có máy!"})
            if r.status_code == 200:
                pid = r.json().get("id")
                if pid:
                    print(f"🔔 Đã ping role, tự xóa sau {PING_AUTO_DELETE}s")
                    delete_message_after(pid, PING_AUTO_DELETE)
        except Exception as e:
            print(f"⚠️ Lỗi gửi ping: {e}")

# =====================================================================
# MAIN LOOP
# =====================================================================
def main():
    print(f"🏁 Bắt đầu relay {DURATION_MINUTES} phút — nguồn: trang BUY (public)")
    print(f"   Logic đọc: MỞ DROPDOWN → đợi 2s → đọc modal → chốt")
    start_time = time.time()

    msg_id, prev_state = load_state()
    print(f"📂 Message ID hiện tại: {msg_id}")

    last_regions = prev_state if prev_state else {c: False for c in REGIONS}
    check_count = 0
    restart_count = 0
    consecutive_failures = 0
    fail_streak = 0
    last_state = 'none'
    last_minute_key = None

    browser = start_browser(prefer_camoufox=True)
    if browser and not wait_cloudflare(browser):
        print("⚠️ Cloudflare chưa qua")

    try:
        while (time.time() - start_time) / 60 < DURATION_MINUTES:

            if browser and browser.name != "Camoufox":
                age = (time.time() - browser.started_at) / 60
                if age >= browser.lifetime_minutes:
                    print(f"⏰ Browser {browser.name} chạy {int(age)}p → proactive restart...")
                    browser = proactive_restart(browser)
                    restart_count += 1
                    consecutive_failures = 0

            vn_now = datetime.now(tz_vn)
            minute_key = (vn_now.day, vn_now.hour, vn_now.minute)

            if minute_key != last_minute_key:
                last_minute_key = minute_key
                check_count += 1

                regions, via = None, ""
                try:
                    if browser is None or not browser.is_alive():
                        print("💀 Browser chết (health check)")
                        consecutive_failures += 1
                        browser = emergency_restart(browser, consecutive_failures)
                        restart_count += 1
                    if browser:
                        regions, via = read_stock(browser)
                except Exception as e:
                    if is_browser_dead_error(e):
                        print(f"💀 Browser chết giữa chừng: {str(e)[:80]}...")
                        consecutive_failures += 1
                        browser = emergency_restart(browser, consecutive_failures)
                        restart_count += 1
                        try:
                            if browser: regions, via = read_stock(browser)
                        except Exception:
                            regions = None
                    else:
                        print(f"❌ Lỗi check: {e}")

                if regions is not None:
                    check_and_ping(regions, prev_state)
                    prev_state = regions
                    last_regions = regions
                    consecutive_failures = 0
                    fail_streak = 0
                    ket_qua = ", ".join(f"{c}: {bool(regions.get(c))}" for c in ['SG','HK','JP','DE','US'])
                else:
                    fail_streak += 1
                    last_state = via or last_state
                    if last_state == 'login':
                        print("🔐 Trang buy đòi đăng nhập với IP này")
                    if fail_streak == FAIL_RESTART_STREAK:
                        print("🛠️ Fail 3 lần liên tiếp → restart browser...")
                        browser = emergency_restart(browser, 1)
                        restart_count += 1
                    if fail_streak == FAIL_ALERT_STREAK or (fail_streak > FAIL_ALERT_STREAK and fail_streak % 60 == 0):
                        send_alert(f"⚠️ Bot UGPhone KHÔNG đọc được stock {fail_streak} phút liên tiếp! "
                                   f"Trạng thái: `{last_state}`. Vào Actions xem log!")

                msg_id = push_embed(last_regions, msg_id)
                save_state(msg_id, last_regions)
                now_vn = datetime.now(tz_vn)
                if regions is not None:
                    print(f"🔄 Check lần {check_count} [{now_vn.strftime('%H:%M')}] ({via}): {ket_qua}")
                else:
                    print(f"🔄 Check lần {check_count} [{now_vn.strftime('%H:%M')}]: ❌ Chưa lấy được dữ liệu (fail {fail_streak})")
                print(f"🕐 Footer cập nhật lúc {now_vn.strftime('%H:%M:%S')} (restart: {restart_count})")

            time.sleep(0.2)

    finally:
        print(f"⏰ Kết thúc relay... (restart {restart_count} lần)")
        if browser:
            try: browser.close()
            except Exception: pass

if __name__ == "__main__":
    main()
