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

# OWNER_ID đọc từ env, KHÔNG in ra log (repo public -> ai mở log cũng thấy)
OWNER_ID = os.environ.get('OWNER_ID', '1160199218313564210')
OWNER_PING_DELETE_S = 300          # xóa tin ping chủ sau 5 phút
OWNER_PING_RESEND_MIN = 30         # lỗi chưa fix sau 30 phút -> nhắc lại
OWNER_PING_FAIL_THRESHOLD = 2      # lỗi dai dẳng >= bao nhiêu phút mới réo chủ

DURATION_MINUTES = 345
PING_AUTO_DELETE = 300
WAIT_AFTER_GOTO_MS = 12000
WAIT_UI_TIMEOUT_MS = 15000
UI_MARKER_TEXT = "Tạo máy UGPhone"

FETCH_ERR_MARK = '__FETCH_ERR__'
MAX_FETCH_ERR = 3

CF_STUCK_RESTART_MIN = 4
CF_GRACE_MIN = 2          # 🆕 v4.8: CF thoáng qua <= grace -> giữ embed xanh, chưa tính fail
MAX_CF_RESTART = 3
CF_RESTART_COOLDOWN_S = 30
MAX_REAL_GOTO = 6
UNK_GIVEUP_MIN = 8

MAX_BROWSER_REOPEN = 3
REOPEN_COOLDOWN_S = 60

DATA_DIR = "data"
DEBUG_DIR = os.path.join(DATA_DIR, "debug")
MSG_ID_FILE = os.path.join(DATA_DIR, "message_id.txt")
PREV_STATE_FILE = os.path.join(DATA_DIR, "prev_state.json")
DEBUG_SHOT = os.path.join(DEBUG_DIR, "last_error.png")

