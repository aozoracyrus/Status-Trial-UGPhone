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
WAIT_AFTER_GOTO_MS = 12000      # chỉ dùng lúc goto THẬT (mở/reset), không dùng mỗi phút
WAIT_UI_TIMEOUT_MS = 15000
UI_MARKER_TEXT = "Tạo máy UGPhone"
FAIL_ALERT_THRESHOLD = 10

# --- 🆕 v4.3: GREEN dùng fetch (KHÔNG navigation) ---
FETCH_ERR_MARK = '__FETCH_ERR__'
MAX_FETCH_ERR = 3               # fetch lỗi liên tiếp bao nhiêu lần thì mới goto reset

# --- Nhóm "chủ động navigation có节流" (goto thật) ---
CF_STUCK_RESTART_MIN = 4        # kẹt CF >= bấy nhiêu phút (sau đã click) thì reset context
MAX_CF_RESTART = 3              # trần reset context mỗi job
CF_RESTART_COOLDOWN_S = 30
MAX_REAL_GOTO = 6               # 🆕 trần số lần goto THẬT mỗi job (mở + reset); vượt -> dừng êm
UNK_GIVEUP_MIN = 8

# --- browser chết thật ---
MAX_BROWSER_REOPEN = 3
REOPEN_COOLDOWN_S = 60

DATA_DIR = "data"
DEBUG_DIR = os.path.join(DATA_DIR, "debug")
MSG_ID_FILE = os.path.join(DATA_DIR, "message_id.txt")
PREV_STATE_FILE = os.path.join(DATA_DIR, "prev_state.json")
DEBUG_SHOT = os.path.join(DEBUG_DIR, "last_error.png")

REGIONS = {
    'SG': {'name': 'Singapore', 'flag': '🇸🇬'},
    'HK': {'name': 'Hong Kong', 'flag': '🇭'},
    'JP': {'name': 'Japan', 'flag': '🇯🇵'},
    'DE': {'name': 'Germany', 'flag': '🇩🇪'},
    'US': {'name': 'America', 'flag': '🇺🇸'}
}
VIEWPORT = {'width': 1920, 'height': 1080}

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
# PHÂN LOẠI TRANG BẰNG CHUỖI (không đoán mò; KHÔNG có login/token)
# =====================================================================
def has_real_ui(html):
    return bool(html) and (UI_MARKER_TEXT.lower() in html.lower())

def is_server_error(html):
    if not html:
        return False
    low = html.lower()
    return any(m in low for m in (
        'error code 520', 'returning an unknown error',
        'error 521', 'error 522', 'error 523',
        'bad gateway', 'service temporarily unavailable',
        'gateway time-out', 'gateway timeout', 'origin error'))

def is_cf_verifying(html):
    if not html:
        return False
    low = html.lower()
    return any(m in low for m in (
        'verifying you are human', 'this may take a few seconds',
        'checking your browser', 'just a moment'))

def classify(html):
    if has_real_ui(html):
        return 'GREEN'
    if is_server_error(html):
        return 'SRV'
    if is_cf_verifying(html):
        return 'CF'
    return 'UNK'

# =====================================================================
# PARSE CHẤM MÀU (chạy được trên HTML thô từ fetch: regex <option>)
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
# 🆕 fetch BÊN TRONG trang (cùng origin+session) -> CF KHÔNG coi là navigation
JS_FETCH = """async (url) => {
  try {
    const r = await fetch(url + '?t=' + Date.now(), {credentials: 'include'});
    return await r.text();
  } catch (e) {
    return '__FETCH_ERR__' + String(e);
  }
}"""

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

DEAD_MARKERS = (
    'target closed', 'target page, context or browser',
    'browser has been closed', 'no such window', 'connection refused',
    'httpconnectionpool', 'net::err_connection')
def _is_really_dead(e):
    m = str(e).lower()
    return any(k in m for k in DEAD_MARKERS)

