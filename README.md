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
→ **KHÔNG.** Ảnh debug thật cho     WAIT_AFTER_GOTO_MS = 12000        # 🧊 CẤM giảm: chờ Xvfb + Turnstile tự verify
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
- **DrissionPage** — Vận hành trình duyệt website ổn định nhất
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
