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
TARGET_URL = "https://hanaminikata.com/tools/buydevice_ugphone"
FALLBACK_URL = "https://hanaminikata.com/tc"
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
ROLE_PING_ID = os.environ.get('ROLE_PING_ID')

DURATION_MINUTES = 345
PING_AUTO_DELETE = 300
FAIL_RESTART_THRESHOLD = 3
FAIL_ALERT_THRESHOLD = 10
MAX_RETRY_PER_CHECK = 3

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
# 🛡️ SCRIPT CHỐNG ANTI-CONSOLE & REDIRECT
# =====================================================================
ANTI_DEBUG_BYPASS = """
(function() {
    const originalDebugger = Function.prototype.constructor;
    Function.prototype.constructor = function(code) {
        if (code === 'debugger') return function() {};
        return originalDebugger.apply(this, arguments);
    };

    const originalToString = Function.prototype.toString;
    Function.prototype.toString = function() {
        if (this === console || this === window.console) {
            return 'function console() { [native code] }';
        }
        return originalToString.apply(this, arguments);
    };

    const originalReplace = window.location.replace;
    const originalAssign = window.location.assign;
    window.location.replace = function(url) {
        if (url.includes('hanaminikata.com') && !url.includes('buydevice') && !url.includes('tc')) {
            console.log('[BOT] Chặn redirect về:', url);
            return;
        }
        return originalReplace.call(window.location, url);
    };
    window.location.assign = function(url) {
        if (url.includes('hanaminikata.com') && !url.includes('buydevice') && !url.includes('tc')) {
            console.log('[BOT] Chặn assign về:', url);
            return;
        }
        return originalAssign.call(window.location, url);
    };

    const originalPushState = history.pushState;
    const originalReplaceState = history.replaceState;
    history.pushState = function() {
        const url = arguments[2];
        if (url && url.includes('hanaminikata.com') && !url.includes('buydevice') && !url.includes('tc')) {
            console.log('[BOT] Chặn pushState về:', url);
            return;
        }
        return originalPushState.apply(history, arguments);
    };
    history.replaceState = function() {
        const url = arguments[2];
        if (url && url.includes('hanaminikata.com') && !url.includes('buydevice') && !url.includes('tc')) {
            console.log('[BOT] Chặn replaceState về:', url);
            return;
        }
        return originalReplaceState.apply(history, arguments);
    };

    console.log('[BOT] Anti-debug bypass activated');
})();
"""

CHECK_URL_SCRIPT = """() => {
    return window.location.href;
}"""

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
        r'<span[^>]*>([^<]*(?:Singapore|Hong Kong|Japan|Germany|America)[^<]*)</span>',
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
JS_FIND_AND_CLICK = """() => {
  let el = document.querySelector('select');
  if (el) {
    el.click();
    el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
    el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
    return { found: true, type: 'select' };
  }
  
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
  document.querySelectorAll('select option, [role="option"], .dropdown-item, li').forEach(el => {
    if (el.textContent.trim()) out.push(el.textContent.trim());
  });
  return out.join('\\n---SEP---\\n');
}"""

# =====================================================================
# BROWSER CLASS
# =====================================================================
class ProtectedBotBrowser:
    def __init__(self):
        if not ensure_camoufox_installed():
            raise Exception("Camoufox chưa cài")
        from camoufox.sync_api import Camoufox
        self.cm = Camoufox(
            headless=True,
            block_images=False
        )
        self.browser = self.cm.__enter__()
        self.page = self.browser.new_page()
        self.name = "Camoufox-Protected"
        self.last_url = None
        print(f"✅ Browser {self.name} đã khởi động (Anti-debug enabled)")

    def goto_with_protection(self, url):
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            
            try:
                self.page.evaluate(ANTI_DEBUG_BYPASS)
                print("🛡️ Anti-debug script injected")
            except Exception as e:
                print(f"⚠️ Không inject được anti-debug: {e}")
            
            self.last_url = url
            return True
        except Exception as e:
            print(f"❌ Lỗi goto: {e}")
            return False

    def check_and_fix_url(self):
        try:
            current_url = self.page.evaluate(CHECK_URL_SCRIPT)
            if current_url and not ('buydevice' in current_url or 'tc' in current_url):
                print(f"⚠️ Bị redirect về: {current_url[:80]}... Ép về trang đích!")
                return self.goto_with_protection(TARGET_URL)
            return True
        except Exception as e:
            print(f"❌ Lỗi check URL: {e}")
            return False

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
        self.check_and_fix_url()
        return self.page.content()

    def close(self):
        try: self.cm.__exit__(None, None, None)
        except Exception: pass

def create_protected_browser():
    for attempt in range(3):
        try:
            b = ProtectedBotBrowser()
            if b.goto_with_protection(TARGET_URL):
                time.sleep(5)
                return b
        except Exception as e:
            print(f"❌ Lỗi tạo browser lần {attempt+1}: {e}")
            time.sleep(5)
    return None

