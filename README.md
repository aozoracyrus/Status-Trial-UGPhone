<div align="center">

# 📱 STATUS TRIAL UGPHONE — DISCORD BOT

**Giám sát trạng thái máy trial UGPhone 24/7 • GitHub Actions Relay • 100% miễn phí**

*Không VPS • Không Render • Không ScraperAPI • Không tốn một xu*

</div>

---

## 📖 Mục lục

- [🌟 Giới thiệu](#-giới-thiệu)
- [⚙️ Yêu cầu](#️-yêu-cầu)
- [🔑 Thêm Secrets](#-thêm-secrets)
- [🔓 Cấp quyền cho Repo](#-cấp-quyền-cho-repo)
- [🚀 Cách hoạt động](#-cách-hoạt-động)
- [📁 Cấu trúc dự án](#-cấu-trúc-dự-án)
- [🛠️ Lỗi thường gặp & cách sửa](#️-lỗi-thường-gặp--cách-sửa)
- [⚙️ Tùy chỉnh](#️-tùy-chỉnh)
- [❓ FAQ](#-faq)
- [⚖️ Tuyên bố miễn trừ](#️-tuyên-bố-miễn-trừ)
- [💖 Credit](#-credit)

---

## 🌟 Giới thiệu

Bot tự động theo dõi trang trạng thái trial UGPhone của **Hanami Website**
(`hanaminikata.com/status_trial_ugphone`) và hiển thị trực tiếp lên Discord:

- 🟢 **5 khu vực**: Singapore, Hong Kong, Japan, Germany, America
- 📊 **1 Embed duy nhất** được EDIT liên tục (không spam tin nhắn)
- 🕐 **Footer Uptime** cập nhật đúng giây `:00` mỗi phút, format 24h, khớp `time.is/Vietnam`
- 🔔 **Ping role** khi có server vừa hết máy → còn máy, **tự xóa sau 5 phút**
- 🛡️ **Bypass Cloudflare** bằng Camoufox (ưu tiên) + SeleniumBase UC Mode (dự phòng)
- ⚡ **Check mỗi 1 phút** bằng XHR đồng bộ (nhanh 1-3 giây, không treo)
- 🔄 **Relay 24/7**: mỗi job chạy 345 phút rồi tự kích hoạt job kế tiếp
- 💊 **Proactive Restart** mỗi 60 phút (restart trước khi browser chết)
- 🔍 **Health check** browser trước mỗi lần check để phát hiện browser chết ngầm
- 🖼️ **Không chặn ảnh** để tránh bị Cloudflare phát hiện là bot

---

## ⚙️ Yêu cầu

| Thành phần | Bắt buộc | Ghi chú |
|---|---|---|
| Tài khoản GitHub | ✅ | Repo phải để **Public** để được unlimited Actions minutes |
| Discord Webhook | ✅ | Kênh nhận embed + ping |
| Personal Access Token | ✅ | Quyền `repo` + `workflow` |
| VPS / Render | ❌ | Không cần (IP datacenter bị Cloudflare chặn) |
| Thẻ tín dụng | ❌ | Không cần |

---

## 🔑 Thêm Secrets

Vào repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Secret | Mô tả | Cách lấy |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | Webhook kênh Discord | Cài đặt kênh → Tích hợp → Webhooks → Tạo |
| `ROLE_PING_ID` | ID role để ping khi có máy | Bật Developer Mode → chuột phải role → Copy ID |
| `PAT` | Token để push code + tự trigger relay | Settings → Developer settings → Tokens (classic) → tick `repo` + `workflow` |

---

## 🔓 Cấp quyền cho Repo

1. **Đổi repo sang Public**: Settings → General → Danger zone → Change visibility
2. **Cấp quyền ghi cho Actions**: Settings → Actions → General →
   chọn **Read and write permissions** → Save

---

## 🚀 Cách hoạt động

### Chu trình Relay (tiếp sức 24/7)

```
┌────────────────────────── JOB #1 (345 phút) ──────────────────────────┐
│ 00:00  Mở browser (Camoufox) → vượt Cloudflare → sleep 10s            │
│ 60s/lần  Health check browser → XHR đồng bộ lấy HTML mới               │
│          → parse 5 khu vực → EDIT cùng 1 embed Discord (không spam)  │
│ :00/lần  Cập nhật footer Uptime (24h, khớp time.is)                   │
│ Có máy mới → ping role → tự xóa tin ping sau 5 phút                   │
│ 60:00    Proactive restart (trước khi browser chết)                    │
│ Browser chết → auto-restart → vượt CF lại → tiếp tục                  │
│ 345:00 Force push data/ (message_id + state) → trigger JOB #2         │
└───────────────────────────────────────────────────────────────────────┘
                                  ⬇️
┌────────────────────────── JOB #2 (345 phút) ──────────────────────────┐
│ Đọc data/message_id.txt → tiếp tục EDIT đúng embed cũ                 │
└───────────────────────────────────────────────────────────────────────┘
```

### Chiến lược cào dữ liệu (theo thứ tự)

1. **Health check** browser (`is_alive()`) — nếu chết → emergency restart ngay
2. **XHR đồng bộ** trong trang — lấy HTML mới từ server trong 1-3 giây
3. **Emergency restart** nếu phát hiện lỗi kết nối (HTTPConnectionPool, XHR failed)
4. **Click "Làm mới"** (null-guard) + đọc DOM — nếu XHR hỏng
5. **recover_cloudflare()** — nếu bị chặn lại: chờ xác minh → quay về trang → lấy HTML
6. **Khởi động lại browser** — nếu tất cả thất bại

### Proactive Restart Strategy

Thay vì đợi browser chết mới restart, bot **chủ động restart định kỳ**:

```
00:00  Mở browser (Camoufox) + sleep 10s để ổn định
60:00  Proactive restart (trước khi browser chết) → sleep 15s
120:00 Proactive restart → sleep 15s
180:00 Proactive restart → sleep 15s
...
345:00 Kết thúc job → force push → trigger job tiếp theo
```

**Lợi ích:**
- Browser không bao giờ chết bất ngờ
- Ít restart hơn (mỗi 60 phút thay vì mỗi 9-30 phút)
- Ổn định hơn với Camoufox + sleep dài hơn

### Smart Restart Strategy

Khi browser chết bất ngờ (emergency restart):

| Số lần restart liên tiếp | Thời gian chờ | Hành động |
|---|---|---|
| **1-2 lần** | 3 giây | Restart bình thường |
| **3-5 lần** | 15 giây | Chờ lâu hơn để browser ổn định |
| **>5 lần** | 30 giây | **Switch browser** (Camoufox ↔ SeleniumBase) |

### Tại sao 345 phút?

GitHub giới hạn mỗi job **360 phút**. Chạy 345 phút để chừa **15 phút an toàn**
cho bước commit + trigger. Nếu job bị kill sớm, dữ liệu đã được lưu liên tục
nên job sau vẫn nối tiếp được embed cũ.

### Tại sao không chặn ảnh?

**Trước (block_images=True):**
- Browser tải trang nhanh (~1s)
- Nhưng Cloudflare phát hiện: "Browser này không load ảnh → chắc chắn là bot!"
- Sau vài phút → block session → browser chết sớm (9-30 phút)

**Sau (không chặn ảnh):**
- Browser tải trang chậm hơn (~3-5s vì phải load ảnh)
- Nhưng Cloudflare thấy: "Browser này load ảnh bình thường → có vẻ là người thật"
- Session sống lâu hơn → ít restart hơn → ổn định hơn

---

## 📁 Cấu trúc dự án

```
Status-Trial-UGPhone/
├── .github/
│   └── workflows/
│       └── runner.yml          # Relay runner (chỉ workflow_dispatch)
├── data/                       # Bot tự tạo & commit
│   ├── message_id.txt          # ID embed Discord (để edit tiếp)
│   └── prev_state.json         # Trạng thái cũ (phát hiện "vừa có máy")
├── long_runner.py              # 🧠 Não bộ của bot
├── requirements.txt            # seleniumbase, camoufox, bs4, requests
└── README.md
```

---

## 🛠️ Lỗi thường gặp & cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `Permission to ... denied to github-actions[bot]` (403 push) | Token mặc định chỉ có quyền đọc | Thêm `permissions: contents: write` + checkout bằng `secrets.PAT` + bật Read/Write permissions |
| `rejected (fetch first)` / `Merge conflict` | Remote có commit mới khi job đang chạy | Dùng `git push --force-with-lease` (state chỉ là cache, force push an toàn) |
| Kẹt `Just a moment...` | Cloudflare challenge | Bot tự xử lý (`wait_cloudflare` / `recover_cloudflare`). Nếu kéo dài, tự restart browser |
| `Cannot read properties of null (reading 'click')` | Trang CF không có nút "Làm mới" | Đã fix bằng null-guard trong `click_refresh()` |
| `HTTPConnectionPool timeout` / `XHR failed` | Browser chết sau vài phút | **Đã fix**: Proactive restart mỗi 60 phút + emergency restart khi phát hiện lỗi |
| `LeakWarning: Blocking image requests` | Cloudflare phát hiện bot không load ảnh | **Đã fix**: Bỏ `block_images=True` khỏi Camoufox |
| Browser chết sớm (9-30 phút) | Cloudflare phát hiện pattern bất thường | **Đã fix**: Không chặn ảnh + Proactive restart mỗi 60 phút |
| Mỗi lần check mất 6-7 phút | Code cũ mở browser mới mỗi lần | Đã fix: giữ browser mở + XHR đồng bộ + watchdog 20s |
| Footer lệch phút / hiện 12h | Cập nhật không đúng nhịp | Đã fix: update đúng giây `:00`, format 24h, nguồn time.is |
| Spam embed mới mỗi lần chạy | `message_id.txt` chưa được commit | Sửa lỗi 403 push (mục trên) để bước Commit State hoạt động |
| Relay đứt (job bị kill trước khi trigger) | Vượt 360 phút hoặc crash | Bấm **Run workflow** thủ công để khởi động lại chuỗi |
| `Workflow run time exceeded` | Job quá 360 phút | Giữ `DURATION_MINUTES = 345` |
| Log không hiện (bị buffer) | Python đệm stdout khi chạy qua pipe | **Đã fix**: Dùng `python -u` + `PYTHONUNBUFFERED=1` trong workflow |

---

## ⚙️ Tùy chỉnh

Các hằng số ở đầu `long_runner.py`:

```python
DURATION_MINUTES = 345          # Thời gian chạy mỗi job (phút)
CHECK_INTERVAL = 60             # Nhịp check trạng thái (giây) - GIỮ 60s để footer không lệch
PING_AUTO_DELETE = 300          # Tự xóa tin ping sau (giây)
BROWSER_LIFETIME_MINUTES = 60   # Proactive restart mỗi X phút
```

Các keyword phát hiện browser chết:

```python
BROWSER_DEAD_KEYWORDS = [
    'httpconnectionpool', 'localhost', 'timeout', 'read timeout',
    'failed to execute', 'invalid selector', 'session info',
    'target closed', 'connection refused', 'browser has been closed',
    'no such window', 'no target', 'target page, context or browser'
]
```

---

## ❓ FAQ

**❓ Repo private có chạy được không?**
→ Được nhưng chỉ 2.000 phút/tháng. Repo **Public** = không giới hạn.

**❓ Có ping role mỗi phút không?**
→ Không. Chỉ ping khi một khu vực chuyển **hết máy → còn máy**
(so sánh với `prev_state.json`).

**❓ Server Hanami khởi động lại thì sao?**
→ Bot phát hiện Cloudflare chặn lại → tự xác minh → tự quay về trang →
tiếp tục check trong 1-2 phút.

**❓ Browser chết sau vài phút thì sao?**
→ Bot có 2 cơ chế:
1. **Proactive restart** mỗi 60 phút (restart trước khi browser chết)
2. **Emergency restart** khi phát hiện lỗi kết nối qua health check hoặc keyword
Số lần restart được đếm và hiển thị ở footer.

**❓ Tại sao không dùng Render/VPS?**
→ IP datacenter của Render/VPS bị Cloudflare blacklist.
GitHub Actions runner sạch hơn + miễn phí.

**❓ Có thể chạy schedule (cron) không?**
→ Không nên. Cron sẽ chạy song song với relay, gây xung đột commit.
Chỉ dùng **Run workflow** thủ công để khởi động chuỗi.

**❓ Tại sao không chặn ảnh để load nhanh hơn?**
→ Vì Cloudflare phát hiện browser không load ảnh → block session sau vài phút.
Không chặn ảnh giúp bot "giống người thật" hơn → session sống lâu hơn.

**❓ Tại sao CHECK_INTERVAL phải là 60s?**
→ Vì footer cập nhật đúng giây `:00` mỗi phút. Nếu dùng 90s, footer sẽ bị lệch
(không cập nhật đúng phút). Giữ 60s để footer luôn khớp với `time.is/Vietnam`.

**❓ Làm sao biết bot đang hoạt động tốt?**
→ Xem log GitHub Actions, tìm dòng:
- `🕐 Footer cập nhật lúc XX:XX:00` (footer cập nhật đúng phút)
- `⏰ Browser đã chạy X phút, proactive restart...` (browser sống đủ 60 phút)
- `🔄 Check lần Y [HH:MM] (XHR): SG: True, HK: True, ...` (check thành công)

**❓ Force push có an toàn không?**
→ An toàn vì file `data/prev_state.json` chỉ là cache tạm thời. Nếu bị mất, job mới
sẽ so sánh với empty state → có thể ping nhầm 1 lần nhưng không ảnh hưởng chức năng.
File `data/message_id.txt` vẫn được giữ để edit đúng embed cũ.

---

## ⚖️ Tuyên bố miễn trừ

Dự án phục vụ mục đích **học tập & giám sát cá nhân**.
Tôn trọng điều khoản dịch vụ của Hanami Website và Cloudflare.
Không lạm dụng tần suất request, không sử dụng cho mục đích thương mại.

---

## 💖 Credit

- **Camoufox** — Stealth Firefox engine (browser chính, ổn định nhất)
- **SeleniumBase** — UC Mode bypass Cloudflare (browser dự phòng)
- **BeautifulSoup4** — Parse HTML
- **time.is** — Nguồn giờ chuẩn Việt Nam
- **Hanami Website** — Dữ liệu trạng thái trial UGPhone
- **Kanamoto Kumo** — Chủ nhân của Repository
- **Korchi Community** — Hỗ trợ phát triển & testing

---

<div align="center">

*Made with ❤️ by Korchi Community • Nếu thấy hữu ích, cho repo mình một ⭐ nhé!*

</div>
