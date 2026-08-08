import os
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

# =====================================================================
# CẤU HÌNH
# =====================================================================
URL = "https://hanaminikata.com/status_trial_ugphone"
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
ROLE_PING_ID = os.environ.get('ROLE_PING_ID')

DURATION_MINUTES = 345   # Chạy 5h45p rồi bàn giao
CHECK_INTERVAL = 60      # Scrape đúng nhịp 1 phút
FOOTER_INTERVAL = 30     # Refresh giờ trên footer mỗi 30 giây

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

# =====================================================================
# HÀM HỖ TRỢ
# =====================================================================
def get_vn_time_str():
    """Lấy giờ Việt Nam CHUẨN theo múi giờ Asia/Ho_Chi_Minh (khớp time.is)"""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    except Exception:
        now = datetime.now(timezone.utc) + timedelta(hours=7)
    return now.strftime("%H:%M ngày %d/%m/%Y")

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

# =====================================================================
# PHẦN CÀO DỮ LIỆU (Giữ nguyên 2 chiến lược đã thành công)
# =====================================================================
def scrape():
    # Chiến lược 1: SeleniumBase UC Mode
    try:
        from seleniumbase import Driver
        driver = Driver(uc=True, headless=True)
        driver.uc_open_with_reconnect(URL, reconnect_time=7)
        driver.sleep(5)
        html = driver.page_source
        driver.quit()
        if "just a moment" not in html.lower():
            return html
    except Exception as e:
        print(f"Lỗi SeleniumBase: {e}")

    # Chiến lược 2: Camoufox
    try:
        from camoufox.sync_api import Camoufox
        with Camoufox(headless=True, block_images=True) as browser:
            page = browser.new_page()
            page.goto(URL, wait_until="domcontentloaded", timeout=45000)
            time.sleep(10)
            html = page.content()
            if "just a moment" not in html.lower():
                return html
    except Exception as e:
        print(f"Lỗi Camoufox: {e}")

    return None

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

# =====================================================================
# PHẦN DISCORD
# =====================================================================
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
        except: pass
    return msg_id, prev_state

def save_state(msg_id, regions):
    ensure_data_dir()
    with open(MSG_ID_FILE, 'w') as f:
        f.write(str(msg_id))
    with open(PREV_STATE_FILE, 'w') as f:
        json.dump(regions, f)

def build_embed(regions):
    """Dựng embed với giờ VIỆT NAM chuẩn, KHÔNG còn chữ Relay Mode"""
    any_in_stock = any(regions.get(c) for c in REGIONS)
    color = 0x57f287 if any_in_stock else 0xed4245

    fields = []
    for code, info in REGIONS.items():
        status = "🟢 Còn máy" if regions.get(code) else "🔴 Hết máy"
        fields.append({
            "name": f"{info['flag']} {info['name']}",
            "value": status,
            "inline": True
        })

    return {
        "title": "📱 Trạng thái UGPhone Trial",
        "color": color,
        "fields": fields,
        "footer": {"text": f"Uptime: {get_vn_time_str()}"}
    }

def push_embed(regions, msg_id=None):
    """Edit message cũ nếu có ID, nếu không thì gửi mới"""
    if not WEBHOOK_URL: return None
    payload = {"embeds": [build_embed(regions)]}

    # 1. Thử EDIT
    if msg_id:
        try:
            res = requests.patch(f"{WEBHOOK_URL}/messages/{msg_id}", json=payload)
            if res.status_code == 200:
                return msg_id
        except: pass

    # 2. Gửi MỚI
    try:
        res = requests.post(f"{WEBHOOK_URL}?wait=true", json=payload)
        if res.status_code == 200:
            return res.json().get("id")
    except: pass

    return msg_id

def check_and_ping(regions, prev_state):
    if not ROLE_PING_ID or not WEBHOOK_URL: return
    new_stock = []
    for code, is_now in regions.items():
        if is_now and not prev_state.get(code, False):
            new_stock.append(REGIONS[code]['name'])
    if new_stock:
        msg = f"<@&{ROLE_PING_ID}> 🎉 Server **{', '.join(new_stock)}** vừa có máy!"
        try:
            requests.post(WEBHOOK_URL, json={"content": msg})
        except: pass

# =====================================================================
# MAIN LOOP - BỘ LẬP LỊCH CHUẨN 1 PHÚT
# =====================================================================
def main():
    print(f"🏁 Bắt đầu chạy relay {DURATION_MINUTES} phút...")
    start_time = time.time()

    msg_id, prev_state = load_state()
    print(f"📂 Message ID hiện tại: {msg_id}")

    last_regions = prev_state if prev_state else {c: False for c in REGIONS}
    check_count = 0

    next_scrape = time.time()                    # Scrape ngay lập tức
    next_footer = time.time() + FOOTER_INTERVAL  # Refresh footer sau 30s

    while (time.time() - start_time) / 60 < DURATION_MINUTES:
        now = time.time()

        # ---------- 1) SCRAPE ĐÚNG NHÍP 1 PHÚT ----------
        if now >= next_scrape:
            check_count += 1
            html = scrape()
            if html:
                regions = parse_html(html)
                check_and_ping(regions, prev_state)
                prev_state = regions
                last_regions = regions
                msg_id = push_embed(regions, msg_id)
                save_state(msg_id, regions)

                # Log mới: kèm kết quả từng khu vực
                ket_qua = ", ".join(f"{c}: {bool(regions.get(c))}" for c in ['SG', 'HK', 'JP', 'DE', 'US'])
                print(f"🔄 Check lần {check_count} [{get_vn_time_str().split(' ngày')[0]}]: {ket_qua}")
            else:
                print(f"🔄 Check lần {check_count}: ❌ Lỗi scrape, thử lại phút sau")

            # Đặt mốc check tiếp theo đúng +60s (không bị trôi nhịp)
            next_scrape = max(next_scrape + CHECK_INTERVAL, time.time())

        # ---------- 2) REFRESH FOOTER MỖI 30s (không scrape lại) ----------
        if time.time() >= next_footer:
            msg_id = push_embed(last_regions, msg_id)
            next_footer = time.time() + FOOTER_INTERVAL

        time.sleep(3)

    print("⏰ Hết 345 phút. Bàn giao cho runner kế tiếp...")

if __name__ == "__main__":
    main()
