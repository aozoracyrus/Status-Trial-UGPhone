<div align="center">

# 📱 STATUS TRIAL UGPHONE — DISCORD BOT

**Giám sát trạng thái máy trial UGPhone 24/7 • GitHub Actions Relay • 100% miễn phí**

*Không VPS • Không Render • Không ScraperAPI • Không tốn một xu*

**Phiên bản v4.0 — "Kiên nhẫn, không phán đoán sai".**
Trang đích là trang MUA công khai, KHÔNG cần đăng nhập. Hệ thống bảo mật duy nhất là
Cloudflare Turnstile, và nó TỰ verify khi browser headful + Xvfb render đủ lâu.
Mọi "login wall" mà bot từng gặp ở v3.x đều là **false positive do code tự bịa ra**.

</div>

---

## 📖 Mục lục

- [🌟 Giới thiệu](#-giới-thiệu)
- [⚙️ Yêu cầu](#️-yêu-cầu)
- [🔑 Thêm Secrets](#-thêm-secrets)
- [🔓 Cấp quyền cho Repo](#-cấp-quyền-cho-repo)
- [🚀 Cách hoạt động](#-cách-hoạt-động)
- [🧊 Chính sách đóng băng](#-chính-sách-đóng-băng)
- [📁 Cấu trúc dự án](#-cấu-trúc-dự-án)
- [🛠️ Lỗi thường gặp & cách sửa](#️-lỗi-thường-gặp--cách-sửa)
- [⚙️ Tùy chỉnh](#️-tùy-chỉnh)
- [❓ FAQ](#-faq)
- [⚖️ Tuyên bố miễn trừ](#️-tuyên-bố-miễn-trừ)
- [📜 Changelog](#-changelog)
- [💖 Credit](#-credit)

---

## 🌟 Giới thiệu

Bot theo dõi trạng thái máy trial UGPhone qua trang **mua hàng công khai**
(`hanaminikata.com/tools/buydevice_ugphone`) và hiển thị lên Discord.

Sự thật nền tảng của v4.0 (đã kiểm chứng bằng log thật `reopen: 0`):

- Trang này **HOÀN TOÀN KHÔNG CẦN ĐĂNG NHẬP**. Chrome thường, không login, vẫn thấy
  dropdown 5 khu vực + nút "Tạo máy UGPhone".
- Bảo mật duy nhất là **Cloudflare Turnstile**, và nó **tự pass** khi browser headful
  render đủ lâu trên Xvfb đúng độ phân giải.
- Do đó bot v4.0 **không còn** logic check "login wall", **không còn** panic restart
  loop. Hai thứ đó ở v3.x chính là nguồn gốc khiến Cloudflare khóa IP (timeout 90s).

Tính năng cốt lõi:

- 🟢 **5 khu vực**: Singapore, Hong Kong, Japan, Germany, America — đọc từ chấm màu
  trong dropdown (🟢 = còn máy, 🔴 = hết máy).
- 📊 **1 Embed duy nhất** được EDIT liên tục, không spam tin nhắn.
- 🕐 **Footer Uptime** đúng giây `:00` mỗi phút, format 24h, dùng `pytz` (Asia/Ho_Chi_Minh).
- 🔔 **Ping role** khi khu vực chuyển hết → còn máy, **tự xóa sau 5 phút**.
- 🛡️ **Headful Camoufox + Xvfb 1920x1080 + humanize**: mô phỏng Chrome thật để
  Turnstile tự verify, không chặn ảnh.
- ⏳ **Kiên nhẫn**: chờ 12s sau mỗi lần load cho Xvfb + Turnstile, đợi text
  "Tạo máy UGPhone" làm mốc UI thật, tối đa 15s.
- 📸 **Lỗi mềm = chụp debug, giữ browser**. Browser chỉ bị mở lại khi **chết thật**
  (target closed / connection refused), có cooldown 60s + giới hạn 3 lần/job.
- 🚨 **Alert Discord** nếu không đọc được stock 10 phút liên tiếp (và nhắc mỗi giờ),
  nhưng KHÔNG bao giờ vì alert mà đập browser.
- 🔄 **Relay 24/7**: mỗi job 345 phút, force push state, tự kích job kế.

---

## ⚙️ Yêu cầu

| Thành phần | Bắt buộc | Ghi chú |
|---|---|---|
| Tài khoản GitHub | ✅ | Repo **Public** = unlimited Actions minutes |
| Discord Webhook | ✅ | Kênh nhận embed + ping |
| Personal Access Token | ✅ | Quyền `repo` + `workflow` |
| Xvfb screen 1920x1080 | ✅ | **Phải khớp** `VIEWPORT` trong code, lệch là click Turnstile sai toạ độ |
| VPS / Render | ❌ | Không cần. IP datacenter không phải vấn đề (đã chứng minh) |
| Thẻ tín dụng / Token đăng nhập | ❌ | **Không cần.** Trang không yêu cầu login |

---

## 🔑 Thêm Secrets

Vào repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Secret | Mô tả | Cách lấy |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | Webhook kênh Discord | Cài đặt kênh → Tích hợp → Webhooks → Tạo |
| `ROLE_PING_ID` | ID role để ping khi có máy | Bật Developer Mode → chuột phải role → Copy ID |
| `PAT` | Token push code + trigger relay | Developer settings → Tokens (classic) → tick `repo` + `workflow` |

> `HANAMI_COOKIES` / `cookies.json` ở v3.x là **dư thừa** ở v4.0 vì trang không cần
> login. Code v4.0 vẫn đọc nếu có (harmless), nhưng anh không cần tạo nữa.

---

## 🔓 Cấp quyền cho Repo

1. **Đổi repo sang Public**: Settings → General → Danger zone → Change visibility
2. **Cấp quyền ghi cho Actions**: Settings → Actions → General → **Read and write permissions** → Save

---

## 🚀 Cách hoạt động

### Luồng đọc dữ liệu v4.0 (mỗi phút, trên CÙNG một browser)

    1. Reload NHẸ trang đích trên browser đang sống (giữ cf_clearance tích luỹ,
       KHÔNG đóng/mở browser).
    2. Chờ 12s (WAIT_AFTER_GOTO_MS) cho Xvfb render + Turnstile tự verify.
    3. Best-effort click vào iframe Turnstile nếu thấy (null-safe, không fail nếu không có).
    4. Đợi text "Tạo máy UGPhone" hiện (tối đa 15s) = mốc UI THẬT đã load.
       - Chưa hiện  -> chụp debug, giữ browser, thử lại phút sau. KHÔNG restart.
    5. Click mở dropdown khu vực -> đọc toàn bộ option/li -> parse chấm màu.
       - Thiếu region / không thấy dropdown -> chụp debug, giữ browser. KHÔNG restart.
    6. Đủ 5 khu vực -> EDIT embed Discord, so sánh prev_state để ping role.
    7. fail_streak CHỈ dùng để bắn alert sau 10 phút, KHÔNG đụng tới browser.

Browser chỉ bị mở lại khi `_is_really_dead()` trả True (target closed, connection
refused...). Khi đó: cooldown 60s cho IP nguội -> mở lại -> giới hạn 3 lần/job,
vượt thì **exit êm** để relay job sau tiếp, chứ không loop vô hạn.

### Vì sao headful + Xvfb mà không headless

| Chế độ | Cloudflare | Kết quả trang | Verdict |
|---|---|---|---|
| Headless (v3.x) | Qua được | Server trả **login wall GIẢ** (bẫy anti-bot) | Chết ở ải 2 |
| Headful + Xvfb 1920 (v4.0) | **Tự pass** trong 12s | UI thật hiện, đọc được dropdown | ✅ Sống |

Headless để lộ `navigator.webdriver` + fingerprint automation -> server giả vờ đòi
login để đá. Headful trên Xvfb đúng độ phân giải thì các dấu vết đó biến mất,
Turnstile coi là người thật và tự xác minh.

### Vì sao 345 phút

GitHub giới hạn mỗi job 360 phút. Chạy 345 phút chừa 15 phút an toàn cho commit +
trigger. Job bị kill sớm thì state đã lưu liên tục, job sau nối tiếp embed cũ.

### Vì sao dùng pytz thay time.is

`time.is` fetch HTTP mỗi 30s -> có thể fail/chậm, log và footer lệch giờ, phụ thuộc
bên thứ 3. `pytz` Asia/Ho_Chi_Minh chạy offline, log và footer dùng chung một mốc
giờ lấy SAU khi push -> không bao giờ lệch phút.

---

## 🧊 Chính sách đóng băng

Bot v4.0 đang ở trạng thái cân bằng mong manh: **headful + Xvfb 1920x1080 + chờ 12s +
giữ browser sống**. Thiếu một miếng là Turnstile lại challenge loop. Từ giờ tới khi
THẬT SỰ hỏng, **CẤM** sửa những thứ sau:

- ❌ Không đổi `VIEWPORT` (1920x1080) và không đổi Xvfb screen — phải khớp nhau.
- ❌ Không giảm `WAIT_AFTER_GOTO_MS` (12000) hay `WAIT_UI_TIMEOUT_MS` (15000).
- ❌ Không thêm bất kỳ check "login wall" / "just a moment" nào vào luồng chính.
- ❌ Không thêm panic restart khi không thấy dropdown / parse thiếu.
- ❌ Không "tối ưu" polling, không đổi engine browser khi chưa hỏng.
- ❌ Không bận tâm quản lý `cookies.json` / `HANAMI_COOKIES` (vô nghĩa ở trang này).

Cám dỗ "cải thiện thêm tí" lúc này = rủi ro phá vỡ cái vừa chạy được. Bài học xương
máu của dự án: mỗi lần thêm logic phán đoán là một lần hỏng. Cứ để nó yên.

### Điều duy nhất cần biết trước (để khỏi hoảng)

Khi job hết 345 phút -> job relay sau mở browser MỚI tinh -> mất `cf_clearance` ->
phút đầu job sau **có thể** hiện vài dòng `⏳` rồi mới `✅`. Đó là **BÌNH THƯỜNG**,
logic mới kiên nhẫn sẽ tự qua trong ~12-30s rồi xanh tiếp. Thấy `⏳` thoáng qua
đừng vội sửa.

---

## 📁 Cấu trúc dự án

    Status-Trial-UGPhone/
    ├── .github/
    │   └── workflows/
    │       └── runner.yml          # Relay runner (workflow_dispatch)
    ├── data/                       # Bot tự tạo & commit
    │   ├── message_id.txt          # ID embed Discord (để edit tiếp)
    │   ├── prev_state.json         # Trạng thái cũ (phát hiện "vừa có máy")
    │   └── debug/
    │       └── last_error.png      # Ảnh chụp khi lỗi mềm (debug, không restart)
    ├── long_runner.py              # 🧠 Não bộ bot v4.0 (headful, kiên nhẫn)
    ├── requirements.txt            # camoufox, bs4, requests, pytz
    └── README.md

---

## 🛠️ Lỗi thường gặp & cách sửa

| Lỗi / Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| `🔐 Vẫn bị login wall` lặp rồi panic | **Đã xóa ở v4.0.** Nếu còn là do anh thêm lại check login | Xóa mọi `if 'login' in html`. Trang không cần login |
| `⏳ Cloudflare timeout 90s` + `PANIC RESTART` | Panic loop làm mất cf_clearance + CF khóa IP dồn dập | Về đúng logic v4.0: lỗi mềm chỉ chụp debug, giữ browser |
| Click Turnstile lệch / không ăn | Xvfb screen ≠ VIEWPORT code | Đặt cả hai = 1920x1080 (xem Chính sách đóng băng) |
| `⏳ UI chưa hiện` ở phút đầu job relay | Browser mới tinh, chưa có cf_clearance | BÌNH THƯỜNG, tự qua trong 12-30s, đừng sửa |
| `Không thấy dropdown` lẻ tẻ | Xvfb render chậm / modal chưa mở | Code tự chụp debug + thử lại phút sau, không restart |
| `❌ Không thể khởi động browser` lần đầu | Camoufox chưa fetch / thiếu lib hệ thống | Workflow có `Pre-download Camoufox` + `libasound2t64` |
| `libasound2 has no installation candidate` | Ubuntu 24.04 đổi tên package | Dùng `libasound2t64` trong workflow |
| `libgdk-pixbuf2.0-0 has no candidate` | Package obsolete | Dùng `libgdk-pixbuf-xlib-2.0-0` |
| `Execution context was destroyed` | Race condition khi trang đang navigate | v4.0 bọc `_safe_eval/_safe_content` retry, navigation ≠ chết |
| `Permission denied` (403 push) | Token mặc định chỉ đọc | `permissions: contents: write` + checkout bằng `secrets.PAT` |
| `rejected (fetch first)` | Remote có commit mới khi job chạy | `git push --force-with-lease` (state chỉ là cache) |
| Relay đứt (job kill trước trigger) | Vượt 360 phút hoặc crash | Bấm **Run workflow** thủ công khởi động lại chuỗi |
| Log không hiện (buffer) | Python đệm stdout qua pipe | `python -u` + `PYTHONUNBUFFERED=1` |
| Footer lệch phút / 12h | Dùng time.is, cache không đồng bộ | pytz + lấy 1 mốc giờ sau khi push (đã fix) |
| Spam embed mới mỗi lần chạy | `message_id.txt` chưa commit | Sửa 403 push để bước Commit State chạy |

---

## ⚙️ Tùy chỉnh

Các hằng số đầu `long_runner.py` (đa số nằm trong vùng CẤM SỬA):

    TARGET_URL = "https://hanaminikata.com/tools/buydevice_ugphone"
    DURATION_MINUTES = 345            # Thời gian mỗi job (phút)
    WAIT_AFTER_GOTO_MS = 12000        # 🧊 CẤM giảm: chờ Xvfb + Turnstile tự verify
    WAIT_UI_TIMEOUT_MS = 15000        # 🧊 CẤM giảm: tối đa đợi UI thật
    UI_MARKER_TEXT = "Tạo máy UGPhone"  # Mốc nhận diện UI THẬT
    VIEWPORT = {'width': 1920, 'height': 1080}  # 🧊 CẤM đổi: phải khớp Xvfb
    FAIL_ALERT_THRESHOLD = 10         # Fail bao nhiêu phút thì alert (KHÔNG restart)
    MAX_BROWSER_REOPEN = 3            # Chỉ áp dụng khi browser CHẾT THẬT
    REOPEN_COOLDOWN_S = 60            # Chờ IP nguội trước khi mở lại (khi chết thật)
    PING_AUTO_DELETE = 300            # Tự xóa tin ping sau (giây)

Workflow — step chạy bot (Xvfb screen phải = VIEWPORT):

    - name: Run 345-Minute Loop
      run: xvfb-run --server-args="-screen 0 1920x1080x24" python -u long_runner.py
      env:
        PYTHONUNBUFFERED: "1"
        DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
        ROLE_PING_ID: ${{ secrets.ROLE_PING_ID }}

---

## ❓ FAQ

**❓ Sao bot không check login cho "chắc"?**
→ Vì trang **không cần login**. Check login ở v3.x là false positive: nó đọc nhầm
text placeholder/hướng dẫn thành "login wall", đá panic restart, restart dồn dập làm
Cloudflare khóa IP (timeout 90s). Xóa check đó = hết bệnh. Đây là bài học đắt nhất
của dự án.

**❓ Sao phải headful mà không headless cho nhẹ?**
→ Headless để lộ fingerprint automation -> server trả login wall GIẢ để đá. Headful
trên Xvfb 1920x1080 thì Turnstile coi là người thật và tự pass. RAM headful Firefox
~500-700MB, runner GitHub 7GB -> dư sức.

**❓ Viewport 1920x1080 có bắt buộc không?**
→ Có, và phải khớp Xvfb screen. Lệch độ phân giải là toạ độ click Turnstile sai ->
challenge không pass.

**❓ IP datacenter có bị chặn không?**
→ Không. Đã chứng minh: Proton VPN (datacenter) và VPS (datacenter) đều vào được.
Vấn đề chưa bao giờ là IP, mà là fingerprint browser + logic panic tự hủy.

**❓ Repo private chạy được không?**
→ Được nhưng chỉ 2.000 phút/tháng. Repo **Public** = không giới hạn.

**❓ Có ping role mỗi phút không?**
→ Không. Chỉ ping khi một khu vực chuyển **hết máy -> còn máy** (so `prev_state.json`).

**❓ Làm sao biết bot đang healthy?**
→ Log có `reopen thật: 0` và `✅ Check [HH:MM] (DROPDOWN): SG: True, ...`. `reopen: 0`
nghĩa là browser không bị đóng/mở lần nào = Turnstile tự pass, không panic.

**❓ Có chạy cron/schedule được không?**
→ Không nên. Cron chạy song song gây xung đột commit. Chỉ dùng **Run workflow** để
khởi động chuỗi relay.

---

## ⚖️ Tuyên bố miễn trừ

Dự án phục vụ mục đích **học tập & giám sát cá nhân**. Tôn trọng điều khoản dịch vụ
của Hanami Website và Cloudflare. Tần suất check 1 phút/lần, không spam, không tạo
máy thật (bot chỉ ĐỌC dropdown, không bấm "Tạo máy UGPhone"), không dùng thương mại.

---

## 📜 Changelog

### Tổng quan các phiên bản

| Version | Nguồn dữ liệu | Kiến trúc đọc | Điểm nhấn |
|---|---|---|---|
| v1.0 | `/status_trial_ugphone` | Requests + scraper | Rời Render (IP bị blacklist), chuyển GitHub Actions |
| v1.3 | `/status_trial_ugphone` | Camoufox/SeleniumBase | Cơ chế Relay 345 phút + force push state |
| v1.4 | `/status_trial_ugphone` | Smart Restart | Bỏ chặn ảnh, restart chiến lược (Camoufox/SeleniumBase) |
| v1.5 | `/status_trial_ugphone` | pytz | Đồng bộ giờ, xóa time.is, hết lệch phút |
| v2.0 | `/status_trial_ugphone` | Tự chẩn đoán + alert | Phát hiện tường login, alert Discord khi fail |
| v3.x | `/tools/buydevice_ugphone` | Anti-console + inject token | Chuyển sang trang BUY, BUT mang bệnh login-wall check + panic loop |
| **v4.0** | `/tools/buydevice_ugphone` | **Headful + Xvfb 1920, kiên nhẫn** | **Xóa login-wall check + panic restart. reopen: 0. ĐÓNG BĂNG** |

### v4.0 — "Kiên nhẫn, không phán đoán sai" (phiên bản hiện tại)

**Bối cảnh:** v3.x thêm logic check "login wall" + panic restart 3 lần. Trên GitHub
Actions, logic này đọc nhầm text trang thành login wall -> panic loop -> mất
cf_clearance mỗi lần mở browser -> Cloudflare khóa IP -> timeout 90s. Đồng thời
headless bị server trả login wall GIẢ (bẫy anti-bot), còn headful trên Xvfb sai độ
phân giải thì Turnstile không render nổi.

**Thay đổi cốt lõi:**

- 🗑️ **Xóa sạch** mọi check `login` / `token` / `just a moment` trong luồng chính.
  Trang không cần login -> check đó là nguồn gốc thảm họa.
- 🗑️ **Xóa panic restart** khi không thấy dropdown / parse thiếu. Lỗi mềm giờ chỉ
  **chụp ảnh debug** (`data/debug/last_error.png`) và giữ browser sống.
- 🧠 **Đổi triết lý**: browser mở 1 lần, mỗi phút **reload nhẹ trên cùng context**
  để giữ `cf_clearance` tích luỹ. Turnstile verify 1 lần, các phút sau vào thẳng.
- 🖥️ **Headful + humanize + Xvfb 1920x1080**, `VIEWPORT` trong code khớp Xvfb screen
  để toạ độ click Turnstile chính xác.
- ⏳ **Kiên nhẫn đúng chỗ**: chờ 12s sau goto, đợi text "Tạo máy UGPhone" (tối đa 15s)
  làm mốc UI thật, thay vì poll "just a moment".
- 🛡️ **Retry-safe navigation**: `_safe_eval` / `_safe_content` phân biệt "đang navigate"
  (browser còn sống) vs "chết thật" (target closed) -> hết lỗi `Execution context
  was destroyed` và hết hiểu nhầm navigation thành chết.
- 🔒 **Mở lại browser chỉ khi chết thật**, có cooldown 60s + giới hạn 3 lần/job,
  vượt thì exit êm cho relay job sau (không loop vô hạn).
- 🧊 **Chính sách đóng băng**: liệt kê rõ những thứ CẤM sửa để không phá vỡ cân bằng.

**Kết quả kiểm chứng (log thật):**

    ✅ Browser Camoufox-Headful đã khởi động (viewport 1920x1080)
    ✅ Check [22:12] (DROPDOWN): SG: True, HK: True, JP: True, DE: True, US: True
    🕐 Footer: 22:12:05 (reopen thật: 0)

`reopen: 0` = browser không bị đóng/mở lần nào = Turnstile tự pass, không panic.

**Ghi chú:** `cookies.json` / `HANAMI_COOKIES` ở v3.x trở thành dư thừa ở v4.0 (trang
không cần login). Code vẫn đọc nếu có nhưng anh không cần tạo/quản lý nữa.

---

## 💖 Credit

- **Camoufox** — Stealth Firefox engine (headful, humanize)
- **Xvfb** — Display ảo để headful chạy trên GitHub Actions
- **BeautifulSoup4** — Parse HTML
- **pytz** — Đồng bộ giờ Việt Nam chính xác
- **Hanami Website** — Nền tảng cung cấp dữ liệu trial UGPhone
- **Aozora Cyrus** — Chủ nhân của Repository
- **Aozorians** — Hỗ trợ phát triển & testing

---

<div align="center">

*Made with ❤️ by Aozorians • v4.0 đã đóng băng — đừng sửa khi chưa hỏng • Nếu thấy hữu ích, cho repo một ⭐ nhé!*

</div>