REGIONS = {
    'SG': {'name': 'Singapore', 'flag': '🇸🇬'},
    'HK': {'name': 'Hong Kong', 'flag': '🇭🇰'},
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
# PHÂN LOẠI (CHỈ chạy trên DOM live / peek; KHÔNG gọi trên fetch-shell)
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
# 🆕 v4.7: tách "tóm tắt lỗi" và "lí do" cho embed 3 dòng
# =====================================================================
def error_summary_reason(mode, via):
    if mode == 'SRV':
        return ("Không cập nhật được trạng thái máy",
                "Máy chủ Hanami đang nghỉ (lỗi 520/5xx). Đây KHÔNG phải lỗi bot — "
                "bot sẽ tự tiếp tục khi server sống lại.")
    if mode == 'CF':
        return ("Không cập nhật được trạng thái máy",
                "Cloudflare đang yêu cầu xác minh con người và chưa nhả, "
                "dù bot đã thử click widget xác minh.")
    if mode == 'UNK':
        return ("Không cập nhật được trạng thái máy",
                "Trang trả về nội dung lạ, bot chưa nhận diện được "
                "(KHÔNG phải tường đăng nhập).")
    if via == 'no-dropdown':
        return ("Không đọc được danh sách khu vực",
                "Trang vẫn mở nhưng bot không tìm thấy ô chọn khu vực để đọc.")
    if via == 'incomplete':
        return ("Thiếu dữ liệu một vài khu vực",
                "Bot đọc được ô chọn nhưng thiếu chấm màu của một/vài khu vực.")
    if via == 'no-options':
        return ("Không đọc được danh sách khu vực",
                "Bot mở được ô chọn nhưng không đọc được nội dung bên trong.")
    return ("Không lấy được dữ liệu",
            f"Bot chưa xác định được nguyên nhân (mode={mode}, via={via}).")

# =====================================================================
# PARSE CHẤM MÀU
# =====================================================================
def _stock_of_text(t):
    low = t.lower()
    if 'có máy' in low or 'đang còn máy' in low: return True
    if 'hết máy' in low: return False
    if '🟢' in t: return True
    if any(k in t for k in ['🔴', '', '🟠', '⚪']): return False
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
        # NOTE: LeakWarning "Canvas and WebGL readback return random data" là CẢNH BÁO vô hại,
        #       không chặn khởi động (bot vẫn xanh). Camoufox mặc định bật canvas_noise để
        #       chống fingerprint-link; tắt nó (canvas_noise=False) là trade-off KHÔNG chắc
        #       thắng và VI PHẠM đóng băng khi bot đang xanh -> GIỮ NGUYÊN, chỉ ghi chú.
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
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(WAIT_AFTER_GOTO_MS)

    def fetch_html(self, url):
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
    try:
        b = PatientBrowser()
        b.real_goto(TARGET_URL)
        return b, True
    except Exception as e:
        print(f"❌ Mở browser lỗi: {e}")
        return None, False

def read_via_fetch_or_dom(browser, html_from_fetch):
    if html_from_fetch:
        parsed = parse_regions_from_text(html_from_fetch)
        if regions_complete(parsed):
            return parsed, 'FETCH'
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
#   v4.8: Discord CHỈ nhận 3 loại:
#     (1) EMBED  — edit cùng 1 msg_id; xanh = 5 khu vực; lỗi = 🚨/🤔/🛠️ (3 dòng)
#     (2) OWNER PING — chỉ khi lỗi dai dẳng VƯỢT grace; post rồi TỰ XÓA 5p; nhắc lại 30p
#     (3) ROLE PING — khi có máy mới (core, giữ); tự xóa 5p
#   🆕 v4.8 GRACE: CF thoáng qua <= CF_GRACE_MIN -> KHÔNG fail, GIỮ embed xanh, KHÔNG réo.
#   MỌI sự cố nội bộ (mở context / fetch lỗi / 520 / UNK / fail streak) -> CHỈ print log.
#   KHÔNG send_alert, KHÔNG post kênh. (cắt từ v4.6)
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

def build_embed_error(summary, reason, fail_streak):
    desc = (f"🚨 **Đang gặp lỗi:** {summary}\n"
            f"🤔 **Lí do:** {reason}\n"
            f"🛠️ Chúng tôi sẽ tìm ra nguyên nhân và cố gắng sửa chữa lỗi đang gặp phải.")
    return {
        "title": "📱 Trạng thái UGPhone Trial",
        "color": 0xed4245,
        "description": desc,
        "footer": {"text": f"Uptime: {get_time_24h()} | Fail liên tiếp: {fail_streak}p"},
    }

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

def push_embed_error(summary, reason, fail_streak, msg_id=None):
    if not WEBHOOK_URL: return None
    payload = {"embeds": [build_embed_error(summary, reason, fail_streak)]}
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

def send_owner_ping():
    content = (f"<@{OWNER_ID}> ⚠️ Bot đang bị lỗi rồi kìa, mau mau fix lỗi nhanh "
               f"để cho các ae biết server máy nào còn ‼️")
    if not WEBHOOK_URL:
        # 🆕 v4.8: KHÔNG in content (chứa <@OWNER_ID> -> lộ ID trên log public). Chỉ marker.
        print("📣 (khong webhook) OWNER PING skipped")
        return None
    try:
        r = requests.post(f"{WEBHOOK_URL}?wait=true", json={"content": content})
        if r.status_code == 200:
            pid = r.json().get("id")
            if pid:
                # pid = message id (không phải user id) -> in harmless
                print(f"📣 Đã ping chủ (msg={pid}), tự xóa sau {OWNER_PING_DELETE_S}s")
                delete_message_after(pid, OWNER_PING_DELETE_S)
                return pid
    except Exception as e:
        print(f"⚠️ Ping chủ lỗi: {e}")
    return None

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
# MAIN LOOP
# =====================================================================
def main():
    # 🆕 v4.8: header SẠCH — không in target URL thừa, không in Owner ID, không mô tả nội bộ
    print("🏁 v4.8 starting")

    ensure_dirs()
    msg_id, prev_state = load_state()
    last_regions = prev_state if prev_state else {c: False for c in REGIONS}

    browser, ok = open_browser_real_goto()
    if not browser:
        print("❌ Không mở được browser lần đầu. Kết thúc job êm (relay sau thử).")
        return
    real_goto_used = 1

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
        browser.click_turnstile(); cf_clicked = True
        try: mode = classify(browser.peek_html())
        except Exception: pass
    if mode == 'SRV':
        browser.screenshot_debug()
        print("🟠 Mở job đã thấy server Hanami 520/5xx -> CHỜ thụ động (log thôi).")
    print(f"🧭 Mode khởi đầu: {mode} (goto đã dùng {real_goto_used}/{MAX_REAL_GOTO})")

    cf_restart_used = 0
    fail_streak = 0
    reopen_count = 0
    last_owner_ping_ts = None
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
            summary = None
            reason = None

            try:
                if mode == 'GREEN':
                    html = browser.fetch_html(TARGET_URL)
                    if html is None:
                        fetch_err += 1
                        print(f"⚠️ [{hhmm}] fetch lỗi (lần {fetch_err}/{MAX_FETCH_ERR}) -> giữ browser, phút sau thử lại.")
                        soft = True
                        if fetch_err >= MAX_FETCH_ERR:
                            if real_goto_used >= MAX_REAL_GOTO:
                                exit_reason = 'goto-cap'
                                print(f"🛑 [{hhmm}] fetch lỗi liên tiếp + hết suất goto -> dừng êm nhường job sau.")
                                break
                            real_goto_used += 1
                            print(f"🔄 [{hhmm}] fetch lỗi {fetch_err} lần -> goto reset lần {real_goto_used}/{MAX_REAL_GOTO}")
                            browser.real_goto(TARGET_URL)
                            fetch_err = 0
                            try: mode = classify(browser.peek_html())
                            except Exception: mode = 'UNK'
                            cf_min = 1 if mode == 'CF' else 0
                            srv_min = 1 if mode == 'SRV' else 0
                            unk_min = 1 if mode == 'UNK' else 0
                            cf_clicked = False
                            if mode == 'CF':
                                browser.click_turnstile(); cf_clicked = True
                    else:
                        fetch_err = 0
                        parsed_direct = parse_regions_from_text(html)
                        if regions_complete(parsed_direct):
                            regions, via = parsed_direct, 'FETCH'
                        else:
                            try:
                                dom = browser.peek_html()
                            except Exception as e:
                                if _is_really_dead(e):
                                    raise
                                dom = ""
                            nm = classify(dom)
                            if nm == 'GREEN':
                                regions, via = read_via_fetch_or_dom(browser, dom)
                                if regions is None:
                                    soft = True
                                    browser.screenshot_debug()
                                    print(f"⚠️ [{hhmm}] DOM xanh nhưng đọc data fail ({via}) -> giữ browser, phút sau thử lại.")
                            elif nm == 'SRV':
                                mode, srv_min, cf_min, unk_min, cf_clicked = 'SRV', 1, 0, 0, False
                                browser.screenshot_debug()
                                print(f"🟠 [{hhmm}] Server Hanami 520/5xx (DOM live) -> CHỜ thụ động.")
                                soft = True
                            elif nm == 'CF':
                                mode, cf_min, srv_min, unk_min, cf_clicked = 'CF', 1, 0, 0, False
                                browser.screenshot_debug()
                                print(f"🟡 [{hhmm}] DOM live = trang verify THẬT -> click widget 1 lần rồi chờ.")
                                browser.click_turnstile(); cf_clicked = True
                                soft = True
                            else:
                                mode, unk_min, srv_min, cf_min, cf_clicked = 'UNK', 1, 0, 0, False
                                print(f"❓ [{hhmm}] DOM live không rõ mặt -> chờ, quá {UNK_GIVEUP_MIN}p dừng êm.")
                                soft = True
                else:
                    peek = browser.peek_html()
                    nm = classify(peek)
                    if nm == 'GREEN':
                        print(f"✅ [{hhmm}] Hồi phục về GREEN (mode cũ={mode}) -> đọc data từ DOM live.")
                        mode = 'GREEN'; cf_min = srv_min = unk_min = 0; cf_clicked = False; fetch_err = 0
                        regions, via = read_via_fetch_or_dom(browser, peek)
                        if regions is None:
                            soft = True; browser.screenshot_debug()
                    elif nm == 'SRV':
                        mode, srv_min, cf_min, unk_min = 'SRV', srv_min + 1, 0, 0
                        if srv_min == 1: browser.screenshot_debug()
                        print(f"🟠 [{hhmm}] Server Hanami 520/5xx (phút thứ {srv_min}) -> chờ thụ động, KHÔNG reload/đổi runner.")
                        soft = True
                    elif nm == 'CF':
                        mode, cf_min, srv_min, unk_min = 'CF', cf_min + 1, 0, 0
                        if cf_min == 1: browser.screenshot_debug()
                        if not cf_clicked:
                            browser.click_turnstile(); cf_clicked = True
                        if cf_min >= CF_STUCK_RESTART_MIN:
                            if cf_restart_used >= MAX_CF_RESTART or real_goto_used >= MAX_REAL_GOTO:
                                exit_reason = 'cf'
                                print(f"🛑 [{hhmm}] Kẹt CF {cf_min}p (ctx {cf_restart_used}/{MAX_CF_RESTART}, goto {real_goto_used}/{MAX_REAL_GOTO}) -> dừng êm nhường job sau.")
                                break
                            cf_restart_used += 1; real_goto_used += 1
                            print(f"🔄 [{hhmm}] Kẹt CF {cf_min}p (đã click vẫn chưa nhả) -> goto reset context lần {cf_restart_used}/{MAX_CF_RESTART} (goto {real_goto_used}/{MAX_REAL_GOTO}, cooldown {CF_RESTART_COOLDOWN_S}s)")
                            try: browser.close()
                            except Exception: pass
                            time.sleep(CF_RESTART_COOLDOWN_S)
                            browser, ok = open_browser_real_goto()
                            if not browser:
                                exit_reason = 'open-fail'; print("❌ Mở context mới thất bại -> dừng êm."); break
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
                    else:
                        mode, unk_min, srv_min, cf_min = 'UNK', unk_min + 1, 0, 0
                        if unk_min >= UNK_GIVEUP_MIN:
                            exit_reason = 'unk'
                            print(f"🛑 [{hhmm}] Trang không rõ mặt {unk_min}p -> dừng êm nhường job sau reset ngữ cảnh.")
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
                        exit_reason = 'dead'; print(f"🛑 Chết thật {reopen_count} lần / hết suất goto -> dừng êm."); break
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
                    cf_clicked = False; fetch_err = 0
                    if mode == 'CF':
                        browser.click_turnstile(); cf_clicked = True
                    soft = True
                else:
                    print(f"⚠️ [{hhmm}] Lỗi mềm: {e} -> chụp debug, giữ browser/mode.")
                    try: browser.screenshot_debug()
                    except Exception: pass
                    soft = True

            # ===== KẾT QUẢ: EMBED (xanh / lỗi 3 dòng) + GRACE + OWNER PING =====
            if regions is not None:
                check_and_ping(regions, prev_state)
                prev_state = regions
                last_regions = regions
                fail_streak = 0
                last_owner_ping_ts = None
                ket_qua = ", ".join(f"{c}: {bool(regions.get(c))}" for c in ['SG','HK','JP','DE','US'])
                print(f"✅ Check [{hhmm}] ({via}): {ket_qua}")
                msg_id = push_embed(last_regions, msg_id)
            elif mode == 'CF' and cf_min <= CF_GRACE_MIN:
                # 🆕 v4.8 GRACE: CF thoáng qua trong grace -> KHÔNG tính fail, GIỮ embed xanh
                # (refresh uptime), KHÔNG đổi đỏ, KHÔNG réo chủ. Giết flicker đỏ-xanh.
                # Cơ chế tự cứu (reset context sau CF_STUCK_RESTART_MIN) nằm trong luồng phía
                # trên, KHÔNG bị grace vô hiệu hóa -> kẹt thật vẫn được cứu như cũ.
                print(f"⏳ [{hhmm}] CF thoáng qua (cf_min={cf_min}<={CF_GRACE_MIN}) -> giữ embed xanh, chưa tính fail.")
                msg_id = push_embed(last_regions, msg_id)
            else:
                fail_streak += 1
                summary, reason = error_summary_reason(mode, via)
                print(f"❌ Fail lần {fail_streak} [{hhmm}] (mode={mode}) :: {summary} | {reason[:80]}")
                now_ts = time.time()
                if fail_streak >= OWNER_PING_FAIL_THRESHOLD and (
                        last_owner_ping_ts is None or (now_ts - last_owner_ping_ts) >= OWNER_PING_RESEND_MIN * 60):
                    send_owner_ping()
                    last_owner_ping_ts = now_ts
                msg_id = push_embed_error(summary, reason, fail_streak, msg_id)

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