# =====================================================================
# BROWSER
# =====================================================================
class PatientBrowser:
    def __init__(self):
        if not ensure_camoufox_installed():
            raise Exception("Camoufox chưa cài")
        from camoufox.sync_api import Camoufox
        self.cm = Camoufox(headless=False, humanize=True, block_images=False)
        self.browser = self.cm.__enter__()
        self.page = self.browser.new_page(viewport=VIEWPORT)
        try:
            self.page.set_viewport_size(VIEWPORT)
        except Exception:
            pass
        self.page.set_default_timeout(30000)
        self.name = "Camoufox-Headful"
        print(f"✅ Browser {self.name} đã khởi động (viewport {VIEWPORT['width']}x{VIEWPORT['height']})")

    def real_goto(self, url):
        """Navigation THẬT -> chỉ dùng lúc mở/reset, có节流 ở main."""
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(WAIT_AFTER_GOTO_MS)

    def fetch_html(self, url):
        """Lấy HTML mới BÊN TRONG trang (KHÔNG navigation). Trả str hoặc None."""
        try:
            res = self.page.evaluate(JS_FETCH, url)
        except Exception as e:
            if _is_really_dead(e):
                raise
            return None
        if isinstance(res, str) and res.startswith(FETCH_ERR_MARK):
            return None
        return res

    def peek_html(self):
        try:
            return self.page.content()
        except Exception as e:
            if _is_really_dead(e):
                raise
            return ""

    def click_turnstile(self):
        """🆕 BẤM widget Turnstile 1 lần bằng mouse thật (humanize jitter)."""
        sels = [
            'iframe[src*="challenges.cloudflare.com"]',
            'iframe[title*="Cloudflare"]',
            '#cf-turnstile iframe',
            'div[id*="turnstile"] iframe',
            'iframe[name*="turnstile"]',
        ]
        for sel in sels:
            try:
                el = self.page.query_selector(sel)
                if el:
                    box = el.bounding_box()
                    if box and box['width'] > 0:
                        cx = box['x'] + box['width'] / 2
                        cy = box['y'] + box['height'] / 2
                        self.page.mouse.move(cx, cy)
                        self.page.wait_for_timeout(300)
                        self.page.mouse.click(cx, cy)
                        print(f"🖱️ Đã click widget Turnstile ({sel})")
                        self.page.wait_for_timeout(6000)
                        return True
            except Exception as e:
                if _is_really_dead(e):
                    raise
                continue
        # fallback: click element chứa text verify/checkbox
        try:
            for kw in ('Verify you are human', 'verify', 'checkbox'):
                loc = self.page.get_by_text(kw, exact=False).first
                if loc and loc.is_visible():
                    loc.click(timeout=3000)
                    print(f"🖱️ Đã click text fallback '{kw}'")
                    self.page.wait_for_timeout(6000)
                    return True
        except Exception:
            pass
        print("ℹ️ Không thấy widget Turnstile để click (có thể non-interactive, chờ tự nhả)")
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
            return not _is_really_dead(e)

    def close(self):
        try: self.cm.__exit__(None, None, None)
        except Exception: pass

def open_browser_real_goto():
    """Mở browser + 1 lần goto THẬT (tính vào节流). Trả (browser, ok)."""
    try:
        b = PatientBrowser()
        b.real_goto(TARGET_URL)
        return b, True
    except Exception as e:
        print(f"❌ Mở browser lỗi: {e}")
        return None, False

# =====================================================================
# ĐỌC DATA: ưu tiên parse từ fetch HTML; thiếu -> fallback DOM click
# =====================================================================
def read_via_fetch_or_dom(browser, html_from_fetch):
    # 1) parse thẳng <option> từ HTML fetch (server-render)
    if html_from_fetch:
        parsed = parse_regions_from_text(html_from_fetch)
        if regions_complete(parsed):
            return parsed, 'FETCH'
    # 2) fallback: thao tác DOM (click dropdown + đọc option)
    click_res = browser.click_dropdown()
    if not click_res or not click_res.get('found'):
        return None, 'no-dropdown'
    browser.page.wait_for_timeout(2000)
    options = browser.read_options()
    if options and len(options) > 10:
        parsed = parse_regions_from_text(options)
        if regions_complete(parsed):
            return parsed, 'DOM'
        return None, 'incomplete'
    return None, 'no-options'

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
    if not WEBHOOK_URL:
        print(f"🚨 (khong webhook) {content[:90]}")
        return
    try:
        requests.post(WEBHOOK_URL, json={"content": content})
        print(f"🚨 Alert: {content[:80]}")
    except Exception as e:
        print(f"⚠️ Alert lỗi (webhook/secret?): {e}")

def check_and_ping(regions, prev_state):
    if not ROLE_PING_ID or not WEBHOOK_URL: return
    new_stock = [REGIONS[c]['name'] for c, v in regions.items() if v and not prev_state.get(c, False)]
    if new_stock:
        try:
            r = requests.post(f"{WEBHOOK_URL}?wait=true",
                              json={"content": f"<@&{ROLE_PING_ID}> 🟢 Server **{', '.join(new_stock)}** vừa có máy!"})
            if r.status_code == 200:
                pid = r.json().get("id")
                if pid: delete_message_after(pid, PING_AUTO_DELETE)
        except Exception: pass

