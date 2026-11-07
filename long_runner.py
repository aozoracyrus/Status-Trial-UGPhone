import os
import json
import time
import re
import requests
import threading
from datetime import datetime
import pytz
from DrissionPage import ChromiumPage, ChromiumOptions

# =====================================================================
# CẤU HÌNH
# =====================================================================
TARGET_URL = "https://hanaminikata.com/tools/buydevice_ugphone"
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
ROLE_PING_ID = os.environ.get('ROLE_PING_ID')

OWNER_ID = os.environ.get('OWNER_ID', '1160199218313564210')
OWNER_PING_FAIL_THRESHOLD = 2      # lỗi NGHIÊM TRỌNG liên tiếp >= p này mới ping
OWNER_PING_COOLDOWN_S = 600        # sau khi xóa ping, chặn post lại 10p (chống flap)

DURATION_MINUTES = 345
PING_AUTO_DELETE = 300
WAIT_AFTER_GOTO_S = 12             # giây (DrissionPage page.wait() dùng GIÂY, không phải ms)
UI_MARKER_TEXT = "Tạo máy UGPhone"

# --- v5.0: peek-only mặc định (KHÔNG goto mỗi phút) + goto thưa chống stale ---
REFRESH_EVERY_MIN = 10             # mỗi N phút goto 1 lần re-hydrate (PHỎNG ĐOÁN, verify bằng log)
MAX_REAL_GOTO = 40                 # 345/10 ~= 35 -> chừa 40

CF_STUCK_RESTART_MIN = 4
CF_GRACE_MIN = 2
MAX_CF_RESTART = 3
CF_RESTART_COOLDOWN_S = 30
UNK_GIVEUP_MIN = 8
MAX_BROWSER_REOPEN = 3
REOPEN_COOLDOWN_S = 60

READ_FAIL_VIAS = ('incomplete', 'no-options')   # v5.0 bỏ 'no-dropdown' (không còn click dropdown)

DATA_DIR = "data"
DEBUG_DIR = os.path.join(DATA_DIR, "debug")
MSG_ID_FILE = os.path.join(DATA_DIR, "message_id.txt")
PREV_STATE_FILE = os.path.join(DATA_DIR, "prev_state.json")
OWNER_PING_ID_FILE = os.path.join(DATA_DIR, "owner_ping_id.txt")
DEBUG_SHOT = os.path.join(DEBUG_DIR, "last_error.png")

# MỖI flag = 2 ký tự regional-indicator (U+1F1E6..U+1F1FF). ĐỪNG để cụt 1 ký tự.
REGIONS = {
    'SG': {'name': 'Singapore', 'flag': '🇸🇬'},  # U+1F1F8 U+1F1EC
    'HK': {'name': 'Hong Kong',  'flag': '🇭🇰'},  # U+1F1ED U+1F1F0
    'JP': {'name': 'Japan',       'flag': '🇯🇵'},  # U+1F1EF U+1F1F5
    'DE': {'name': 'Germany',     'flag': '🇩🇪'},  # U+1F1E9 U+1F1EA
    'US': {'name': 'America',     'flag': '🇺🇸'},  # U+1F1FA U+1F1F8
}

tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
def get_time_24h():
    return datetime.now(tz_vn).strftime("%H:%M ngày %d/%m/%Y")

def ensure_dirs():
    for d in (DATA_DIR, DEBUG_DIR):
        if not os.path.exists(d):
            os.makedirs(d)

# =====================================================================
# PHÂN LOẠI (CHỈ DOM live / page.html; TUYỆT ĐỐI không login/token)
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

def error_summary_reason(mode, via):
    if mode == 'SRV':
        return ("Không cập nhật được trạng thái máy",
                "Máy chủ Hanami đang nghỉ (lỗi 520/5xx). Đây KHÔNG phải lỗi bot — "
                "bot sẽ tự tiếp tục khi server sống lại.")
    if mode == 'CF':
        return ("Không cập nhật được trạng thái máy",
                "Cloudflare đang yêu cầu xác minh con người và chưa nhả.")
    if mode == 'UNK':
        return ("Không cập nhật được trạng thái máy",
                "Trang trả về nội dung lạ, bot chưa nhận diện được "
                "(KHÔNG phải tường đăng nhập).")
    if via == 'incomplete':
        return ("Thiếu dữ liệu một vài khu vực",
                "Bot đọc được ô chọn nhưng thiếu chấm màu của một/vài khu vực.")
    if via == 'no-options':
        return ("Không đọc được danh sách khu vực",
                "Bot thấy giao diện nhưng không parse ra đủ 5 khu vực.")
    return ("Không lấy được dữ liệu",
            f"Bot chưa xác định được nguyên nhân (mode={mode}, via={via}).")

