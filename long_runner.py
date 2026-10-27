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
COOKIES_FILE = "cookies.json"

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
                           capture_output=True, text=True, timeout=180)
        return r.returncode == 0
    except Exception:
        return False

# =====================================================================
# COOKIES (optional - Chrome khong login van vao duoc nen day chi du phong)
# =====================================================================
def load_hanami_cookies():
    cookies_data = None
    env_cookies = os.environ.get('HANAMI_COOKIES')
    if env_cookies:
        try:
            cookies_data = json.loads(env_cookies)
            print("🍪 Đã load cookies từ GitHub Secret")
        except Exception as e:
            print(f"⚠️ Lỗi parse HANAMI_COOKIES: {e}")
    if cookies_data is None and os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, 'r') as f:
                cookies_data = json.load(f)
            print(f"🍪 Đã load cookies từ file {COOKIES_FILE}")
        except Exception as e:
            print(f"⚠️ Lỗi đọc file cookies: {e}")
    if not cookies_data:
        return []
    hanami_cookies = []
    for cookie in cookies_data:
        domain = cookie.get('domain', '')
        name = cookie.get('name', '')
        if 'hanaminikata.com' in domain and name != 'cf_clearance':
            hanami_cookies.append(cookie)
    print(f"✅ Chuẩn bị {len(hanami_cookies)} cookies Hanami (dự phòng)")
    return hanami_cookies

def inject_cookies(page, cookies):
    if not cookies:
        return False
    try:
        formatted = []
        for c in cookies:
            formatted.append({
                'name': c['name'],
                'value': c['value'],
                'domain': c.get('domain', '.hanaminikata.com'),
                'path': c.get('path', '/'),
                'expires': c.get('expires', -1),
                'secure': c.get('secure', True),
                'httpOnly': c.get('httpOnly', False),
                'sameSite': c.get('sameSite', 'Lax')
            })
        page.context.add_cookies(formatted)
        print(f"✅ Đã inject {len(formatted)} cookies")
        return True
    except Exception as e:
        print(f"⚠️ Lỗi inject cookies: {e}")
        return False

# =====================================================================
# ANTI-DEBUG / CHAN REDIRECT VE TRANG CHU
# =====================================================================
ANTI_DEBUG_BYPASS = """
(function() {
    const origReplace = window.location.replace;
    const origAssign = window.location.assign;
    const allow = (u) => !u || u.includes('buydevice') || u.includes('/tc');
    window.location.replace = function(url) {
        if (!allow(url)) { console.log('[BOT] Chan replace:', url); return; }
        return origReplace.call(window.location, url);
    };
    window.location.assign = function(url) {
        if (!allow(url)) { console.log('[BOT] Chan assign:', url); return; }
        return origAssign.call(window.location, url);
    };
    const origPush = history.pushState;
    const origRep = history.replaceState;
    history.pushState = function() {
        if (!allow(arguments[2])) { console.log('[BOT] Chan pushState:', arguments[2]); return; }
        return origPush.apply(history, arguments);
    };
    history.replaceState = function() {
        if (!allow(arguments[2])) { console.log('[BOT] Chan replaceState:', arguments[2]); return; }
        return origRep.apply(history, arguments);
    };
    console.log('[BOT] Anti-debug + chan redirect ON');
})();
"""

CHECK_URL_SCRIPT = "() => window.location.href"

