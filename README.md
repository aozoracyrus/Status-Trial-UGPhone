<div align="center>

# 📱 STATUS TRIAL UGPHONE — DISCORD BOT

**Giám sát trạng thái máy trial UGPhone 24/7 • GitHub Actions Relay • 100% miễn phí**

*Không VPS • Không Render • Không ScraperAPI • Không token đăng nhập • Không tốn một xu*

**Phiên bản v5.3 — "Chrome-CDP + peek-only + tự kéo về trang".**
Sau 13 phiên bản, bot đã tìm ra con đường sống trên GitHub Actions: **engine Chrome
thật điều khiển qua CDP (DrissionPage)** thay vì Firefox-stealth (Camoufox), và
**mỗi phút chỉ "nhìn trộm" DOM (peek) chứ không tải lại trang (goto)**. Kết quả:
Cloudflare managed-auto tự nhả trong ~7 giây, bot xanh liền mạch hàng chục phút,
và khi site đá bot về Dashboard (anti-console/idle) thì bot **tự goto ép về lại
trang buydevice** mà không cần réo chủ. VPS đã được loại — GitHub là đường chính.

**Trạng thái hiện tại (07/11/2026):** 🟢 ĐANG CHẠY. CF vào ~7s, peek-only sạch,
UNK = redirect Dashboard đã có recovery tự cure.

</div>

---

## 📖 Mục lục