# =====================================================================
# PARSE (chạy trên string page.html, KHÔNG cần JS)
#   Thứ tự ưu tiên: text VN -> 🟢 (còn) -> màu hết -> None (chưa rõ).
#   KHÔNG có chuỗi rỗng '' trong list màu (lỗi cẩu thả đã sửa).
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
# BROWSER WRAPPER (DrissionPage / Chrome-CDP) - CHỈ dùng API đã test chắc
# =====================================================================
class ChromeCDPBrowser:
    def __init__(self):
        opt = ChromiumOptions()
        # headed mặc định (KHÔNG gọi headless()) -> cần Xvfb. KHÔNG set UA/window
        # (để Chrome thật tự khai UA đúng version + Xvfb lo size) -> khớp drift_test PASS.
        opt.set_argument('--no-sandbox')             # bắt buộc trong container GitHub
        opt.set_argument('--disable-dev-shm-usage')  # /dev/shm nhỏ trên runner
        opt.set_argument('--disable-gpu')            # Xvfb không GPU thật -> software render
        self.page = ChromiumPage(opt)
        self.name = "DrissionPage-ChromeCDP"
        print(f"✅ Browser {self.name} đã khởi động (headed + CDP, Xvfb 1920x1080)")

    def real_goto(self, url):
        try:
            self.page.get(url)
            self.page.wait(WAIT_AFTER_GOTO_S)
            return True
        except Exception as e:
            print(f"❌ real_goto lỗi: {e}")
            return False

    def peek_html(self):
        """DOM live outerHTML (đã hydrate). Catch-all -> '' khi lỗi (mềm, KHÔNG raise)."""
        try:
            return self.page.html or ""
        except Exception as e:
            print(f"⚠️ peek_html lỗi (coi như mềm): {e}")
            return ""

    def parse_data(self):
        """Parse 5 region thẳng từ page.html. Trả (regions|None, via)."""
        html = self.peek_html()
        if not html:
            return None, 'no-options'
        parsed = parse_regions_from_text(html)
        if regions_complete(parsed):
            return parsed, 'DOM'
        if has_real_ui(html):
            return None, 'incomplete'   # GREEN-mù (critical)
        return None, 'no-options'

    def click_turnstile(self):
        """Best-effort. Test chứng minh CF tự nhả không cần click -> fail ở đây VÔ HẠI."""
        sels = [
            'css:iframe[src*="challenges.cloudflare.com"]',
            'css:iframe[title*="Cloudflare"]',
            'css:#cf-turnstile iframe',
            'text:Verify you are human',
        ]
        for sel in sels:
            try:
                el = self.page.ele(sel, timeout=2)
                if el:
                    el.click()
                    print(f"🖱️ Đã click widget ({sel})")
                    self.page.wait(6)
                    return True
            except Exception:
                continue
        print("ℹ️ Không click được widget (managed-auto, chờ tự nhả) -> vô hại")
        return False

    def screenshot_debug(self):
        try:
            ensure_dirs()
            self.page.get_screenshot(path=DEBUG_SHOT)
            print(f"📸 Đã chụp debug -> {DEBUG_SHOT}")
        except Exception as e:
            print(f"⚠️ Chụp debug thất bại: {e}")

    def is_really_alive(self):
        """Thử đọc title. Browser chết -> raise -> False. Trang CF verify -> title tồn tại -> True."""
        try:
            _ = self.page.title
            return True
        except Exception:
            return False

    def close(self):
        try: self.page.quit()
        except Exception: pass

def open_browser():
    try:
        b = ChromeCDPBrowser()
        if not b.real_goto(TARGET_URL):
            b.close()
            return None
        return b
    except Exception as e:
        print(f"❌ Mở browser lỗi: {e}")
        return None

# =====================================================================
# DISCORD & STATE (xóa ping ngay khi xanh + cooldown chống flap)
# =====================================================================
def load_state():
    msg_id, prev_state, owner_ping_id = None, {}, None
    if os.path.exists(MSG_ID_FILE):
        msg_id = open(MSG_ID_FILE).read().strip()
    if os.path.exists(PREV_STATE_FILE):
        try: prev_state = json.load(open(PREV_STATE_FILE))
        except Exception: pass
    if os.path.exists(OWNER_PING_ID_FILE):
        owner_ping_id = open(OWNER_PING_ID_FILE).read().strip() or None
    return msg_id, prev_state, owner_ping_id