# =====================================================================
# ✅ THÊM LẠI HÀM WAIT CLOUDFLARE (ĐỢI ĐÚNG CÁCH)
# =====================================================================
def wait_cloudflare(browser, timeout=90):
    """Đợi Cloudflare challenge hoàn tất (tối đa 90 giây)"""
    start = time.time()
    last_log = 0
    
    while time.time() - start < timeout:
        try:
            html = browser.get_html()
        except Exception:
            time.sleep(3)
            continue
        
        if "just a moment" not in html.lower():
            elapsed = int(time.time() - start)
            if elapsed > 5:  # Chỉ in nếu đợi > 5 giây
                print(f"✅ Đã qua Cloudflare sau {elapsed}s")
            return True
        
        now = time.time()
        if now - last_log >= 15:
            elapsed = int(now - start)
            print(f"⏳ Đang chờ Cloudflare xác minh... (đã chờ {elapsed}s)")
            last_log = now
        
        time.sleep(5)
    
    print(f"❌ Timeout: Cloudflare không qua sau {timeout}s")
    return False

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
                              json={"content": f"<@&{ROLE_PING_ID}> 🎉 Server **{', '.join(new_stock)}** vừa có máy!"})
            if r.status_code == 200:
                pid = r.json().get("id")
                if pid: delete_message_after(pid, PING_AUTO_DELETE)
        except Exception: pass

# =====================================================================
# MAIN LOGIC (FIXED: WAIT CLOUDFLARE ĐÚNG CÁCH)
# =====================================================================
def main():
    print(f"🏁 Bắt đầu bot (Chống Anti-Console + Auto-Recovery)")
    print(f"   Target: {TARGET_URL}")
    print(f"   Fallback: {FALLBACK_URL}")
    
    msg_id, prev_state = load_state()
    last_regions = prev_state if prev_state else {c: False for c in REGIONS}
    
    browser = create_protected_browser()
    if not browser:
        print("❌ Không thể khởi động browser. Kết thúc.")
        return

    # ✅ ĐỢI CLOUDFLARE LẦN ĐẦU
    if not wait_cloudflare(browser, timeout=120):
        print("⚠️ Cloudflare chưa qua lần đầu, sẽ thử lại trong loop")

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
                success = False

                for retry in range(MAX_RETRY_PER_CHECK):
                    try:
                        if not browser.is_alive():
                            print("💀 Browser chết. Đang tạo mới...")
                            browser.close()
                            browser = create_protected_browser()
                            restart_count += 1
                            if not browser: break
                            
                            # ✅ ĐỢI CLOUDFLARE SAU KHI TẠO MỚI
                            if not wait_cloudflare(browser, timeout=90):
                                print("❌ Cloudflare không qua sau restart")
                                continue

                        if not browser.check_and_fix_url():
                            print("⚠️ Không fix được URL, reload trang...")
                            browser.goto_with_protection(TARGET_URL)
                            time.sleep(3)

                        html = browser.get_html()
                        
                        # ✅ FIX: DÙNG wait_cloudflare THAY VÌ sleep 10s
                        if 'just a moment' in html.lower():
                            print("🛡️ Cloudflare detected. Đang đợi...")
                            if not wait_cloudflare(browser, timeout=60):
                                print("❌ Cloudflare không qua, retry...")
                                browser.goto_with_protection(TARGET_URL)
                                if not wait_cloudflare(browser, timeout=60):
                                    continue
                            html = browser.get_html()
                        
                        if 'login' in html.lower() and 'token' in html.lower():
                            print("🔐 Trang yêu cầu Login. Thử fallback URL...")
                            browser.goto_with_protection(FALLBACK_URL)
                            time.sleep(3)
                            html = browser.get_html()
                            if 'login' in html.lower():
                                print("❌ Fallback cũng yêu cầu login. Skip phút này.")
                                break

                        click_res = browser.click_dropdown()
                        if not click_res or not click_res.get('found'):
                            print(f"⚠️ Không thấy dropdown (lần {retry+1}/{MAX_RETRY_PER_CHECK})")
                            time.sleep(5)
                            browser.goto_with_protection(TARGET_URL)
                            time.sleep(3)
                            continue

                        time.sleep(2)
                        options = browser.read_options()
                        
                        if options and len(options) > 10:
                            regions = parse_regions_from_text(options)
                            if regions_complete(regions):
                                via = "DROPDOWN"
                                success = True
                                break
                            else:
                                print(f"⚠️ Parse thiếu data (lần {retry+1})")
                        else:
                            print(f"⚠️ Không đọc được options (lần {retry+1})")
                        
                        time.sleep(5)
                        
                    except Exception as e:
                        print(f"❌ Lỗi retry {retry+1}: {e}")
                        time.sleep(5)
                        continue

                if success and regions:
                    check_and_ping(regions, prev_state)
                    prev_state = regions
                    last_regions = regions
                    fail_streak = 0
                    ket_qua = ", ".join(f"{c}: {bool(regions.get(c))}" for c in ['SG','HK','JP','DE','US'])
                    print(f"✅ Check [{vn_now.strftime('%H:%M')}] ({via}): {ket_qua}")
                else:
                    fail_streak += 1
                    print(f"❌ Fail lần {fail_streak} [{vn_now.strftime('%H:%M')}]")
                    
                    if fail_streak >= FAIL_RESTART_THRESHOLD:
                        print(f"🛠️ FAIL STREAK {fail_streak} -> PANIC RESTART")
                        browser.close()
                        browser = create_protected_browser()
                        restart_count += 1
                        fail_streak = 0
                        
                        # ✅ ĐỢI CLOUDFLARE SAU PANIC RESTART
                        if browser and not wait_cloudflare(browser, timeout=90):
                            print("❌ Cloudflare không qua sau panic restart")
                    
                    if fail_streak == FAIL_ALERT_THRESHOLD:
                        send_alert(f"⚠️ Bot fail {fail_streak} lần liên tiếp!")

                msg_id = push_embed(last_regions, msg_id)
                save_state(msg_id, last_regions)
                print(f"🕐 Footer: {vn_now.strftime('%H:%M:%S')} (Restart: {restart_count})")

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("🛑 Dừng bot.")
    finally:
        if browser: browser.close()

if __name__ == "__main__":
    main()