# =====================================================================
# PARSE CHAM MAU
# =====================================================================
def _stock_of_text(t):
    low = t.lower()
    if 'có máy' in low or 'đang còn máy' in low: return True
    if 'hết máy' in low: return False
    if '' in t: return True
    if any(k in t for k in ['🔴', '🟥', '🟠', '', '']): return False
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
# JS CLICK DROPDOWN + DOC OPTIONS
# =====================================================================
JS_FIND_AND_CLICK = """() => {
  let el = document.querySelector('select');
  if (el) {
    el.click();
    el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
    el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
    return { found: true, type: 'select' };
  }
  const all = document.querySelectorAll('*');
  for (let i = 0; i < all.length; i++) {
    if (all[i].textContent.includes('Singapore') && all[i].children.length < 5) {
      all[i].click();
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
# BROWSER CLASS - FIX: HEADLESS=FALSE + HUMANIZE
# =====================================================================
class ProtectedBotBrowser:
    def __init__(self, cookies=None):
        if not ensure_camoufox_installed():
            raise Exception("Camoufox chưa cài")
        from camoufox.sync_api import Camoufox
        # FIX CHINH: headless=False de giong Chrome/Quetta that, kh lo webdriver
        self.cm = Camoufox(
            headless=False,
            humanize=True,
            block_images=False
        )
        self.browser = self.cm.__enter__()
        self.page = self.browser.new_page()
        self.name = "Camoufox-Headed"
        self.last_url = None
        if cookies:
            inject_cookies(self.page, cookies)
        print(f"✅ Browser {self.name} đã khởi động (HEADED + humanize)")

    def goto_with_protection(self, url):
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            try:
                self.page.evaluate(ANTI_DEBUG_BYPASS)
                print("🛡️ Anti-debug + chan redirect injected")
            except Exception as e:
                print(f"⚠️ Không inject được anti-debug: {e}")
            self.last_url = url
            return True
        except Exception as e:
            print(f"❌ Lỗi goto: {e}")
            return False

    def check_and_fix_url(self):
        try:
            cur = self.page.evaluate(CHECK_URL_SCRIPT)
            if cur and not ('buydevice' in cur or '/tc' in cur):
                print(f"⚠️ Bị redirect về: {cur[:80]}... Ép về trang đích!")
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

def create_protected_browser(cookies=None):
    for attempt in range(3):
        try:
            b = ProtectedBotBrowser(cookies=cookies)
            if b.goto_with_protection(TARGET_URL):
                time.sleep(5)
                return b
        except Exception as e:
            print(f"❌ Lỗi tạo browser lần {attempt+1}: {e}")
            time.sleep(5)
    return None

# =====================================================================
# WAIT CLOUDFLARE
# =====================================================================
def wait_cloudflare(browser, timeout=90):
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
            if elapsed > 5:
                print(f"✅ Đã qua Cloudflare sau {elapsed}s")
            return True
        now = time.time()
        if now - last_log >= 15:
            print(f"⏳ Đang chờ Cloudflare xác minh... (đã chờ {int(now-start)}s)")
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
# MAIN LOOP
# =====================================================================
def main():
    print(f"🏁 Bắt đầu bot (HEADED + humanize - fix fingerprint)")
    print(f"   Target: {TARGET_URL}")

    hanami_cookies = load_hanami_cookies()
    msg_id, prev_state = load_state()
    last_regions = prev_state if prev_state else {c: False for c in REGIONS}

    browser = create_protected_browser(cookies=hanami_cookies)
    if not browser:
        print("❌ Không thể khởi động browser. Kết thúc.")
        return

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
                            browser = create_protected_browser(cookies=hanami_cookies)
                            restart_count += 1
                            if not browser: break
                            if not wait_cloudflare(browser, timeout=90):
                                continue

                        if not browser.check_and_fix_url():
                            browser.goto_with_protection(TARGET_URL)
                            time.sleep(3)

                        html = browser.get_html()

                        if 'just a moment' in html.lower():
                            print("🛡️ Cloudflare detected. Đang đợi...")
                            if not wait_cloudflare(browser, timeout=60):
                                browser.goto_with_protection(TARGET_URL)
                                if not wait_cloudflare(browser, timeout=60):
                                    continue
                            html = browser.get_html()

                        if 'login' in html.lower() and 'token' in html.lower():
                            print("🔐 Vẫn bị login wall dù headed -> fingerprint sâu hơn (TLS/JA3)")
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
                        browser = create_protected_browser(cookies=hanami_cookies)
                        restart_count += 1
                        fail_streak = 0
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
