<div align="center>

# 📱 STATUS TRIAL UGPHONE — DISCORD BOT

**Giám sát máy trial UGPhone 24/7 • GitHub Actions Relay • 100% miễn phí**

*Không VPS • Không Render • Không token đăng nhập • Không proxy • Không solver • Không tốn tiền*

**v5.3 — Chrome-CDP + peek-only + tự kéo về trang khi bị đá về Dashboard.**

**Trạng thái 09/11/2026:** 🟢 Đang chạy. Cloudflare managed-auto tự nhả ~7 giây. Bot peek DOM mỗi phút, không reload liên tục. Khi site đá về Dashboard, bot recovery goto về buydevice và tự xanh lại mà không ping chủ.

</div>

---

## 📖 Mục lục

- [Giới thiệu](#-giới-thiệu)
- [Yêu cầu](#️-yêu-cầu)
- [Secrets & quyền](#-secrets--quyền)
- [Cách hoạt động v5.3](#-cách-hoạt-động-v53)
- [Chính sách đóng băng](#-chính-sách-đóng-băng)
- [Cấu trúc](#-cấu-trúc)
- [Lỗi thường gặp](#️-lỗi-thường-gặp)
- [Tùy chỉnh](#️-tùy-chỉnh)
- [FAQ](#-faq)
- [Changelog](#-changelog)
- [Credit](#-credit)

---

## 🌟 Giới thiệu

Bot đọc trạng thái 5 khu vực SG / HK / JP / DE / US từ trang công khai:

`https://hanaminikata.com/tools/buydevice_ugphone`

Bốn sự thật đã được chứng minh bằng log/ảnh:

- **Không cần đăng nhập.** Chrome thường không login vẫn thấy dropdown 5 khu vực và nút “Tạo máy UGPhone”.
- **Cloudflare ở đây là managed-auto.** Trang “Verifying you are human” hiện ~7 giây rồi tự nhả, thường không có widget/checkbox để click.
- **UNK không phải login wall.** Ảnh `data/debug/last_error.png` cho thấy bot bị site đá về **Dashboard gốc** (`hanaminikata.com`, “Đăng nhập để xem Dashboard”) do anti-console/idle-guard. v5.3 chữa bằng recovery goto ép về buydevice.
- **Engine quyết định sống còn.** Camoufox/Firefox-stealth bị CF chấm thấp, kẹt phút 0. DrissionPage/Chrome-CDP dùng Chrome thật, không lộ `navigator.webdriver` kiểu Selenium, nên CF tự nhả ~7s và bot xanh liền mạch.

Tính năng chính:

- 🟢 Đọc 5 khu vực từ DOM live: 🟢 còn máy / 🔴 hết máy.
- 📊 Một embed duy nhất, edit liên tục, không spam.
- 🚨 Khi lỗi, embed đổi thành 3 dòng: `🚨 Đang gặp lỗi` / `🤔 Lí do` / `🛠️ Chúng tôi sẽ sửa`.
- 🔔 Ping role khi có máy mới, tự xóa sau 5 phút.
- 👤 Ping chủ chỉ khi lỗi nghiêm trọng dai dẳng; tin ping treo suốt lúc embed đỏ và chỉ xóa khi bot xanh lại, có cooldown 10 phút chống spam.
- 👁️ Peek-only mỗi phút: đọc DOM, không reload trang liên tục.
- 🔁 Goto có节流: chỉ khi mở job, goto-thừa chống stale mỗi 10 phút, hoặc recovery khi UNK.
- 📸 Ảnh debug được push ngay khi chụp, có thể soi lúc bot đang lỗi.
- 🔄 Relay 24/7: job 345 phút, commit state, tự kích job kế.

---

## ⚙️ Yêu cầu

| Thành phần | Bắt buộc | Ghi chú |
|---|---|---|
| GitHub repo Public | ✅ | Unlimited Actions minutes |
| Discord Webhook | ✅ | Nhận embed, role ping, owner ping |
| PAT GitHub | ✅ | Scope `repo` + `workflow` để push state và trigger relay |
| Xvfb 1920x1080 | ✅ | Phải khớp `VIEWPORT` trong code |
| Chrome runner | ✅ | Image `ubuntu-26.04` 20261101.186.1 đã có Chrome `156.0.8078.79`; workflow vẫn cài deps cho chắc |
| VPS / Render | ❌ | Đã loại: GitHub là đường chính |
| Login token / cookie | ❌ | Trang không cần đăng nhập |
| Residential proxy / CapSolver | ❌ | CF managed-auto ~7s, datacenter không phải vấn đề |

---

## 🔑 Secrets & quyền

Repo → Settings → Secrets and variables → Actions:

| Secret | Mô tả |
|---|---|
| `DISCORD_WEBHOOK_URL` | Webhook kênh Discord |
| `ROLE_PING_ID` | ID role ping khi có máy |
| `PAT` | Token classic có `repo` + `workflow` |

Quyền repo:

1. Repo phải Public.
2. Settings → Actions → General → Workflow permissions → **Read and write permissions**.

Lưu ý `OWNER_ID`:

- ID chủ để ping khi lỗi nghiêm trọng đang hard-default trong `long_runner.py`.
- **Không** đưa `OWNER_ID` vào env/secrets nếu secret có thể rỗng, vì env rỗng sẽ ghi đè default và làm ping hỏng âm thầm.
- Muốn đổi ID: sửa 1 dòng trong code, không thêm env.

---

## 🚀 Cách hoạt động v5.3

Bot mở một Chrome thật qua DrissionPage/CDP, headed trong Xvfb 1920x1080.

Mỗi phút bot peek DOM và phân loại:

    GREEN = DOM chứa "Tạo máy UGPhone"
    SRV   = DOM chứa lỗi 520/5xx của Hanami
    CF    = DOM chứa "Verifying you are human" / "Just a moment"
    UNK   = không match cả 3; thường là bị đá về Dashboard

Luồng chính:

- **GREEN:** parse 5 region từ `page.html`. Mỗi 10 phút có thể goto-thừa re-hydrate chống stale. Nếu UNK ngay sau goto, retry peek 3 lần cách 8 giây trước khi kết luận.
- **SRV:** server Hanami nghỉ. Bot chỉ chờ thụ động, không reload, không ping, vì runner/IP mới cũng gặp cùng server đó.
- **CF:** Cloudflare verify. Bot không reload. Click widget best-effort; nếu managed-auto không có widget thì chờ tự nhả. Kẹt ≥4 phút thì mở context Chrome mới, tối đa 3 lần/job. Hết trần thì ping chủ và dừng êm nhường job sau.
- **UNK:** thường là redirect về Dashboard. Bot recovery goto ép về `TARGET_URL` một lần/episode. Nếu cure → GREEN, lấy data, không ping. Nếu fail → đếm UNK, ≥8 phút thì ping chủ và dừng êm.

Kết quả mỗi phút:

- Xanh: edit embed 5 khu vực, xóa owner ping nếu có, reset recovery flag.
- Lỗi nghiêm trọng dai dẳng: edit embed đỏ 3 dòng, ping chủ một lần và treo đến khi xanh.
- CF/SRV: embed có thể đỏ nếu kéo dài, nhưng không ping chủ vì bot tự lo hoặc chờ server.

Vì sao kiến trúc này sống:

- Chrome-CDP có vân tay sạch hơn Firefox-stealth trên Cloudflare hiện tại.
- Peek-only tránh pattern “reload trang protected mỗi phút”, vốn khiến CF chèn challenge giữa job.
- Recovery UNK chữa đúng bằng chứng ảnh: bot bị đá về Dashboard, không phải bị login wall.

---

## 🧊 Chính sách đóng băng

Bot đang xanh nhờ bộ thông số hiện tại. Khi bot đang chạy tốt, **không tối ưu, không thêm tính năng, không đổi engine**.

Cấm sửa khi xanh:

- Không đổi `VIEWPORT` 1920x1080 và không đổi Xvfb screen; hai thứ phải khớp.
- Không giảm `WAIT_AFTER_GOTO_S` dưới 12. CF cần ~7s tự nhả, 12s là buffer.
- Không đổi `UI_MARKER_TEXT` trừ khi website thật sự đổi chữ “Tạo máy UGPhone”.
- Không thêm check login/token/đăng nhập. UNK là redirect Dashboard, không phải login wall.
- Không đổi engine sang Camoufox/Puppeteer/Playwright/Brave. Bài học lớn nhất: Firefox-stealth kẹt phút 0, Chrome-CDP xanh.
- Không bật `disable_coop=True`, không set window 1280x720, không override User-Agent.
- Không mua proxy dân cư, không dùng CapSolver/Anti-Captcha.

Được phép chỉnh có bằng chứng:

- Các trần tự-cứu: `CF_GRACE_MIN`, `CF_STUCK_RESTART_MIN`, `MAX_CF_RESTART`, `UNK_GIVEUP_MIN`, `MAX_RECOVERY_GOTO`, `REFRESH_EVERY_MIN`, `MAX_REAL_GOTO`, `GOTO_UNK_RETRY`.
- Chúng kích hoạt bằng log/ảnh thật, không đoán mò.
- Không đặt trần vô hạn; không đặt trần 0.

---

## 📁 Cấu trúc

    Status-Trial-UGPhone/
    ├── .github/workflows/
    │   ├── runner.yml              # Relay 345 phút, Xvfb 1920x1080x24
    │   └── drift-test.yml          # Tùy chọn: test Chrome-CDP độc lập
    ├── data/
    │   ├── message_id.txt          # ID embed Discord
    │   ├── prev_state.json         # Trạng thái cũ để phát hiện máy mới
    │   ├── owner_ping_id.txt       # ID tin ping chủ đang treo
    │   └── debug/last_error.png    # Ảnh lỗi, push ngay khi chụp
    ├── long_runner.py              # Bot v5.3
    ├── drift_test.py               # Tùy chọn: test engine
    ├── requirements.txt            # DrissionPage, bs4, requests, pytz
    └── README.md

---

## 🛠️ Lỗi thường gặp

| Hiện tượng | Nguyên nhân thật | Xử lý |
|---|---|---|
| `UNK` lặp, ảnh là Dashboard | Site đá bot về trang gốc do anti-console/idle | v5.3 recovery goto về buydevice. Nếu recovery fail ≥8 phút, nhường job sau |
| `CF` lặp giữa job kiểu bản cũ | Đang chạy nhầm engine Firefox/Camoufox | Xác nhận log có `🏁 v5.3 starting` và dùng DrissionPage/Chrome-CDP |
| `Không thấy widget Turnstile để click` | CF managed-auto không có checkbox | Bình thường. Chờ tự nhả ~7s |
| Ảnh debug trên GitHub là ảnh cũ khi đang lỗi | Job chưa commit state cuối | v5.2+ push ảnh ngay khi chụp. Kiểm tra log `📤 Đã push ảnh debug` |
| Owner ping spam nhiều tin | Dao động lỗi/xanh chớp | v5.3 dùng idempotent + cooldown 10 phút. Kiểm tra log `🧹 Đã xóa` / `⏸️ Bỏ qua ping` |
| `Xóa ping fail HTTP ...` | Webhook không đủ quyền xóa hoặc message id sai | Bot giữ id retry, không post trùng. Kiểm tra webhook |
| `libasound2 has no candidate` | Ubuntu 26.04 đổi package | Dùng `libasound2t64` |
| `libgdk-pixbuf2.0-0 has no candidate` | Package obsolete | Dùng `libgdk-pixbuf-xlib-2.0-0` |
| Push state 403 | Token Actions mặc định chỉ đọc | Dùng `PAT` và `permissions: contents: write` |
| Relay đứt | Job bị kill trước bước trigger | Bấm Run workflow thủ công để khởi động lại chuỗi |
| Footer lệch giờ | Dùng nguồn giờ ngoài | Bot dùng `pytz Asia/Ho_Chi_Minh`, lấy một mốc giờ duy nhất |

---

## ⚙️ Tùy chỉnh

Hằng số quan trọng đầu `long_runner.py`:

    TARGET_URL = "https://hanaminikata.com/tools/buydevice_ugphone"
    DURATION_MINUTES = 345
    WAIT_AFTER_GOTO_S = 12              # 🧊 không giảm
    UI_MARKER_TEXT = "Tạo máy UGPhone"  # 🧊 chỉ sửa khi web đổi thật
    VIEWPORT = {'width': 1920, 'height': 1080}  # 🧊 khớp Xvfb

    OWNER_PING_FAIL_THRESHOLD = 2
    OWNER_PING_COOLDOWN_S = 600
    PING_AUTO_DELETE = 300

    REFRESH_EVERY_MIN = 10              # goto-thừa chống stale
    MAX_REAL_GOTO = 40
    GOTO_UNK_RETRY = 3
    GOTO_UNK_RETRY_WAIT_S = 8
    MAX_RECOVERY_GOTO = 40

    CF_STUCK_RESTART_MIN = 4
    CF_GRACE_MIN = 2
    MAX_CF_RESTART = 3
    CF_RESTART_COOLDOWN_S = 30
    UNK_GIVEUP_MIN = 8
    MAX_BROWSER_REOPEN = 3
    REOPEN_COOLDOWN_S = 60

Workflow chạy bot:

    xvfb-run --server-args="-screen 0 1920x1080x24" python -u long_runner.py

---

## ❓ FAQ

**Không VPS được thật không?**  
Được. v5.3 chứng minh GitHub Actions sống: Chrome-CDP vượt CF ~7s, peek-only giữ xanh, UNK redirect có recovery tự cure. VPS đã bị loại theo quyết định chủ repo.

**UNK có phải login wall không?**  
Không. Ảnh debug cho thấy UNK là trang Dashboard gốc. Bot không cần login. Recovery goto về buydevice là fix đúng.

**Cần click Turnstile hoặc solver không?**  
Không. CF ở đây managed-auto tự nhả ~7s. Không cần CapSolver, không cần proxy.

**Peek-only có làm data stale không?**  
Câu hỏi còn mở. Nếu SPA Hanami tự poll API thì peek-only đủ. Nếu không, goto-thừa 10 phút là lưới an toàn. Người maintain nên mở web thật đối chiếu: nếu dot màu tự đổi mà bot không thấy thì giữ goto-thừa; nếu web cũng đứng im thì có thể tăng `REFRESH_EVERY_MIN` hoặc tắt goto-thừa.

**Sao kẹt CF/server nghỉ không ping chủ?**  
Vì bot tự lo được hoặc chờ server. Chỉ lỗi nghiêm trọng dai dẳng, bot bó tay, mới réo chủ.

**Sao owner ping không xóa sau 5 phút?**  
Vì nó báo tình trạng lỗi, không phải sự kiện. Nó phải treo suốt lúc embed đỏ và chỉ xóa khi bot xanh lại. Cooldown 10 phút chống spam khi bot dao động chớp.

**Repo private chạy được không?**  
Được nhưng chỉ 2.000 phút/tháng. Public mới unlimited.

---

## 📜 Changelog

| Bản | Engine | Điểm chính |
|---|---|---|
| v1–v2 | Requests/Camoufox/SeleniumBase | Nền móng: relay, embed, pytz, alert |
| v3.x | Camoufox + token | Sai hướng: tưởng login wall, panic restart |
| v4.0–4.5 | Camoufox headful | Bỏ login wall, thêm máy trạng thái, sửa nhầm CF do fetch |
| v4.6–4.11 | Camoufox headful | Kênh sạch, embed lỗi 3 dòng, owner ping vòng đời, geoip thử nhưng vô dụng |
| v5.0 | DrissionPage/Chrome-CDP | Đổi engine quyết định thắng. drift_test PASS+DATA, CF tự nhả ~7s |
| v5.1–5.2 | Chrome-CDP | Sửa UNK không chụp ảnh, push debug ngay, retry-hydrate sau goto |
| v5.3 | Chrome-CDP | UNK = redirect Dashboard. Recovery goto ép về buydevice, bot tự cure không ping |

### v5.3

- Thêm recovery UNK: khi bot bị đá về Dashboard, goto ép về buydevice một lần/episode.
- Cure được thì xanh lại, không ping chủ.
- Không cure được mới tính là lỗi nghiêm trọng dai dẳng.
- Giữ nguyên peek-only, Chrome-CDP, goto节流, push ảnh debug ngay, owner ping xóa khi xanh.

---

## 💖 Credit

- **DrissionPage + Chrome-CDP** — engine đã cứu bot khỏi Firefox-stealth.
- **Google Chrome trên GitHub runner** — browser thật, image 20261101.186.1 có Chrome 156.0.8078.79.
- **Xvfb** — display ảo cho headed Chrome trên Actions.
- **Aozora Cyrus** — chủ repo, người bắt lỗi bằng ảnh và giữ kỷ luật test trước khi port.
- **Aozorians** — hỗ trợ phát triển và testing.

---

<div align="center>

*Made with ❤️ by Aozorians • v5.3: hỏng thật hãy sửa, xanh thì để yên • Mọi dòng quan trọng đều có log/ảnh làm chứng, không hứa suông.*

</div>
