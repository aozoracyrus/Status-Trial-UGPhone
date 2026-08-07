import os
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

# =====================================================================
# CẤU HÌNH THỜI GIAN AN TOÀN
# =====================================================================
URL = "https://hanaminikata.com/status_trial_ugphone"
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
ROLE_PING_ID = os.environ.get('ROLE_PING_ID')

# CHẠY 345 PHÚT (5 tiếng 45 phút). 
# Chừa lại 15 phút cho việc cài đặt, commit và trigger job sau.
# Nếu GitHub ngắt ở phút 350, dữ liệu đã được commit ở phút 345 nên vẫn an toàn.
DURATION_MINUTES = 345 
CHECK_INTERVAL = 60    # Check mỗi 1 phút

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
    utc_now = datetime.now(timezone.utc)
    vn_now = utc_now + timedelta(hours=7)
    return vn_now.strftime("%H:%M ngày %d/%m/%Y")

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

# =====================================================================
# PHẦN CÀO DỮ LIỆU
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
# PHẦN DISCORD (EDIT EMBED + PING)
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

def send_discord_embed(regions, msg_id=None):
    if not WEBHOOK_URL: return None

    vn_time = get_vn_time_str()
    any_in_stock = any(regions.values())
    color = 0x57f287 if any_in_stock else 0xed4245
    
    fields = []
    for code, info in REGIONS.items():
        status = "🟢 Còn máy" if regions.get(code) else "🔴 Hết máy"
        fields.append({
            "name": f"{info['flag']} {info['name']}",
            "value": status,
            "inline": True
        })

    embed = {
        "title": "📱 Trạng thái UGPhone Trial",
        "color": color,
        "fields": fields,
        "footer": {"text": f"Uptime: {vn_time} • Relay Mode"}
    }
    payload = {"embeds": [embed]}

    # 1. Thử EDIT message cũ
    if msg_id:
        try:
            url = f"{WEBHOOK_URL}/messages/{msg_id}"
            res = requests.patch(url, json=payload)
            if res.status_code == 200:
                return msg_id
        except: pass

    # 2. Gửi message MỚI nếu edit thất bại
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
# MAIN LOOP
# =====================================================================
def main():
    print(f"🏁 Bắt đầu chạy relay {DURATION_MINUTES} phút...")
    start_time = time.time()
    
    # Load state cũ
    msg_id, prev_state = load_state()
    print(f"📂 Message ID hiện tại: {msg_id}")

    while True:
        elapsed_min = (time.time() - start_time) / 60
        
        # Dừng ở phút 345 để kịp commit
        if elapsed_min >= DURATION_MINUTES:
            print("⏰ Đã chạy đủ 345 phút. Dừng để bàn giao...")
            break

        print(f"🔄 Check lần {int(elapsed_min) + 1}...")
        
        html = scrape()
        if html:
            regions = parse_html(html)
            check_and_ping(regions, prev_state)
            msg_id = send_discord_embed(regions, msg_id)
            prev_state = regions
            save_state(msg_id, regions) # Lưu ngay vào file local
        else:
            print("❌ Scrape lỗi, đợi 1 phút...")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
