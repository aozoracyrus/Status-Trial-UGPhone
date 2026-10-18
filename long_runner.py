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
URL = "https://hanaminikata.com/tools/buydevice_ugphone"
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
ROLE_PING_ID = os.environ.get('ROLE_PING_ID')

DURATION_MINUTES = 345
PING_AUTO_DELETE = 300
FAIL_RESTART_THRESHOLD = 3  # Restart browser sau 3 lần fail liên tiếp
FAIL_ALERT_THRESHOLD = 10   # Alert Discord sau 10 lần fail

DATA_DIR = "data"
MSG_ID_FILE = os.path.join(DATA_DIR, "message_id.txt")
PREV_STATE_FILE = os.path.join(DATA_DIR, "prev_state.json")

REGIONS = {
    'SG': {'name': 'Singapore', 'flag': '🇸'},
    'HK': {'name': 'Hong Kong', 'flag': '🇭🇰'},
    'JP': {'name': 'Japan', 'flag': '🇯🇵'},
    'DE': {'name': 'Germany', 'flag': '🇩🇪'},
    'US': {'name': 'America', 'flag': '🇺🇸'}
}

tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')

def get_time_24h():
    return datetime.now(tz_vn).strftime("%H:%M ngày %d/%m/%Y")

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def ensure_camoufox_installed():
    try:
        r = subprocess.run(['python', '-m', 'camoufox', 'fetch'],
                           capture_output=True, text=True, timeout=120)
        return r.returncode == 0
    except Exception:
        return False

# =====================================================================
# PARSE LOGIC
# =====================================================================
def _stock_of_text(t):
    low = t.lower()
    if 'có máy' in low or 'đang còn máy' in low: return True
    if 'hết máy' in low: return False
    if '' in t: return True
    if any(k in t for k in ['🔴', '🟥', '🟠', '⚪']): return False
    return None

def parse_regions_from_text(text):
    chunks = []
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
# JS SCRIPTS
# =====================================================================
# JS này tìm thẻ <select> hoặc nút có chứa text "Singapore" để click
JS_FIND_AND_CLICK = """() => {
  // 1. Tìm thẻ select chuẩn
  let el = document.querySelector('select');
  if (el) {
    el.click();
    // Dispatch events cho các framework như React/Vue
    el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
    el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
    return { found: true, type: 'select' };
  }
  
  // 2. Tìm theo text (phòng trường hợp custom dropdown)
  const allElements = document.querySelectorAll('*');
  for (let i = 0; i < allElements.length; i++) {
    if (allElements[i].textContent.includes('Singapore') && allElements[i].children.length < 5) {
      allElements[i].click();
      return { found: true, type: 'text-match' };
    }
  }
  
  return { found: false };
}"""

JS_READ_OPTIONS = """() => {
  const out = [];
  // Đọc cả option ẩn và hiện
  document.querySelectorAll('select option, [role="option"], .dropdown-item, li').forEach(el => {
    if (el.textContent.trim()) out.push(el.textContent.trim());
  });
  return out.join('\\n---SEP---\\n');
}"""

# =====================================================================
# BROWSER CLASS
# =====================================================================
class BotBrowser:
    def __init__(self):
        if not ensure_camoufox_installed():
            raise Exception("Camoufox chưa cài")
        from camoufox.sync_api import Camoufox
        self.cm = Camoufox(headless=True)
        self.browser = self.cm.__enter__()
        self.page = self.browser.new_page()
        self.name = "Camoufox"
        print(f"✅ Browser {self.name} đã khởi động")

    def goto(self):
        self.page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        time.sleep(5) # Đợi trang load xong JS

    def is_alive(self):
        try:
            _ = self.page.content()
            return True
        except Exception:
            return False

    def click_dropdown(self):
        return self.page.evaluate(JS_FIND_AND_CLICK)

    def read_options(self):
        return self.page.evaluate(JS_READ_OPTIONS)

    def get_html(self):
        return self.page.content()

    def close(self):
        try: self.cm.__exit__(None, None, None)
        except Exception: pass

def create_browser():
    """Hàm đảm bảo luôn trả về 1 browser sống"""
    for attempt in range(3):
        try:
            b = BotBrowser()
            b.goto()
            return b
        except Exception as e:
            print(f"❌ Lỗi tạo browser lần {attempt+1}: {e}")
            time.sleep(5)
    return None

# =====================================================================
# DISCORD & STATE
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
        print(f"🚨 Alert: {content[:80]}")
    except Exception: pass

