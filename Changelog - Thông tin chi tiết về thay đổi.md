# 📜 CHANGELOG

Tất cả những thay đổi đáng chú ý của dự án **Status Trial UGPhone Discord Bot** sẽ được ghi lại trong tài liệu này.
Hãy đọc nó trước khi fork nhé mọi người

---

## [v2.0.0] - 16/10/2026 (Phiên bản hiện tại: Trang BUY & Tự chữa lỗi)

### 🔄 Thay đổi lớn
- **Chuyển nguồn dữ liệu**: Chuyển từ `/status_trial_ugphone` (bị ẩn sau tường đăng nhập Token+OTP) sang `/tools/buydevice_ugphone` (trang mua công khai, không yêu cầu đăng nhập).
- **Logic đọc dữ liệu mới**: Triển khai cơ chế 3 bước: Click mở dropdown vùng miền → Đợi 2 giây modal render → Đọc và parse chấm màu (🟢/🔴) từ text.
- **Tự chẩn đoán (Self-Diagnosis)**: Bot tự động phân loại trạng thái trang (`ok`, `cf`, `login`, `server`, `incomplete`) để log chính xác nguyên nhân lỗi.

### 🛡️ Cải thiện độ ổn định
- **Cảnh báo sự cố (Alert System)**: Tự động gửi tin nhắn cảnh báo lên Discord nếu bot không lấy được dữ liệu liên tục trong 10 phút (và nhắc lại mỗi 60 phút), chấm dứt tình trạng "fail câm lặng".
- **Tự chữa lỗi nâng cao**: Tự động restart browser ngay sau 3 lần fail liên tiếp để làm mới phiên làm việc.

### 🐛 Sửa lỗi
- Khắc phục lỗi không tìm thấy phần tử dropdown bằng cách thử nhiều selector (`select`, `[role="combobox"]`, `.dropdown-toggle`, v.v.).

---

## [v1.5.0] - Đồng bộ thời gian & Tối ưu Log

### ⏱️ Thay đổi lớn
- **Loại bỏ hoàn toàn `time.is`**: Chuyển sang sử dụng thư viện `pytz` (Asia/Ho_Chi_Minh) để lấy giờ Việt Nam. Đảm bảo 100% chính xác, hoạt động offline, không phụ thuộc API bên thứ 3.
- **Đồng bộ khung giờ**: Log check và Footer Embed giờ dùng chung một mốc thời gian duy nhất sau khi push, loại bỏ hoàn toàn hiện tượng lệch phút (ví dụ: log 08:32 nhưng footer 08:33).

### 🧹 Tối ưu hóa
- **Giảm spam log**: Thông báo "Đang chờ Cloudflare xác minh" chỉ xuất hiện mỗi 15 giây (kèm thời gian đã chờ), thay vì 5 giây như trước.
- **Quét nhịp chính xác**: Sử dụng vòng lặp `time.sleep(0.2)` để đảm bảo bắt đúng giây `:00` của mỗi phút, không bị hụt.

---

## [v1.4.0] - Smart Restart Strategy & Tránh bị phát hiện

### 🧠 Thay đổi lớn
- **Chiến lược Restart thông minh**: 
  - **Camoufox**: KHÔNG proactive restart (chạy liên tục ~345 phút), chỉ emergency restart khi chết.
  - **SeleniumBase**: Proactive restart mỗi 120 phút để tránh tràn RAM.
  - **Emergency Restart**: Tăng thời gian chờ (3s → 15s → 30s) và tự động chuyển đổi browser (Camoufox ↔ SeleniumBase) nếu fail quá 5 lần liên tiếp.
- **Bỏ chặn ảnh (`block_images=False`)**: Cho phép browser tải ảnh để mô phỏng hành vi người dùng thật, tránh bị Cloudflare WAF phát hiện và block session sớm (vấn đề từng gây chết browser sau 9-30 phút).

### 🛠️ Sửa lỗi
- Thêm hàm `ensure_camoufox_installed()` tự động chạy `camoufox fetch` nếu thư viện chưa được cài đặt, tránh lỗi `official/stable is not installed`.
- Thêm `null-guard` cho hàm `click_refresh()` để tránh lỗi `Cannot read properties of null` khi trang đang hiển thị Cloudflare challenge.

---

## [v1.3.0] - Hệ thống Relay 24/7 trên GitHub Actions

### 🔄 Thay đổi lớn
- **Cơ chế Relay 345 phút**: Thiết lập giới hạn chạy 345 phút/job (chừa 15 phút an toàn so với giới hạn 360 phút của GitHub). Cuối chu kỳ, bot tự động force push state và dùng API để trigger job tiếp theo.
- **Xử lý xung đột Git**: Thêm cơ chế `git pull --rebase` và fallback `git push --force-with-lease` để tránh lỗi `rejected (fetch first)` khi có chỉnh sửa file trên web trong lúc job đang chạy.
- **Unbuffered Log**: Thêm `python -u` và biến môi trường `PYTHONUNBUFFERED=1` để log hiển thị tức thì trên GitHub Actions, không bị giữ trong bộ đệm.

---

## [v1.0.0] - Khởi đầu & Di chuyển khỏi Render

### 🚀 Thay đổi lớn
- **Rời bỏ Render.com**: Do IP datacenter của Render bị Cloudflare blacklist vĩnh viễn và không có quyền root để cài browser.
- **Chuyển sang GitHub Actions**: Tận dụng free tier (unlimited minutes cho Public Repo) để chạy bot.
- **Stack công nghệ ban đầu**: Python, Camoufox, SeleniumBase (UC Mode), BeautifulSoup4, Requests.
- **Tính năng cốt lõi**: Check 1 phút/lần, Edit cùng 1 Discord Embed, Ping role khi có máy và tự xóa sau 5 phút.

---

## ⚠️ Giới hạn đã biết & Kế hoạch tương lai

### Giới hạn hiện tại
- **VMOS & Vsphone**: Hiện tại các trang này đã siết chặt bảo mật, yêu cầu bắt buộc đăng nhập bằng Token + OTP. GitHub Actions (với IP thay đổi liên tục và giới hạn thời gian) không thể duy trì session ổn định cho các trang này. Bot hiện tại chỉ hoạt động ổn định cho **UGPhone** (do trang BUY vẫn công khai).

### Kế hoạch tương lai (Khi có nhu cầu mở rộng)
- **Triển khai VPS IP tĩnh**: Xây dựng kịch bản `bot_vps.py` với khả năng tự động đọc OTP từ `notevn.com`, tự điền Token, và lưu cookies bền vững (persistent profile) để duy trì đăng nhập 24/7 mà không bị đá phiên.
- **Hỗ trợ đa nền tảng**: Mở rộng logic parse cho VMOS và Vsphone khi họ nới lỏng hoặc khi giải pháp VPS được triển khai.