def save_state(msg_id, regions, owner_ping_id):
    ensure_dirs()
    open(MSG_ID_FILE, 'w').write(str(msg_id))
    json.dump(regions, open(PREV_STATE_FILE, 'w'))
    if owner_ping_id:
        open(OWNER_PING_ID_FILE, 'w').write(str(owner_ping_id))
    elif os.path.exists(OWNER_PING_ID_FILE):
        os.remove(OWNER_PING_ID_FILE)

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
    return {"title": "📱 Trạng thái UGPhone Trial", "color": 0xed4245,
            "description": desc,
            "footer": {"text": f"Uptime: {get_time_24h()} | Fail liên tiếp: {fail_streak}p"}}

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

def post_owner_ping_once(state):
    if state['owner_ping_msg_id'] is not None:
        return
    now = time.time()
    lc = state.get('last_cleared_ts')
    if lc is not None and (now - lc) < OWNER_PING_COOLDOWN_S:
        print(f"⏸️ Bỏ qua ping (vừa xóa {int(now-lc)}s trước < cooldown {OWNER_PING_COOLDOWN_S}s) -> chống flap")
        return
    content = (f"<@{OWNER_ID}> ⚠️ Bot đang bị lỗi rồi kìa, mau mau fix lỗi nhanh "
               f"để cho các ae biết server máy nào còn ‼️")
    if not WEBHOOK_URL:
        print("📣 (khong webhook) OWNER PING skipped")
        return
    try:
        r = requests.post(f"{WEBHOOK_URL}?wait=true", json={"content": content})
        if r.status_code == 200:
            pid = r.json().get("id")
            if pid:
                state['owner_ping_msg_id'] = pid
                print(f"📣 Đã ping chủ (msg={pid}), GIỮ đến khi xanh")
    except Exception as e:
        print(f"⚠️ Ping chủ lỗi: {e}")