- [🌟 Giới thiệu](#-giới-thiệu)
- [⚙️ Yêu cầu](#️-yêu-cầu)
- [🔑 Thêm Secrets](#-thêm-secrets)
- [🔓 Cấp quyền cho Repo](#-cấp-quyền-cho-repo)
- [🚀 Cách hoạt động (kiến trúc v5.3)](#-cách-hoạt-động-kiến-trúc-v53)
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

Bốn sự thật nền tảng (mỗi sự thật đều có bằng chứng log/ảnh thật, không suy diễn):

- Trang này **HOÀN TOÀN KHÔNG CẦN ĐĂNG NHẬP**. Chrome thường, không login, vẫn
  thấy dropdown 5 khu vực + nút "Tạo máy UGPhone". Mọi check "login wall" đều là
  ảo giác của code (bệnh v3.x) và đã bị xóa vĩnh viễn.
- Lớp bảo vệ là **Cloudflare managed-auto**: trang "Verifying you are human"
  hiện ~7 giây rồi **tự nhả**, KHÔNG có checkbox/widget để click. Đây là lý do
  code `click_turnstile` thường in `ℹ️ Không thấy widget` — đó là BÌNH THƯỜNG,
  không phải lỗi.
- Site có **anti-console / idle-guard**: ngồi im quá lâu HOẶC navigate sai nhịp
  sẽ bị **đá về trang Dashboard gốc** (`hanaminikata.com`, "Đăng nhập để xem
  Dashboard"). Đây KHÔNG phải trang lạ, KHÔNG phải login wall — nó là redirect
  lạc trang. v5.3 chữa bằng cách **goto ép về buydevice lại** (recovery), bot tự
  fix, không réo chủ.
- **Engine quyết định tất cả**: Firefox-stealth (Camoufox) bị CF chấm điểm thấp
  → kẹt từ phút 0, reset context cũng thua. Chrome thật qua CDP (DrissionPage)
  → vân tay sạch, `navigator.webdriver` không bị set kiểu Selenium → CF tự nhả
  ~7s. Bằng chứng: `drift_test` PASS+DATA, rồi 39–49 phút GREEN liên tục.

Tính năng cốt lõi v5.3:

- 🟢 **5 khu vực** SG / HK / JP / DE / US — đọc chấm màu từ DOM live (🟢 còn máy,
  🔴 hết máy).
- 📊 **1 Embed duy nhất** được EDIT liên tục, không spam. Khi lỗi, embed đổi sang
  3 dòng: `🚨 Đang gặp lỗi` / `🤔 Lí do` / `🛠️ Chúng tôi sẽ sửa`.
- 🕐 **Footer Uptime** đúng giây `:00` mỗi phút, 24h, `pytz` Asia/Ho_Chi_Minh.
- 🔔 **Ping role** khi khu vực hết → còn máy, tự xóa sau 5 phút.
- 👤 **Ping chủ (owner)** CHỈ khi lỗi **nghiêm trọng dai dẳng** (bot bó tay).
  Tin ping **TREO SUỐT** thời gian embed đỏ, **chỉ bị xóa khi bot XANH lại**
  (không timer 5p), và có **cooldown 10 phút** chống spam khi bot dao động chớp.
  CF và SRV (server nghỉ) **KHÔNG BAO GIỜ ping** — bot tự lo / chờ.
- 🖥️ **Headful Chrome thật + Xvfb 1920x1080**, điều khiển qua CDP (DrissionPage),
  `humanize` bật, không chặn ảnh.
- 👁️ **Peek-only mỗi phút**: đọc `page.html` (DOM đã hydrate), **KHÔNG goto**.
  Không navigation = Cloudflare không có cớ chèn challenge = xanh liền mạch.
- 🔁 **Goto có chủ đích, có节流**: chỉ 3 lúc — (1) mở job 1 lần, (2) goto-thừa
  mỗi 10 phút để re-hydrate chống data stale, (3) recovery khi UNK. Mỗi loại có
  trần riêng, không spam.
- ♻️ **Retry-hydrate**: UNK ngay sau goto-thừa → retry peek 3 lần cách 8s trước
  khi kết luận (phân biệt "hydrate chậm, cứu được" vs "trang lạ thật").
- 📸 **Ảnh debug push NGAY khi chụp** (throttle 60s) → mở GitHub lúc lỗi là thấy
  ảnh mới, không đợi job chết. Mọi nhánh lỗi (SRV/CF/UNK/GREEN-mù) đều chụp.
- 🛡️ **Máy trạng thái 4 chế độ** GREEN / SRV / CF / UNK, mỗi chế độ một phản ứng
  riêng, không gộp thành panic loop.
- 🔄 **Relay 24/7**: job 345 phút, force-push state, tự kích job kế.

---

## ⚙️ Yêu cầu

| Thành phần | Bắt buộc | Ghi chú |
|---|---|---|
| Tài khoản GitHub | ✅ | Repo **Public** = unlimited minutes |
| Discord Webhook | ✅ | Kênh nhận embed + ping + owner ping |
| Personal Access Token | ✅ | Quyền `repo` + `workflow` |
| Xvfb screen 1920x1080 | ✅ | **Phải khớp** `VIEWPORT` code, lệch = sai toạ độ |
| Google Chrome (runner) | ✅ | Image `ubuntu-26.04` đã có sẵn `google-chrome-stable` |
| VPS / Render | ❌ | **Đã loại.** GitHub là đường chính (xem FAQ) |
| Token đăng nhập / cookie | ❌ | **Không cần.** Trang không đòi login |
| Residential proxy / CapSolver | ❌ | **Không cần.** CF tự nhả ~7s, datacenter vô tội |

---

## 🔑 Thêm Secrets

Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Secret | Mô tả | Cách lấy |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | Webhook kênh Discord | Kênh → Tích hợp → Webhooks → Tạo |
| `ROLE_PING_ID` | ID role để ping khi có máy | Developer Mode → chuột phải role → Copy ID |
| `PAT` | Token push + trigger relay | Developer settings → Tokens (classic) → `repo` + `workflow` |

> `OWNER_ID` (ID chủ để réo khi lỗi nghiêm trọng) **KHÔNG** đưa vào Secrets/env.
> Nó hard-default trong code. Lý do: nếu truyền qua env mà secret trống, env sẽ
> = `""` (chuỗi rỗng) làm code nhận `""` thay vì default → ping hỏng âm thầm
> `<@>`. Muốn đổi ID thì sửa 1 dòng trong `long_runner.py`, không thêm env.

> `HANAMI_COOKIES` / `cookies.json` ở v3.x là **dư thừa** từ v4.0 trở đi (trang
> không cần login). Code v5.3 không còn đọc chúng — xóa khỏi repo/secrets cho gọn.

---

## 🔓 Cấp quyền cho Repo

1. **Repo sang Public**: Settings → General → Danger zone → Change visibility
2. **Ghi cho Actions**: Settings → Actions → General → **Read and write permissions** → Save

---

## 🚀 Cách hoạt động (kiến trúc v5.3)

Bot chạy trên **một Chrome thật** (qua CDP) cho cả job. Mỗi phút, bot nhìn DOM
hiện tại và phân loại thành 4 chế độ, rồi phản ứng ĐÚNG bệnh của chế độ đó.
Nguyên tắc vàng: **chỉ goto khi thật cần; khi chưa chắc thì peek, không reload.**

Phân loại bằng chuỗi đặc trưng THẬT (không đoán mò, không có login/token):

    GREEN  = DOM chứa "Tạo máy UGPhone"        → trang buydevice đã hydrate
    SRV    = DOM chứa "error code 520/5xx..."  → máy chủ Hanami nghỉ
    CF     = DOM chứa "verifying you are human" / "just a moment" → Cloudflare
    UNK    = không match cả 3                  → thường là bị đá về Dashboard

Mở đầu job: `open_browser()` → goto 1 lần → classify → nếu UNK thì recovery ngay.

Mỗi phút (đúng nhịp `:00`), lặp 1 vòng:

    NẾU browser chết (đọc title fail):
        đóng -> cooldown 60s -> MỞ CHROME MỚI (trần 3 lần/job)
        vượt trần -> ping chủ -> KẾT THÚC JOB ÊM

    NẾU mode = GREEN:
        nếu đã 10p kể từ goto trước VÀ còn suất goto-thừa:
            goto re-hydrate (chống stale) -> peek -> classify
            nếu UNK sau goto: retry peek 3 lần cách 8s
                cứu được (GREEN) -> tiếp
                vẫn UNK -> ghi nhận "không phải hydrate chậm"
        NGƯỢC LẠI (phút thường): CHỈ peek, KHÔNG goto   ← đây là bí quyết xanh
        peek -> classify:
            GREEN  -> parse 5 region từ page.html -> data
            SRV    -> chuyển mode SRV, chụp ảnh, chờ thụ động
            CF     -> chuyển mode CF, click best-effort, chờ tự nhả
            UNK    -> RECOVERY: goto ép về buydevice 1 lần/episode
                        cure (GREEN) -> lấy data, KHÔNG ping
                        fail -> chuyển mode UNK dai dẳng

    NẾU mode = SRV (server nghỉ):
        CHỈ peek chờ, KHÔNG reload, KHÔNG goto, KHÔNG ping
        (IPv4/runner mới cũng vô ích vì cùng server đó đang nghỉ)
        server sống lại -> GREEN -> đọc data

    NẾU mode = CF (Cloudflare verify):
        peek chờ, KHÔNG reload (reload = đá nát verify)
        click widget best-effort 1 lần (managed-auto thường không có gì để click)
        kẹt >= 4p -> mở context Chrome mới (danh tính mới) -> trần 3
        hết trần -> ping chủ -> KẾT THÚC JOB ÊM (nhường job sau IP mới)

    NẾU mode = UNK (bị đá về Dashboard):
        lần đầu vào UNK -> RECOVERY goto ép về buydevice
            cure -> GREEN, không ping
            fail -> đếm UNK, chờ thụ động
        UNK >= 8p -> ping chủ -> KẾT THÚC JOB ÊM

Cuối mỗi phút: xanh → push embed 5 khu vực + xóa owner ping (nếu có) + reset
flag recovery; lỗi → push embed 3 dòng (🚨/🤔/🛠️) + ping chủ NẾU nghiêm trọng
dai dẳng (CF/SRV không ping). `fail_streak` chỉ dùng để ping, **không bao giờ**
đụng browser.

### Vì sao Chrome-CDP mà không Firefox-stealth

    Camoufox/Firefox (v3–v4.11): CF chấm điểm thấp -> kẹt PHÚT 0, reset context
                      (cùng IP, cùng engine) cũng thua -> chết job sau 11p.
    DrissionPage/Chrome-CDP (v5.0+): Chrome thật, attach qua CDP, navigator.webdriver
                      không set kiểu Selenium -> CF managed-auto tự nhả ~7s ->
                      39–49p GREEN liên tục. Cùng runner, cùng Xvfb, cùng IP —
                      chỉ khác engine. Đây là thay đổi quyết định, có bằng chứng.

### Vì sao peek-only mà không goto mỗi phút

    goto mỗi phút (bệnh v4.3): Cloudflare thấy một "khách" reload trang protected
                      dày đặc = hành vi bot kinh điển -> chèn challenge giữa job.
    peek-only (v5.0+): đọc DOM đã hydrate, KHÔNG navigation -> CF không có cớ
                      chèn challenge -> xanh liền mạch. goto chỉ còn 3 lúc có
                      chủ đích (mở / goto-thừa thưa / recovery), có节流.

### Vì sao UNK phải recovery (đây là phát hiện quan trọng nhất)

Ảnh `last_error.png` thật cho thấy "trang không rõ mặt" kỳ thực là **Dashboard
gốc** (`hanaminikata.com`, "Đăng nhập để xem Dashboard"), KHÔNG phải buydevice.
Site có anti-console/idle-guard đá bot về nhà. Fix: khi UNK, bot **goto ép về
TARGET_URL (buydevice)** 1 lần. Cure được → GREEN, bot tự fix, không réo chủ.
Không cure → mới là UNK dai dẳng thật → ping. Giới hạn 1 lần/episode + trần
riêng, không spam goto.

### Vì sao pytz thay time.is

`time.is` fetch HTTP mỗi 30s → fail/chậm, log và footer lệch giờ, phụ thuộc bên 3.
`pytz` chạy offline, log và footer dùng chung MỘT mốc giờ lấy sau khi push → không
bao giờ lệch phút.

---

## 🧊 Chính sách đóng băng

v5.3 chạy được là nhờ đúng bộ thông số hiện tại. **CẤM** sửa khi bot đang xanh:

- ❌ Không đổi `VIEWPORT` (1920x1080) và không đổi Xvfb screen — phải khớp nhau.
- ❌ Không giảm `WAIT_AFTER_GOTO_S` (12). Con số 12 = CF tự nhả ~7s + buffer.
      Giảm xuống < 7s = bot peek lúc CF chưa nhả → UNK/CF oan.
- ❌ Không đổi `UI_MARKER_TEXT` ("Tạo máy UGPhone") trừ khi website ĐỔI nút thật
      (khi đó chỉ sửa 1 chuỗi, không đụng kiến trúc).
- ❌ Không thêm BẤT KỲ check "login" / "token" / "đăng nhập" nào vào luồng chính.
      Đó là nguồn gốc thảm họa v3.x. Trang không cần login. UNK = redirect
      Dashboard, KHÔNG phải login wall — đừng nhầm lại.
- ❌ Không đổi engine browser (Chrome-CDP → Camoufox/Puppeteer/Playwright/Brave...).
      Đây là bài học ĐẮT nhất series: Firefox-stealth kẹt phút 0, Chrome-CDP xanh.
      Đổi engine trên GitHub Actions = quay lại chết, chỉ khác logo.
- ❌ Không bật `disable_coop=True`, không set `window=(1280,720)`, không override
      User-Agent. Mấy thứ này là lý thuyết chung trên mạng, áp vào = phá fingerprint
      đang xanh + lệch viewport khỏi Xvfb = sai toạ độ.
- ❌ Không mua residential proxy, không đăng ký CapSolver/Anti-Captcha. CF ở đây
      managed-auto ~7s, datacenter vô tội (Proton/VPS/Chrome thường đều vào được).
- ❌ Không "tối ưu" polling, không bỏ humanize, không bật lại chặn ảnh, không bỏ
      peek-only (đừng thêm goto mỗi phút lại).

### Cái trần tự-cứu là NGOẠI LỆ được phép (và vì sao)

Các biến `CF_STUCK_RESTART_MIN` (4), `MAX_CF_RESTART` (3), `CF_GRACE_MIN` (2),
`UNK_GIVEUP_MIN` (8), `MAX_RECOVERY_GOTO` (40), `REFRESH_EVERY_MIN` (10),
`MAX_REAL_GOTO` (40), `GOTO_UNK_RETRY` (3) là **mới/cập nhật ở v5.x** và ĐƯỢC phép
tồn tại vì chúng kích hoạt dựa trên **bằng chứng cứng** (ảnh `last_error.png` =
Dashboard; log = CF tự nhả ~7s; log = UNK sau goto), KHÔNG phải đoán mò. Phân biệt rõ:

    Đóng băng cấm: SUY ĐOÁN trạng thái trang rồi hành động (bệnh v3/v4.0).
    Cho phép:      PHỤC HỒI có giới hạn khi một trạng thái ĐÃ ĐƯỢC XÁC MINH bằng ảnh/log.

Quy tắc vàng: **đừng đặt trần = vô hạn** (tái sinh liệt-có-tổ-chức của v4.0), và
**đừng đặt trần = 0** (tái sinh panic loop của v3). Giá trị hiện tại là điểm cân
bằng: đủ kiên nhẫn cho CF tự nhả + đủ recovery cho idle-redirect + đủ trần để
không nằm liệt.

### Điều duy nhất cần biết trước (để khỏi hoảng)

Phút đầu mỗi job (Chrome mới tinh, chưa có `cf_clearance`) **sẽ** hiện ~7s trang
"Verifying you are human" rồi tự GREEN. Đó là BÌNH THƯỜNG. Giữa job, nếu thấy
`↩️ Recovery ... -> GREEN` nghĩa là site đá bot về Dashboard và bot tự kéo về —
cũng BÌNH THƯỜNG, không ping. Chỉ lo khi thấy `🛑 ... bó tay` lặp nhiều job liên
tiếp => khi đó anti-console siết cả recovery, mới tính chuyện khác (NHƯNG VPS đã
loại, xem FAQ).

---

## 📁 Cấu trúc dự án

    Status-Trial-UGPhone/
    ├── .github/
    │   └── workflows/
    │       ├── runner.yml              # Relay (workflow_dispatch), Xvfb 1920x1080x24
    │       └── drift-test.yml          # (tùy chọn) test engine Chrome-CDP độc lập
    ├── data/                           # Bot tự tạo & force-push
    │   ├── message_id.txt              # ID embed Discord (edit tiếp)
    │   ├── prev_state.json             # Trạng thái cũ (phát hiện "vừa có máy")
    │   ├── owner_ping_id.txt           # ID tin ping chủ đang treo (xóa khi xanh)
    │   └── debug/
    │       └── last_error.png          # Ảnh chụp khi lỗi (push NGAY, soi được lúc chạy)
    ├── long_runner.py                  # 🧠 Não bộ v5.3 (Chrome-CDP + peek-only + recovery)
    ├── drift_test.py                   # (tùy chọn) script test engine 1 lần
    ├── requirements.txt                # DrissionPage, bs4, requests, pytz
    └── README.md

---

## 🛠️ Lỗi thường gặp & cách sửa

| Lỗi / Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| `❓ UNK` lặp rồi `🛑` chết job, ảnh = trang **Dashboard** | **Anti-console/idle đá về nhà (bệnh v5.0–5.2):** bot ngồi ở buydevice bị kéo về gốc, classify không match → UNK | v5.3 recovery: UNK → goto ép về buydevice. Nếu recovery fail dai dẳng → trần `MAX_RECOVERY_GOTO` hết → nhường job sau. Đừng thêm check login — đó KHÔNG phải login wall |
| `🟡 CF` lặp giữa job (kiểu Camoufox) | Engine Firefox-stealth bị CF chấm thấp | **Đã giải quyết bằng v5.0**: chuyển Chrome-CDP. Nếu còn thấy lặp → đừng vá Firefox, xác nhận đang chạy đúng `long_runner.py` v5.3 (in `🏁 v5.3 starting`) |
| `ℹ️ Không thấy widget Turnstile để click` | CF ở đây managed-auto, không có checkbox | BÌNH THƯỜNG. Code chờ tự nhả ~7s. Không phải lỗi, không cần sửa |
| `Fail streak` dài + `reopen:0` + ảnh = "Verifying you are human" | Liệt-có-tổ-chức (bệnh v4.0): kẹt CF nhưng browser sống nên không restart | v5.x có trần CF + mở context mới + nhường job sau. Nếu vẫn streak vô hạn → kiểm tra trần CF_* chưa bị sửa về vô hạn |
| Ảnh `last_error.png` trên GitHub là ảnh CŨ khi đang lỗi | (bệnh v5.1): commit state chỉ push CUỐI job | v5.2+ push ảnh NGAY khi chụp (throttle 60s). Nếu vẫn cũ → kiểm tra `push_debug_shot` có chạy (log `📤 Đã push ảnh debug`) |
| Owner ping spam nhiều tin / không xóa khi xanh | (bệnh v4.9/v4.10): timer xóa + green_streak quá cao | v5.x: xóa NGAY khi xanh + cooldown 10p chống flap + idempotent qua file `owner_ping_id.txt`. Nếu vẫn spam → xem log `🧹 Đã xóa` / `⏸️ Bỏ qua ping` |
| `⚠️ Xóa ping fail HTTP ...` lặp | Webhook không có quyền xóa / mid sai | GIỮ id retry, không post trùng (kênh vẫn 1 tin). Báo chủ kiểm tra webhook |
| `🔐 Vẫn bị login wall` lặp rồi panic | **Đã xóa ở v4.0+.** Còn là do ai thêm lại check login | Xóa mọi `if 'login' in html`. Trang không cần login |
| Click Turnstile lệch / không ăn | Xvfb screen ≠ `VIEWPORT` code | Đặt cả hai = 1920x1080 |
| `libasound2 has no installation candidate` | Ubuntu 26.04 đổi tên package | Workflow dùng `libasound2t64` (đã đúng) |
| `libgdk-pixbuf2.0-0 has no candidate` | Package obsolete trên 26.04 | Workflow dùng `libgdk-pixbuf-xlib-2.0-0` (đã đúng) |
| `Permission denied` (403 push) | Token mặc định chỉ đọc | `permissions: contents: write` + checkout bằng `secrets.PAT` |
| `rejected (fetch first)` | Remote có commit mới khi job chạy | `git push --force-with-lease` (state chỉ là cache) |
| Relay đứt (job kill trước trigger) | Vượt 360 phút hoặc crash | Bấm **Run workflow** thủ công khởi động lại chuỗi |
| Log không hiện (buffer) | Python đệm stdout qua pipe | `python -u` + `PYTHONUNBUFFERED=1` |
| Footer lệch phút / 12h | Dùng time.is, cache không đồng bộ | pytz + lấy 1 mốc giờ sau khi push (đã fix) |
| Embed hiện cờ "nửa vời" / ký tự lạ | Giá trị `flag` thiếu 1 codepoint | Mỗi flag = ĐỦ 2 regional-indicator (🇸🇬🇭🇰🇯🇵🇩🇪🇺🇸) — thuần mỹ quan |
| `LeakWarning: Canvas and WebGL readback return random data` | (chỉ ở bản Camoufox cũ) cảnh báo vô hại | v5.3 dùng Chrome-CDP, không còn warning này. Nếu thấy = đang chạy nhầm bản cũ |

---

## ⚙️ Tùy chỉnh

Hằng số đầu `long_runner.py` (🧊 = vùng CẤM SỬA khi xanh):

    TARGET_URL = "https://hanaminikata.com/tools/buydevice_ugphone"
    DURATION_MINUTES = 345              # Thời gian mỗi job (phút)
    WAIT_AFTER_GOTO_S = 12              # 🧊 CẤM giảm (<7s = peek lúc CF chưa nhả)
    UI_MARKER_TEXT = "Tạo máy UGPhone"  # 🧊 Mốc UI THẬT (chỉ sửa khi web đổi nút)
    VIEWPORT = {'width': 1920, 'height': 1080}  # 🧊 CẤM đổi: phải khớp Xvfb
    OWNER_PING_FAIL_THRESHOLD = 2       # Lỗi NGHIÊM TRỌNG >= p này mới ping chủ
    OWNER_PING_COOLDOWN_S = 600         # Sau khi xóa ping, chặn post lại 10p (chống flap)
    PING_AUTO_DELETE = 300              # Role ping (có máy) tự xóa sau (giây)

    # --- goto có节流 (3 loại, mỗi loại trần riêng) ---
    REFRESH_EVERY_MIN = 10              # 🔓 goto-thừa chống stale (MỞ: xem FAQ freshness)
    MAX_REAL_GOTO = 40                  # 🔓 trần goto-thừa + mở job
    GOTO_UNK_RETRY = 3                  # 🔓 retry peek sau goto-thừa khi UNK
    GOTO_UNK_RETRY_WAIT_S = 8
    MAX_RECOVERY_GOTO = 40              # 🔓 trần recovery ép về buydevice khi UNK

    # --- máy trạng thái tự-cứu ---
    CF_STUCK_RESTART_MIN = 4            # 🔓 kẹt CF >= p này -> mở context mới
    CF_GRACE_MIN = 2                    # 🔓 CF thoáng qua <= p này -> giữ embed xanh
    MAX_CF_RESTART = 3                  # 🔓 trần context mới mỗi job
    CF_RESTART_COOLDOWN_S = 30
    UNK_GIVEUP_MIN = 8                  # 🔓 UNK dai dẳng >= p này -> nhường job sau
    MAX_BROWSER_REOPEN = 3              # 🔓 trần mở lại khi Chrome CHẾT THẬT
    REOPEN_COOLDOWN_S = 60

Workflow — step chạy bot (Xvfb screen phải = `VIEWPORT`):

    - name: Run 345-Minute Loop
      run: xvfb-run --server-args="-screen 0 1920x1080x24" python -u long_runner.py
      env:
        PYTHONUNBUFFERED: "1"
        DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
        ROLE_PING_ID: ${{ secrets.ROLE_PING_ID }}
        # CỐ Ý KHÔNG truyền OWNER_ID (xem mục Secrets)

---

## ❓ FAQ

**❓ Sao không dùng VPS? / VPS có tốt hơn không?**
→ **VPS đã được loại** (chủ repo xác nhận "VPS = died"). GitHub Actions là đường
chính. v5.3 chứng minh GitHub sống được: Chrome-CDP vượt CF ~7s, peek-only xanh
liền mạch, và idle-redirect (đá về Dashboard) đã có recovery tự cure. Giới hạn
của GitHub (anti-console kick) được xử lý bằng recovery + nhường job sau lấy IP
mới, không cần VPS.

**❓ UNK là gì, có phải bị chặn đăng nhập không?**
→ **KHÔNG.** Ảnh debug thật cho thấy UNK = bot bị đá về trang **Dashboard gốc**
("Đăng nhập để xem Dashboard"), do anti-console/idle-guard của site, KHÔNG phải
login wall. Bot không cần login. v5.3 chữa bằng recovery goto ép về buydevice.
Đừng thêm check login — đó chính là bệnh v3.x đã giết bot nhiều lần.

**❓ Cloudflare có cần click / cần solver không?**
→ **KHÔNG.** CF ở đây là managed-auto, trang "Verifying you are human" hiện ~7s
rồi **tự nhả**, không có checkbox/widget. Code `click_turnstile` là best-effort,
thường in "Không thấy widget" — BÌNH THƯỜNG. Không cần CapSolver/Anti-Captcha,
không cần residential proxy (datacenter vô tội: Proton/VPS/Chrome thường đều vào).

**❓ peek-only có làm data stale (cũ) không?**
→ **CÂU HỎI MỞ — chủ repo chưa chốt dứt điểm.** peek-only đọc DOM đã hydrate;
nếu SPA Hanami TỰ poll API nội bộ thì data luôn fresh, goto-thừa là thừa. Nếu
SPA KHÔNG tự poll thì data đứng im tới lần goto-thừa kế (10p). v5.3 GIỮ
goto-thừa mỗi 10p như lưới an toàn, nhưng goto cũng là 1 trigger bị đá về
Dashboard (đã có recovery). **Ai fork/duy trì:** mở web thật, xem dot màu có tự
đổi mà bot không thấy không — đổi → giữ goto-thừa; không đổi → có thể bỏ
goto-thừa (`REFRESH_EVERY_MIN` đặt rất lớn) để giảm risk redirect. Đừng tự bỏ
khi chưa kiểm chứng — đó là bài học geoip (em từng đoán mò, log chứng minh vô dụng).

**❓ Sao bot không ping khi kẹt CF / server nghỉ?**
→ Vì đó là bệnh **bot tự lo được**: CF tự nhả ~7s (grace nuốt flicker), SRV là
Hanami nghỉ (anh có fix cũng vô ích, bot chờ). Chỉ lỗi **nghiêm trọng dai dẳng**
(bot bó tay: UNK recovery fail / GREEN-mù / Chrome chết hết suất) mới réo chủ.
Nguyên tắc: đừng làm phiền chủ cho chuyện bot tự chữa được.

**❓ Tin ping chủ sao không biến mất sau 5 phút như role ping?**
→ Vì vòng đời nó KHÁC. Role ping = báo sự kiện (máy vừa xuất hiện) → xóa 5p cho
sạch kênh. Owner ping = báo TÌNH TRẠNG lỗi → phải TREO SUỐT lúc embed đỏ, chỉ
xóa khi bot XANH lại (đúng ý chủ). Cooldown 10p chống spam khi bot dao động chớp.

**❓ Repo private chạy được không? / Có ping mỗi phút không? / Chạy cron được không?**
→ Private chỉ 2.000 phút/tháng (Public = không giới hạn). Chỉ ping khi khu vực
hết → còn máy (so `prev_state.json`). Không chạy cron (xung đột commit); chỉ
**Run workflow** để khởi động chuỗi relay.

**❓ Làm sao biết bot healthy ở v5.3?**
→ Log xen kẽ `✅ Check [...] (DOM)` mỗi phút; khi site đá về Dashboard thì thấy
`↩️ Recovery ... -> GREEN` (bot tự cure, không ping); khi CF chen thì `⏳ CF
thoáng qua` rồi xanh lại. Footer có `recovery:n/40` cho biết bot đã phải kéo về
bao nhiêu lần. KHÔNG thấy streak vô hạn, KHÔNG thấy `🟡 CF` lặp như bản Camoufox.

---

## ⚖️ Tuyên bố miễn trừ

Dự án phục vụ **học tập & giám sát cá nhân**. Tôn trọng ToS của Hanami Website và
Cloudflare. Tần suất 1 phút/lần, không spam, **không tạo máy thật** (bot chỉ ĐỌC
dropdown, không bấm "Tạo máy UGPhone"), không dùng thương mại.

---

## 📜 Changelog

### Tổng quan các phiên bản

| Version | Engine | Kiến trúc đọc | Điểm nhấn |
|---|---|---|---|
| v1.0–v2.0 | Requests/Camoufox/SeleniumBase | trang `/status_trial_ugphone` | Nền móng: relay 345p, smart restart, pytz, alert |
| v3.x | Camoufox + inject token | `/tools/buydevice_ugphone` | Chuyển trang BUY, NHUNG bệnh login-wall check + panic loop |
| v4.0 | Camoufox headful + Xvfb 1920 | goto mỗi phút | Xóa login-wall + panic. Sinh bệnh "liệt-có-tổ-chức" (kiên nhẫn vô hạn với kẹt CF) |
| v4.1–4.5 | Camoufox headful | peek + trần CF + sửa nhầm-CF-by-fetch | Grace CF, máy trạng thái, classify DOM-live (giết nhầm CF do bundle SPA) |
| v4.6–4.11 | Camoufox headful | như trên + UX | Kênh sạch (chỉ embed/ping), embed lỗi 3 dòng, owner ping vòng đời, geoip (VÔ DỤNG — log chứng minh) |
| **v5.0** | **DrissionPage / Chrome-CDP** | **peek-only (KHÔNG goto mỗi phút)** | **Đổi engine = quyết định thắng. CF tự nhả ~7s, 39–49p GREEN liền mạch. drift_test PASS+DATA** |
| v5.1–5.2 | Chrome-CDP | peek-only + goto-thừa | Sửa UNK không chụp ảnh; push ảnh debug NGAY; retry-hydrate sau goto |
| **v5.3** | **Chrome-CDP** | **peek-only + UNK recovery** | **UNK = redirect Dashboard (bằng chứng ảnh). Recovery goto ép về buydevice, bot tự cure không ping. VPS chính thức loại** |

### v5.3 — "Tự kéo về trang khi bị đá về Dashboard" (hiện tại)

**Bối cảnh / phát hiện bằng ảnh.** Log v5.0–5.2 cho thấy UNK xảy ra ở HAI trigger:
ngay sau goto-thừa (20:00, 10:58) VÀ khi ngồi im peek (18:09). Ảnh
`last_error.png` anh chủ đưa vạch trần: "trang không rõ mặt" kỳ thực là **Dashboard
gốc** (`hanaminikata.com`, "Đăng nhập để xem Dashboard") — site có anti-console/
idle-guard đá bot về nhà. Đây KHÔNG phải login wall, KHÔNG phải trang lạ.

**Thay đổi cốt lõi v5.3:**

- ♻️ **UNK recovery**: khi classify = UNK, bot **goto ép về TARGET_URL (buydevice)**
      1 lần/episode (trần `MAX_RECOVERY_GOTO`). Cure (GREEN) → lấy data, **KHÔNG
      ping chủ** (bot tự fix redirect). Không cure → UNK dai dẳng thật → ping →
      giveup. Flag `unk_recovery_done` reset khi GREEN để episode kế được recovery.
- 🧊 **Giữ peek-only + goto-thưa + retry-hydrate** của v5.0–5.2 nguyên vẹn; chỉ
      THÊM lớp recovery, không đổi luồng đọc.
- 📝 **Changelog/FAQ ghi trung thực**: UNK = redirect Dashboard (không phải login);
      CF managed-auto ~7s (không cần click/solver); VPS đã loại; câu freshness
      goto-thừa vẫn MỞ (chủ chưa chốt).

**Kết quả kỳ vọng:** idle-redirect (18:09 kiểu) được cure trong 1 phút, embed
không đỏ, chủ không bị réo. goto-redirect (20:00/10:58 kiểu) có thêm 1 cửa cứu
qua recovery. Chỉ UNK dai dẳng thật (anti-console kick cả recovery) mới ping +
nhường job sau.

### v5.0–5.2 — "Đổi engine, peek-only, bằng chứng trước lời hứa"

**Bước ngoặt của cả series.** Sau 11 phiên bản vá Camoufox mà bot vẫn kẹt CF phút
0 (job 18:24: `Mode khởi đầu: CF`, 3 lần reset context thua, chết sau 11p), chủ
repo đưa bài Gemini về DrissionPage và **bắt test nhỏ trước khi port** — đúng kỷ
luật "không đoán mò" mà em đã thề bỏ nhiều lần. `drift_test.py` chạy 1 lần qua
workflow riêng → verdict **PASS+DATA** (title thật, select FOUND, chứa Singapore,
CF tự nhả). Chỉ SAU khi có verdict em mới port v5.0.

- 🖥️ **Engine: Camoufox/Firefox → DrissionPage/Chrome-CDP.** Cùng runner, cùng
      Xvfb 1920, cùng IP — chỉ khác engine. Firefox-stealth bị CF chấm thấp;
      Chrome thật qua CDP (không `navigator.webdriver` kiểu Selenium) → CF managed-
      auto tự nhả ~7s. Log v5.0: `Mode khởi đầu: GREEN`, 39p `✅ Check (DOM)` liên
      tục, `reopen:0`, `cf-ctx:0`. Đây là lần đầu bot sống liền mạch.
- 👁️ **peek-only**: mỗi phút chỉ đọc `page.html` (DOM hydrate), KHÔNG goto. Không
      navigation = CF không cớ chèn challenge. goto chỉ còn 3 lúc có节流.
- 🐛 **v5.1 sửa bug em tự gây**: UNK không gọi `screenshot_debug` → mất bằng chứng.
      Thêm chụp ảnh vào MỌI nhánh UNK.
- 🐛 **v5.2 sửa bug commit timing**: ảnh debug chỉ push CUỐI job → chủ mở GitHub
      lúc lỗi thấy ảnh CŨ. Thêm `push_debug_shot` (throttle 60s) push NGAY khi
      chụp. + retry-hydrate sau goto-thừa để phân biệt "hydrate chậm" vs "trang lạ".

**Bài học em ghi lại (không giấu):** geoip (v4.11) là lần em ĐOÁN MÒ — thêm
`camoufox[geoip]` vì lý thuyết "fingerprint lệch IP" của bài Gemini, nhưng log
in ra `tz=UTC lang=en-US` (đã khớp IP US) → geoip không đổi 1 byte hành vi CF.
Em nhận lỗi và rút lại hướng đó. Series này thắng nhờ **bằng chứng (ảnh + log +
drift_test)**, không nhờ lời hứa "xong" của em.

### v4.0–4.11 — "Kiên nhẫn, rồi kiên nhẫn phải có lối thoát"

Chữa bệnh panic-restart của v3.x (headful + Xvfb 1920 + lỗi mềm chỉ chụp debug),
nhưng sinh bệnh "liệt-có-tổ-chức" (kiên nhẫn vô hạn với kẹt CF → fail 283p mà
`reopen:0`). v4.1 gắn trần thoát-kẹt (grace CF, mở context, nhường job sau).
v4.5 giết bệnh nhầm-CF-do-fetch (bundle SPA chứa constant "verifying..." →
classify DOM-live mới đúng). v4.6–4.11 dọn kênh Discord (chỉ embed + ping),
embed lỗi 3 dòng, owner ping vòng đời (xóa khi xanh + cooldown flap). Toàn bộ
chạy trên Camoufox/Firefox — engine cuối cùng bị chứng minh là kẹt phút 0 ở v5.0.

### v3.x — Anti-console + inject token (giai đoạn sai hướng)

Chuyển sang trang BUY, thêm chống redirect + inject `session_token`. Sai ở chỗ:
trang **không cần token**, và logic check "login wall" + panic loop chính là thứ
khiến Cloudflare khóa IP. Toàn bộ phần này bị loại ở v4.0.

### v1.x–v2.0 — Nền móng trên trang status

Relay 345 phút, smart restart, pytz đồng bộ giờ, tự chẩn đoán + alert. Đặt nền
tảng hạ tầng (Discord embed edit, ping tự xóa, force-push state) mà v5.3 vẫn dùng
nguyên.

---

## 💖 Credit

- **DrissionPage** — Engine Chrome-CDP (thứ đã cứu bot khỏi Firefox-stealth)
- **Google Chrome** — Browser thật trên runner `ubuntu-26.04`
- **Xvfb** — Display ảo để headful chạy trên GitHub Actions
- **BeautifulSoup4** — Parse HTML
- **pytz** — Đồng bộ giờ Việt Nam chính xác
- **Hanami Website** — Nền tảng dữ liệu trial UGPhone
- **Aozora Cyrus** — Chủ nhân Repository, người bắt lỗi bằng ảnh & giữ kỷ luật "test trước khi port"
- **Aozorians** — Hỗ trợ phát triển & testing

---

<div align="center>

*Made with ❤️ by Aozorians • v5.3 đã đóng băng (kèm ngoại lệ trần tự-cứu có bằng chứng) • Hỏng thật hãy report, xanh thì để yên • Mỗi dòng trong README này đều có log/ảnh làm chứng, không có lời hứa suông • Cho repo một ⭐ nếu hữu ích!*

</div>
