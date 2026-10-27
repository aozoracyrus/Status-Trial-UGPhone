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
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
ROLE_PING_ID = os.environ.get('ROLE_PING_ID')

DURATION_MINUTES = 345
PING_AUTO_DELETE = 300

# ✅ Theo yêu cầu: chờ đủ lâu cho Xvfb + Turnstile tự verify
WAIT_AFTER_GOTO_MS = 12000      # 12s sau goto (anh yêu cầu 10-15s)
WAIT_UI_TIMEOUT_MS = 15000      # tối đa 15s đợi text 'Tạo máy UGPhone'
UI_MARKER_TEXT = "Tạo máy UGPhone"   # dấu hiệu UI THẬT đã load

# ✅ KHÔNG panic restart. fail_streak CHỈ dùng để alert Discord.
FAIL_ALERT_THRESHOLD = 10

# ✅ Chỉ mở lại browser khi CHẾT THẬT, có cooldown + giới hạn
MAX_BROWSER_REOPEN = 3
REOPEN_COOLDOWN_S = 60          # chờ IP "nguội" trước khi mở lại

DATA_DIR = "data"
DEBUG_DIR = os.path.join(DATA_DIR, "debug")
MSG_ID_FILE = os.path.join(DATA_DIR, "message_id.txt")
PREV_STATE_FILE = os.path.join(DATA_DIR, "prev_state.json")
DEBUG_SHOT = os.path.join(DEBUG_DIR, "last_error.png")

REGIONS = {
    'SG': {'name': 'Singapore', 'flag': '🇸'},
    'HK': {'name': 'Hong Kong', 'flag': '🇭'},
    'JP': {'name': 'Japan', 'flag': '🇯🇵'},
    'DE': {'name': 'Germany', 'flag': '🇩🇪'},
    'US': {'name': 'America', 'flag': '🇺🇸'}
}

VIEWPORT = {'width': 1920, 'height': 1080}   # ✅ đồng bộ Xvfb

tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
def get_time_24h():
    return datetime.now(tz_vn).strftime("%H:%M ngày %d/%m/%Y")

def ensure_dirs():
    for d in (DATA_DIR, DEBUG_DIR):
        if not os.path.exists(d):
            os.makedirs(d)

def ensure_camoufox_installed():
    try:
        r = subprocess.run(['python', '-m', 'camoufox', 'fetch'],
                           capture_output=True, text=True, timeout=180)
        return r.returncode == 0
    except Exception:
        return False

# =====================================================================
# PARSE CHẤM MÀU (giữ nguyên, đã ổn định)
# =====================================================================
def _stock_of_text(t):
    low = t.lower()
    if 'có máy' in low or 'đang còn máy' in low: return True
    if 'hết máy' in low: return False
    if '🟢' in t: return True
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
# JS
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
# BROWSER - HEADFUL, VIEWPORT CHUẨN, KIÊN NHẪN, KHÔNG PANIC
# =====================================================================
DEAD_MARKERS = (
    'target closed', 'target page, context or browser',
    'browser has been closed', 'no such window', 'connection refused',
    'httpconnectionpool', 'net::err_connection'
)

def _is_really_dead(e):
    m = str(e).lower()
    return any(k in m for k in DEAD_MARKERS)