# =====================================================================
# MAIN LOOP — GREEN dùng fetch (không navigation); CF click 1 lần; goto节流
# =====================================================================
def main():
    print(f"🏁 v4.3 — GREEN=fetch(KHÔNG reload) | CF=click widget 1 lần | goto节流 max {MAX_REAL_GOTO}")
    print(f"   Target: {TARGET_URL}")

    ensure_dirs()
    msg_id, prev_state = load_state()
    last_regions = prev_state if prev_state else {c: False for c in REGIONS}

    browser, ok = open_browser_real_goto()
    if not browser:
        print("❌ Không mở được browser lần đầu. Kết thúc job êm (relay sau thử).")
        return
    real_goto_used = 1   # đã dùng 1 lần goto mở

    # phân loại sau khi mở
    try:
        init_peek = browser.peek_html()
    except Exception as e:
        if _is_really_dead(e):
            print("💀 Browser chết ngay lúc mở. Kết thúc job êm."); return
        init_peek = ""
    mode = classify(init_peek)
    cf_min = 1 if mode == 'CF' else 0
    srv_min = 1 if mode == 'SRV' else 0
    unk_min = 1 if mode == 'UNK' else 0
    cf_clicked = False
    fetch_err = 0
    if mode == 'CF':
        # vừa mở đã kẹt -> click widget ngay
        browser.click_turnstile()
        cf_clicked = True
        try:
            mode = classify(browser.peek_html())
        except Exception:
            pass
    if mode == 'SRV':
        browser.screenshot_debug()
        send_alert("🟠 Mở job đã thấy server Hanami 520/5xx -> CHỜ thụ động (không đổi runner).")
    print(f"🧭 Mode khởi đầu: {mode} (goto đã dùng {real_goto_used}/{MAX_REAL_GOTO})")

    cf_restart_used = 0
    fail_streak = 0
    reopen_count = 0
    last_minute_key = None
    start_time = time.time()
    exit_reason = None

    try:
        while (time.time() - start_time) / 60 < DURATION_MINUTES:
            vn_now = datetime.now(tz_vn)
            minute_key = (vn_now.day, vn_now.hour, vn_now.minute)
            if minute_key == last_minute_key:
                time.sleep(0.5)
                continue
            last_minute_key = minute_key
            hhmm = vn_now.strftime('%H:%M')

            regions = None
            via = "NONE"
            soft = False

            try:
                if mode == 'GREEN':
                    # ===== 🆕 KHÔNG goto. fetch HTML mới bên trong trang =====
                    html = browser.fetch_html(TARGET_URL)
                    if html is None:
                        fetch_err += 1
                        print(f"⚠️ [{hhmm}] fetch lỗi (lần {fetch_err}/{MAX_FETCH_ERR}) -> giữ browser, phút sau thử lại.")
                        soft = True
                        if fetch_err >= MAX_FETCH_ERR:
                            # page state có vẻ hỏng -> 1 lần goto reset (节流)
                            if real_goto_used >= MAX_REAL_GOTO:
                                exit_reason = 'goto-cap'
                                print(f"🛑 [{hhmm}] fetch lỗi liên tiếp và đã hết suất goto -> dừng êm nhường job sau.")
                                send_alert("🛑 fetch lỗi kéo dài + hết suất navigation, nhường job sau (runner mới).")
                                break
                            real_goto_used += 1
                            print(f"🔄 [{hhmm}] fetch lỗi {fetch_err} lần -> goto reset lần {real_goto_used}/{MAX_REAL_GOTO}")
                            browser.real_goto(TARGET_URL)
                            fetch_err = 0
                            try:
                                mode = classify(browser.peek_html())
                            except Exception:
                                mode = 'UNK'
                            cf_min = 1 if mode == 'CF' else 0
                            srv_min = 1 if mode == 'SRV' else 0
                            unk_min = 1 if mode == 'UNK' else 0
                            cf_clicked = False
                            if mode == 'CF':
                                browser.click_turnstile(); cf_clicked = True
                    else:
                        fetch_err = 0
                        nm = classify(html)
                        if nm == 'GREEN':
                            regions, via = read_via_fetch_or_dom(browser, html)
                            if regions is None:
                                soft = True
                                browser.screenshot_debug()
                                print(f"⚠️ [{hhmm}] GREEN nhưng đọc data fail ({via}) -> giữ browser, fetch lại phút sau.")
                        elif nm == 'SRV':
                            mode, srv_min, cf_min, unk_min, cf_clicked = 'SRV', 1, 0, 0, False
                            browser.screenshot_debug()
                            send_alert(f"🟠 [{hhmm}] Server Hanami 520/5xx -> CHỜ thụ động (không reload/đổi runner).")
                            soft = True
                        elif nm == 'CF':
                            mode, cf_min, srv_min, unk_min, cf_clicked = 'CF', 1, 0, 0, False
                            browser.screenshot_debug()
                            print(f"🟡 [{hhmm}] fetch trả về trang verify -> click widget 1 lần rồi chờ.")
                            browser.click_turnstile(); cf_clicked = True
                            soft = True
                        else:  # UNK
                            mode, unk_min, srv_min, cf_min, cf_clicked = 'UNK', 1, 0, 0, False
                            print(f"❓ [{hhmm}] fetch trả trang không rõ mặt -> chờ, quá {UNK_GIVEUP_MIN}p dừng êm.")
                            soft = True

                else:
                    # ===== CHƯA xanh: KHÔNG navigation, chỉ peek (+ click CF 1 lần) =====
                    peek = browser.peek_html()
                    nm = classify(peek)

                    if nm == 'GREEN':
                        print(f"✅ [{hhmm}] Hồi phục về GREEN (mode cũ={mode}) -> fetch+đọc data.")
                        mode = 'GREEN'
                        cf_min = srv_min = unk_min = 0
                        cf_clicked = False
                        fetch_err = 0
                        html = browser.fetch_html(TARGET_URL)
                        if html:
                            regions, via = read_via_fetch_or_dom(browser, html)
                            if regions is None:
                                soft = True
                                browser.screenshot_debug()
                        else:
                            soft = True

                    elif nm == 'SRV':
                        mode, srv_min, cf_min, unk_min = 'SRV', srv_min + 1, 0, 0
                        if srv_min == 1:
                            browser.screenshot_debug()
                        print(f"🟠 [{hhmm}] Server Hanami 520/5xx (phút thứ {srv_min}) -> chờ thụ động, KHÔNG reload/đổi runner.")
                        soft = True

                    elif nm == 'CF':
                        mode, cf_min, srv_min, unk_min = 'CF', cf_min + 1, 0, 0
                        if cf_min == 1:
                            browser.screenshot_debug()
                        # click widget 1 LẦN duy nhất khi mới vào CF
                        if not cf_clicked:
                            browser.click_turnstile()
                            cf_clicked = True
                        if cf_min >= CF_STUCK_RESTART_MIN:
                            if cf_restart_used >= MAX_CF_RESTART or real_goto_used >= MAX_REAL_GOTO:
                                exit_reason = 'cf'
                                print(f"🛑 [{hhmm}] Kẹt CF {cf_min}p (ctx {cf_restart_used}/{MAX_CF_RESTART}, goto {real_goto_used}/{MAX_REAL_GOTO}) -> dừng êm nhường job sau.")
                                send_alert(f"🛑 Kẹt Cloudflare dù đã click widget, nhường job sau lấy runner/IP mới.")
                                break
                            cf_restart_used += 1
                            real_goto_used += 1
                            print(f"🔄 [{hhmm}] Kẹt CF {cf_min}p (đã click vẫn chưa nhả) -> goto reset context lần {cf_restart_used}/{MAX_CF_RESTART} (goto {real_goto_used}/{MAX_REAL_GOTO}, cooldown {CF_RESTART_COOLDOWN_S}s)")
                            send_alert(f"🔄 Kẹt Cloudflare {cf_min}p dù đã click widget, mở context mới lần {cf_restart_used}.")
                            try: browser.close()
                            except Exception: pass
                            time.sleep(CF_RESTART_COOLDOWN_S)
                            browser, ok = open_browser_real_goto()
                            if not browser:
                                exit_reason = 'open-fail'
                                print("❌ Mở context mới thất bại -> dừng êm."); break
                            try: pk = browser.peek_html()
                            except Exception: pk = ""
                            mode = classify(pk)
                            cf_min = 1 if mode == 'CF' else 0
                            srv_min = 1 if mode == 'SRV' else 0
                            unk_min = 1 if mode == 'UNK' else 0
                            cf_clicked = False
                            if mode == 'CF':
                                browser.click_turnstile(); cf_clicked = True
                            soft = True
                        else:
                            print(f"⏳ [{hhmm}] Kẹt CF {cf_min}/{CF_STUCK_RESTART_MIN}p (đã click widget, chờ tự nhả) -> KHÔNG reload.")
                            soft = True

                    else:  # UNK
                        mode, unk_min, srv_min, cf_min = 'UNK', unk_min + 1, 0, 0
                        if unk_min >= UNK_GIVEUP_MIN:
                            exit_reason = 'unk'
                            print(f"🛑 [{hhmm}] Trang không rõ mặt {unk_min}p -> không biết nó là gì, dừng êm nhường job sau reset ngữ cảnh.")
                            send_alert(f"🛑 Gặp trang không nhận diện được {unk_min} phút, nhường job sau (runner mới).")
                            break
                        print(f"❓ [{hhmm}] Trang không rõ mặt {unk_min}/{UNK_GIVEUP_MIN}p -> chờ thụ động, không mở ctx (tránh đoán mò).")
                        soft = True

            except Exception as e:
                if _is_really_dead(e):
                    print(f"💀 [{hhmm}] Browser chết thật: {str(e)[:80]}...")
                    try: browser.close()
                    except Exception: pass
                    reopen_count += 1
                    if reopen_count > MAX_BROWSER_REOPEN or real_goto_used >= MAX_REAL_GOTO:
                        exit_reason = 'dead'
                        print(f"🛑 Chết thật {reopen_count} lần / hết suất goto -> dừng êm."); break
                    real_goto_used += 1
                    time.sleep(REOPEN_COOLDOWN_S)
                    browser, ok = open_browser_real_goto()
                    if not browser:
                        exit_reason = 'open-fail'; break
                    try: pk = browser.peek_html()
                    except Exception: pk = ""
                    mode = classify(pk)
                    cf_min = 1 if mode == 'CF' else 0
                    srv_min = 1 if mode == 'SRV' else 0
                    unk_min = 1 if mode == 'UNK' else 0
                    cf_clicked = False
                    fetch_err = 0
                    if mode == 'CF':
                        browser.click_turnstile(); cf_clicked = True
                    soft = True
                else:
                    print(f"⚠️ [{hhmm}] Lỗi mềm: {e} -> chụp debug, giữ browser/mode.")
                    try: browser.screenshot_debug()
                    except Exception: pass
                    soft = True

            # ===== KẾT QUẢ =====
            if regions is not None:
                check_and_ping(regions, prev_state)
                prev_state = regions
                last_regions = regions
                fail_streak = 0
                ket_qua = ", ".join(f"{c}: {bool(regions.get(c))}" for c in ['SG','HK','JP','DE','US'])
                print(f"✅ Check [{hhmm}] ({via}): {ket_qua}")
            else:
                fail_streak += 1
                print(f"❌ Fail lần {fail_streak} [{hhmm}] (mode={mode})")
                if fail_streak == FAIL_ALERT_THRESHOLD or (fail_streak > FAIL_ALERT_THRESHOLD and fail_streak % 30 == 0):
                    extra = ""
                    if mode == 'SRV':
                        extra = f" | Server Hanami nghỉ (520) phút thứ {srv_min}, bot chờ đúng bài."
                    elif mode == 'CF':
                        extra = f" | Kẹt Cloudflare phút thứ {cf_min} (đã click widget)."
                    elif mode == 'UNK':
                        extra = f" | Trang không rõ mặt phút thứ {unk_min}."
                    send_alert(f"⚠️ Bot không đọc được stock {fail_streak} phút liên tiếp (mode={mode}).{extra} Ảnh: data/debug/last_error.png")

            msg_id = push_embed(last_regions, msg_id)
            save_state(msg_id, last_regions)
            print(f"🕐 Footer: {vn_now.strftime('%H:%M:%S')} (mode={mode} | chết:{reopen_count} | cf-ctx:{cf_restart_used} | goto:{real_goto_used}/{MAX_REAL_GOTO} | fetch-err:{fetch_err})")

            if exit_reason:
                break
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("🛑 Dừng bot.")
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        print(f"⏰ Kết thúc job. reason={exit_reason or 'hết 345p'} (chết:{reopen_count} cf-ctx:{cf_restart_used} goto:{real_goto_used})")

if __name__ == "__main__":
    main()