def check_and_ping(regions, prev_state):
    if not ROLE_PING_ID or not WEBHOOK_URL: return
    new_stock = [REGIONS[c]['name'] for c, v in regions.items() if v and not prev_state.get(c, False)]
    if new_stock:
        try:
            r = requests.post(f"{WEBHOOK_URL}?wait=true",
                              json={"content": f"<@&{ROLE_PING_ID}>  Server **{', '.join(new_stock)}** vừa có máy!"})
            if r.status_code == 200:
                pid = r.json().get("id")
                if pid: delete_message_after(pid, PING_AUTO_DELETE)
        except Exception: pass

# =====================================================================
# MAIN LOGIC
# =====================================================================
def main():
    print(f"🏁 Bắt đầu bot (Fix vĩnh viễn lỗi dropdown & restart)")
    msg_id, prev_state = load_state()
    last_regions = prev_state if prev_state else {c: False for c in REGIONS}
    
    browser = create_browser()
    if not browser:
        print("❌ Không thể khởi động browser. Kết thúc.")
        return

    fail_streak = 0
    restart_count = 0
    last_minute_key = None
    start_time = time.time()

    try:
        while (time.time() - start_time) / 60 < DURATION_MINUTES:
            vn_now = datetime.now(tz_vn)
            minute_key = (vn_now.day, vn_now.hour, vn_now.minute)

            if minute_key != last_minute_key:
                last_minute_key = minute_key
                regions = None
                via = "NONE"

                # 1. Kiểm tra browser sống không
                if not browser.is_alive():
                    print("💀 Browser chết. Đang tạo mới...")
                    browser.close()
                    browser = create_browser()
                    restart_count += 1

                # 2. Thử đọc dữ liệu
                try:
                    html = browser.get_html()
                    # Check Cloudflare/Login
                    if 'just a moment' in html.lower():
                        print(" Cloudflare detected. Reload trang...")
                        browser.goto()
                        html = browser.get_html()
                    
                    if 'login' in html.lower() and 'token' in html.lower():
                        print("🔐 Trang yêu cầu Login. IP bị chặn hoặc session hết hạn.")
                        regions = None
                    else:
                        # Click dropdown
                        click_res = browser.click_dropdown()
                        if not click_res or not click_res.get('found'):
                            print("⚠️ Không thấy dropdown. Reload trang...")
                            browser.goto() # Hard reload
                            time.sleep(3)
                            click_res = browser.click_dropdown() # Thử lại lần cuối

                        if click_res and click_res.get('found'):
                            time.sleep(2) # Đợi modal mở
                            options = browser.read_options()
                            if options and len(options) > 10:
                                regions = parse_regions_from_text(options)
                                via = "DROPDOWN"
                except Exception as e:
                    print(f"❌ Lỗi đọc trang: {e}")
                    regions = None

                # 3. Xử lý kết quả
                if regions and regions_complete(regions):
                    check_and_ping(regions, prev_state)
                    prev_state = regions
                    last_regions = regions
                    fail_streak = 0 # Reset fail
                    ket_qua = ", ".join(f"{c}: {bool(regions.get(c))}" for c in ['SG','HK','JP','DE','US'])
                    print(f"✅ Check [{vn_now.strftime('%H:%M')}]: {ket_qua}")
                else:
                    fail_streak += 1
                    print(f"❌ Fail lần {fail_streak} [{vn_now.strftime('%H:%M')}]")
                    
                    # 🚨 PANIC RESTART: Nếu fail 3 lần, đập browser đi xây lại
                    if fail_streak >= FAIL_RESTART_THRESHOLD:
                        print(f"🛠️ FAIL STREAK {fail_streak} -> PANIC RESTART BROWSER")
                        browser.close()
                        browser = create_browser()
                        restart_count += 1
                        fail_streak = 0 # Reset sau khi restart
                        
                        if fail_streak == 0 and fail_streak > 0: # Logic dummy để giữ cấu trúc
                            pass

                    if fail_streak == FAIL_ALERT_THRESHOLD:
                        send_alert(f"⚠️ Bot fail {fail_streak} lần liên tiếp! Cần kiểm tra.")

                # 4. Push Embed & Save
                msg_id = push_embed(last_regions, msg_id)
                save_state(msg_id, last_regions)
                print(f"🕐 Footer: {vn_now.strftime('%H:%M:%S')} (Restart: {restart_count})")

            time.sleep(0.5) # Sleep ngắn để bắt nhịp phút chính xác

    except KeyboardInterrupt:
        print("🛑 Dừng bot.")
    finally:
        if browser: browser.close()

if __name__ == "__main__":
    main()