class PatientBrowser:
    def __init__(self):
        if not ensure_camoufox_installed():
            raise Exception("Camoufox chưa cài")
        from camoufox.sync_api import Camoufox
        # ✅ headful + humanize, KHÔNG chặn ảnh (giống người thật)
        self.cm = Camoufox(headless=False, humanize=True, block_images=False)
        self.browser = self.cm.__enter__()
        # ✅ viewport 1920x1080 đồng bộ Xvfb để toạ độ Turnstile chính xác
        self.page = self.browser.new_page(viewport=VIEWPORT)
        try:
            self.page.set_viewport_size(VIEWPORT)
        except Exception:
            pass
        self.page.set_default_timeout(30000)
        self.name = "Camoufox-Headful"
        print(f"✅ Browser {self.name} đã khởi động (viewport {VIEWPORT['width']}x{VIEWPORT['height']})")

    def load_and_wait(self, url):
        """goto + chờ đủ lâu cho Xvfb render + Turnstile tự verify."""
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(WAIT_AFTER_GOTO_MS)   # ✅ 12s kiên nhẫn

    def try_click_turnstile(self):
        """Best-effort click vùng Turnstile (null-safe, KHÔNG fail nếu không có)."""
        try:
            el = self.page.query_selector(
                'iframe[src*="challenges.cloudflare.com"], iframe[title*="Cloudflare"]'
            )
            if el:
                box = el.bounding_box()
                if box:
                    self.page.mouse.click(
                        box['x'] + box['width'] / 2,
                        box['y'] + box['height'] / 2
                    )
                    print("🖱️ Đã click vào vùng Turnstile (best-effort)")
                    self.page.wait_for_timeout(3000)
                    return True
        except Exception as e:
            print(f"⚠️ try_click_turnstile bỏ qua: {e}")
        return False

    def wait_for_real_ui(self):
        """✅ CHỈ đợi text 'Tạo máy UGPhone' = UI thật đã load. Trả bool, KHÔNG raise."""
        try:
            self.page.get_by_text(UI_MARKER_TEXT, exact=False).first.wait_for(
                state="visible", timeout=WAIT_UI_TIMEOUT_MS
            )
            return True
        except Exception:
            return False

    def click_dropdown(self):
        try:
            return self.page.evaluate(JS_FIND_AND_CLICK)
        except Exception as e:
            if _is_really_dead(e):
                raise
            return None

    def read_options(self):
        try:
            return self.page.evaluate(JS_READ_OPTIONS)
        except Exception as e:
            if _is_really_dead(e):
                raise
            return None

    def screenshot_debug(self):
        """✅ Lỗi thì chụp ảnh, KHÔNG restart."""
        try:
            ensure_dirs()
            self.page.screenshot(path=DEBUG_SHOT, full_page=True)
            print(f"📸 Đã chụp debug -> {DEBUG_SHOT}")
        except Exception as e:
            print(f"⚠️ Chụp debug thất bại: {e}")

    def is_really_alive(self):
        try:
            _ = self.page.title()
            return True
        except Exception as e:
            return not _is_really_dead(e)   # navigation != chết

    def close(self):
        try: self.cm.__exit__(None, None, None)
        except Exception: pass

def open_browser():
    try:
        b = PatientBrowser()
        b.load_and_wait(TARGET_URL)
        return b
    except Exception as e:
        print(f"❌ Mở browser lỗi: {e}")
        return None