def clear_owner_ping(state):
    pid = state['owner_ping_msg_id']
    if pid is None:
        return
    if not WEBHOOK_URL:
        state['owner_ping_msg_id'] = None
        state['last_cleared_ts'] = time.time()
        return
    try:
        r = requests.delete(f"{WEBHOOK_URL}/messages/{pid}")
        if r.status_code in (200, 204):
            state['owner_ping_msg_id'] = None
            state['last_cleared_ts'] = time.time()
            print(f"🧹 Đã xóa tin ping chủ (msg={pid}) -> cooldown chống flap bắt đầu")
        else:
            print(f"⚠️ Xóa ping fail HTTP {r.status_code} -> GIỮ id để retry (không post trùng)")
    except Exception as e:
        print(f"⚠️ Xóa ping lỗi: {e} -> GIỮ id để retry (không post trùng)")

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
# MAIN LOOP - peek-only mặc định + goto thưa + máy trạng thái GREEN/SRV/CF/UNK
# =====================================================================
def main():
    print("🏁 v5.0 starting (DrissionPage Chrome-CDP, peek-only chống CF)")
    ensure_dirs()
    msg_id, prev_state, owner_ping_id = load_state()
    state = {'owner_ping_msg_id': owner_ping_id, 'last_cleared_ts': None}
    last_regions = prev_state if prev_state else {c: False for c in REGIONS}

    browser = open_browser()
    if not browser:
        print("❌ Không mở được browser lần đầu. Kết thúc job êm (relay sau thử).")
        return
    real_goto_used = 1
    mins_since_goto = 0

    mode = classify(browser.peek_html())
    cf_min = 1 if mode == 'CF' else 0
    srv_min = 1 if mode == 'SRV' else 0
    unk_min = 1 if mode == 'UNK' else 0
    cf_clicked = False
    if mode == 'CF':
        browser.click_turnstile(); cf_clicked = True
        mode = classify(browser.peek_html())
        cf_min = 1 if mode == 'CF' else 0
    if mode == 'SRV':
        browser.screenshot_debug()
        print("🟠 Mở job đã thấy server Hanami 520/5xx -> CHỜ thụ động (log thôi, không ping).")
    print(f"🧭 Mode khởi đầu: {mode} (goto đã dùng {real_goto_used}/{MAX_REAL_GOTO})")

    cf_restart_used = 0
    fail_streak = 0
    critical_fail_streak = 0
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
            mins_since_goto += 1

            # phát hiện browser chết CHỦ ĐỘNG (không đoán exception message)
            if not browser.is_really_alive():
                print(f"💀 [{hhmm}] Browser chết (title fail) -> reopen...")
                try: browser.close()
                except Exception: pass
                reopen_count += 1
                if reopen_count > MAX_BROWSER_REOPEN:
                    exit_reason = 'dead'
                    print(f"🛑 Reopen {reopen_count} lần (quá {MAX_BROWSER_REOPEN}) -> bó tay, ping rồi dừng êm.")
                    post_owner_ping_once(state)
                    break
                time.sleep(REOPEN_COOLDOWN_S)
                browser = open_browser()
                if not browser:
                    exit_reason = 'open-fail'
                    print("❌ Reopen thất bại -> bó tay, ping rồi dừng êm.")
                    post_owner_ping_once(state)
                    break
                real_goto_used += 1; mins_since_goto = 0
                mode = classify(browser.peek_html())
                cf_min = 1 if mode == 'CF' else 0
                srv_min = 1 if mode == 'SRV' else 0
                unk_min = 1 if mode == 'UNK' else 0
                cf_clicked = False
                if mode == 'CF':
                    browser.click_turnstile(); cf_clicked = True

            regions = None
            via = "NONE"
            summary = None
            reason = None

            try:
                if mode == 'GREEN':
                    # peek-only mặc định; goto thưa mỗi REFRESH_EVERY_MIN để re-hydrate (chống stale)
                    if mins_since_goto >= REFRESH_EVERY_MIN and real_goto_used < MAX_REAL_GOTO:
                        print(f"🔁 [{hhmm}] goto re-hydrate thưa lần {real_goto_used+1}/{MAX_REAL_GOTO} (chống stale)")
                        browser.real_goto(TARGET_URL)
                        real_goto_used += 1; mins_since_goto = 0
                    peek = browser.peek_html()
                    nm = classify(peek)
                    if nm == 'GREEN':
                        regions, via = browser.parse_data()
                        if regions is None:
                            summary, reason = error_summary_reason('GREEN', via)
                            browser.screenshot_debug()
                            print(f"⚠️ [{hhmm}] GREEN nhưng parse thiếu ({via}) -> critical, giữ browser.")
                    elif nm == 'SRV':
                        mode, srv_min, cf_min, unk_min, cf_clicked = 'SRV', 1, 0, 0, False
                        browser.screenshot_debug()
                        print(f"🟠 [{hhmm}] Server Hanami 520/5xx -> CHỜ thụ động.")
                    elif nm == 'CF':
                        mode, cf_min, srv_min, unk_min, cf_clicked = 'CF', 1, 0, 0, False
                        browser.screenshot_debug()
                        print(f"🟡 [{hhmm}] Rơi vào CF verify -> click best-effort rồi chờ tự nhả.")
                        browser.click_turnstile(); cf_clicked = True
                    else:
                        mode, unk_min, srv_min, cf_min, cf_clicked = 'UNK', 1, 0, 0, False
                        print(f"❓ [{hhmm}] peek trả trang không rõ mặt -> chờ, quá {UNK_GIVEUP_MIN}p dừng êm.")
                else:
                    peek = browser.peek_html()
                    nm = classify(peek)
                    if nm == 'GREEN':
                        print(f"✅ [{hhmm}] Hồi phục về GREEN (mode cũ={mode}) -> parse data.")
                        mode = 'GREEN'; cf_min = srv_min = unk_min = 0; cf_clicked = False; mins_since_goto = 0
                        regions, via = browser.parse_data()
                        if regions is None:
                            summary, reason = error_summary_reason('GREEN', via)
                            browser.screenshot_debug()
                    elif nm == 'SRV':
                        mode, srv_min, cf_min, unk_min = 'SRV', srv_min + 1, 0, 0
                        if srv_min == 1: browser.screenshot_debug()
                        print(f"🟠 [{hhmm}] Server Hanami 520/5xx (phút thứ {srv_min}) -> chờ thụ động, KHÔNG reload.")
                    elif nm == 'CF':
                        mode, cf_min, srv_min, unk_min = 'CF', cf_min + 1, 0, 0
                        if cf_min == 1: browser.screenshot_debug()
                        if not cf_clicked:
                            browser.click_turnstile(); cf_clicked = True
                        if cf_min >= CF_STUCK_RESTART_MIN:
                            if cf_restart_used >= MAX_CF_RESTART or real_goto_used >= MAX_REAL_GOTO:
                                exit_reason = 'cf'
                                print(f"🛑 [{hhmm}] Kẹt CF {cf_min}p (ctx {cf_restart_used}/{MAX_CF_RESTART}, goto {real_goto_used}/{MAX_REAL_GOTO}) -> bó tay, ping rồi dừng êm.")
                                post_owner_ping_once(state)
                                break
                            cf_restart_used += 1; real_goto_used += 1
                            print(f"🔄 [{hhmm}] Kẹt CF {cf_min}p -> mở context Chrome mới lần {cf_restart_used}/{MAX_CF_RESTART} (cooldown {CF_RESTART_COOLDOWN_S}s)")
                            try: browser.close()
                            except Exception: pass
                            time.sleep(CF_RESTART_COOLDOWN_S)
                            browser = open_browser()
                            if not browser:
                                exit_reason = 'open-fail'
                                print("❌ Mở context mới thất bại -> bó tay, ping rồi dừng êm.")
                                post_owner_ping_once(state)
                                break
                            mins_since_goto = 0
                            mode = classify(browser.peek_html())
                            cf_min = 1 if mode == 'CF' else 0
                            srv_min = 1 if mode == 'SRV' else 0
                            unk_min = 1 if mode == 'UNK' else 0
                            cf_clicked = False
                            if mode == 'CF':
                                browser.click_turnstile(); cf_clicked = True
                        else:
                            print(f"⏳ [{hhmm}] Kẹt CF {cf_min}/{CF_STUCK_RESTART_MIN}p (đã click, chờ tự nhả) -> KHÔNG reload.")
                    else:
                        mode, unk_min, srv_min, cf_min = 'UNK', unk_min + 1, 0, 0
                        if unk_min >= UNK_GIVEUP_MIN:
                            exit_reason = 'unk'
                            print(f"🛑 [{hhmm}] Trang không rõ mặt {unk_min}p -> bó tay, ping rồi dừng êm.")
                            post_owner_ping_once(state)
                            break
                        print(f"❓ [{hhmm}] Trang không rõ mặt {unk_min}/{UNK_GIVEUP_MIN}p -> chờ thụ động.")
            except Exception as e:
                print(f"⚠️ [{hhmm}] Lỗi mềm ngoài dự kiến: {e} -> chụp debug, giữ browser/mode.")
                try: browser.screenshot_debug()
                except Exception: pass

            # ===== KẾT QUẢ =====
            if regions is not None:
                check_and_ping(regions, prev_state)
                prev_state = regions
                last_regions = regions
                fail_streak = 0
                critical_fail_streak = 0
                ket_qua = ", ".join(f"{c}: {bool(regions.get(c))}" for c in ['SG','HK','JP','DE','US'])
                print(f"✅ Check [{hhmm}] ({via}): {ket_qua}")
                msg_id = push_embed(last_regions, msg_id)
                clear_owner_ping(state)
            else:
                if summary is None:
                    summary, reason = error_summary_reason(mode, via)
                critical_now = (mode == 'UNK') or (mode == 'GREEN' and via in READ_FAIL_VIAS)
                if critical_now:
                    fail_streak += 1
                    critical_fail_streak += 1
                    print(f"❌ Fail [{fail_streak}] [{hhmm}] (mode={mode} CRITICAL) :: {summary} | {reason[:80]}")
                    msg_id = push_embed_error(summary, reason, fail_streak, msg_id)
                    if critical_fail_streak >= OWNER_PING_FAIL_THRESHOLD:
                        post_owner_ping_once(state)
                elif mode == 'CF' and cf_min <= CF_GRACE_MIN:
                    print(f"⏳ [{hhmm}] CF thoáng qua (cf_min={cf_min}<={CF_GRACE_MIN}) -> giữ embed xanh, chưa tính fail.")
                    msg_id = push_embed(last_regions, msg_id)
                    critical_fail_streak = 0
                else:
                    fail_streak += 1
                    critical_fail_streak = 0
                    print(f"❌ Fail [{fail_streak}] [{hhmm}] (mode={mode} tự-lo, KHÔNG ping) :: {summary} | {reason[:80]}")
                    msg_id = push_embed_error(summary, reason, fail_streak, msg_id)

            save_state(msg_id, last_regions, state['owner_ping_msg_id'])
            print(f"🕐 Footer: {vn_now.strftime('%H:%M:%S')} (mode={mode} | reopen:{reopen_count} | cf-ctx:{cf_restart_used} | goto:{real_goto_used}/{MAX_REAL_GOTO} | since_goto:{mins_since_goto} | ping:{'có' if state['owner_ping_msg_id'] else 'không'})")

            if exit_reason:
                break
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("🛑 Dừng bot.")
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        print(f"⏰ Kết thúc job. reason={exit_reason or 'hết 345p'} (reopen:{reopen_count} cf-ctx:{cf_restart_used} goto:{real_goto_used})")

if __name__ == "__main__":
    main()