# =====================================================================
# DISCORD & STATE (giữ nguyên)
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
    ensure_dirs()
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
# MAIN LOOP - KIÊN NHẪN, KHÔNG PANIC, GIỮ cf_clearance
# =====================================================================
def main():
    print(f"🏁 Bắt đầu bot (HEADFUL + kiên nhẫn, KHÔNG login-wall check, KHÔNG panic restart)")
    print(f"   Target: {TARGET_URL}")
    print(f"   Chờ sau goto: {WAIT_AFTER_GOTO_MS}ms | Đợi UI: {WAIT_UI_TIMEOUT_MS}ms | Viewport: {VIEWPORT}")

    ensure_dirs()
    msg_id, prev_state = load_state()
    last_regions = prev_state if prev_state else {c: False for c in REGIONS}

    browser = open_browser()
    if not browser:
        print("❌ Không mở được browser lần đầu. Kết thúc job (relay job sau sẽ thử).")
        return

    fail_streak = 0
    reopen_count = 0
    last_minute_key = None
    start_time = time.time()

    try:
        while (time.time() - start_time) / 60 < DURATION_MINUTES:
            vn_now = datetime.now(tz_vn)
            minute_key = (vn_now.day, vn_now.hour, vn_now.minute)
            if minute_key == last_minute_key:
                time.sleep(0.5)
                continue
            last_minute_key = minute_key

            regions = None
            via = "NONE"
            soft_fail = False   # ✅ lỗi "mềm": UI chưa load / parse thiếu -> KHÔNG restart

            try:
                # Reload NHẸ trên cùng browser (giữ cf_clearance tích luỹ)
                browser.load_and_wait(TARGET_URL)
                browser.try_click_turnstile()

                # ✅ CHỈ đợi UI thật. Không check login, không check 'just a moment'.
                if not browser.wait_for_real_ui():
                    print(f"⏳ [{vn_now.strftime('%H:%M')}] UI '{UI_MARKER_TEXT}' chưa hiện "
                          f"(Xvfb chậm / Turnstile đang verify) -> giữ browser, thử lại phút sau. KHÔNG restart.")
                    browser.screenshot_debug()
                    soft_fail = True
                else:
                    click_res = browser.click_dropdown()
                    if not click_res or not click_res.get('found'):
                        print(f"⚠️ [{vn_now.strftime('%H:%M')}] Không thấy dropdown -> chụp debug, KHÔNG restart.")
                        browser.screenshot_debug()
                        soft_fail = True
                    else:
                        browser.page.wait_for_timeout(2000)
                        options = browser.read_options()
                        if options and len(options) > 10:
                            parsed = parse_regions_from_text(options)
                            if regions_complete(parsed):
                                regions = parsed
                                via = "DROPDOWN"
                            else:
                                print(f"⚠️ [{vn_now.strftime('%H:%M')}] Parse thiếu region -> chụp debug, KHÔNG restart.")
                                browser.screenshot_debug()
                                soft_fail = True
                        else:
                            print(f"⚠️ [{vn_now.strftime('%H:%M')}] Không đọc được options -> chụp debug, KHÔNG restart.")
                            browser.screenshot_debug()
                            soft_fail = True

            except Exception as e:
                if _is_really_dead(e):
                    # ✅ Browser CHẾT THẬT -> mới mở lại, có cooldown + giới hạn
                    print(f"💀 Browser chết thật: {str(e)[:80]}...")
                    try: browser.close()
                    except Exception: pass
                    reopen_count += 1
                    if reopen_count > MAX_BROWSER_REOPEN:
                        print(f"🛑 Đã mở lại {reopen_count} lần (quá giới hạn {MAX_BROWSER_REOPEN}). "
                              f"Kết thúc job êm để relay job sau tiếp (IP đã nguội).")
                        break
                    print(f"⏳ Cooldown {REOPEN_COOLDOWN_S}s cho IP nguội trước khi mở lại...")
                    time.sleep(REOPEN_COOLDOWN_S)
                    browser = open_browser()
                    if not browser:
                        print("❌ Mở lại thất bại. Kết thúc job êm.")
                        break
                    soft_fail = True
                else:
                    # Exception lạ (không phải chết) -> coi như soft fail, KHÔNG restart
                    print(f"⚠️ Lỗi mềm: {e} -> chụp debug, giữ browser, KHÔNG restart.")
                    try: browser.screenshot_debug()
                    except Exception: pass
                    soft_fail = True

            # ✅ Xử lý kết quả: soft_fail CHỈ tăng streak để alert, KHÔNG đụng browser
            if regions is not None:
                check_and_ping(regions, prev_state)
                prev_state = regions
                last_regions = regions
                fail_streak = 0
                ket_qua = ", ".join(f"{c}: {bool(regions.get(c))}" for c in ['SG','HK','JP','DE','US'])
                print(f"✅ Check [{vn_now.strftime('%H:%M')}] ({via}): {ket_qua}")
            else:
                fail_streak += 1
                print(f"❌ Fail lần {fail_streak} [{vn_now.strftime('%H:%M')}] "
                      f"({'soft - giữ browser' if soft_fail else 'unknown'})")
                if fail_streak == FAIL_ALERT_THRESHOLD or (fail_streak > FAIL_ALERT_THRESHOLD and fail_streak % 60 == 0):
                    send_alert(f"⚠️ Bot UGPhone không đọc được stock {fail_streak} phút liên tiếp "
                               f"(đã chụp debug/data/last_error.png). KHÔNG panic restart - đang kiên nhẫn chờ.")

            msg_id = push_embed(last_regions, msg_id)
            save_state(msg_id, last_regions)
            print(f"🕐 Footer: {vn_now.strftime('%H:%M:%S')} (reopen thật: {reopen_count})")

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("🛑 Dừng bot.")
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        print(f"⏰ Kết thúc job. (browser mở lại thật: {reopen_count} lần)")

if __name__ == "__main__":
    main()
