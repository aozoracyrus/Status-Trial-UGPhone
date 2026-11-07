import sys
from DrissionPage import ChromiumPage, ChromiumOptions

TARGET_URL = "https://hanaminikata.com/tools/buydevice_ugphone"
UI_MARKER = "Tạo máy UGPhone"
CF_MARKERS = ("verifying you are human", "just a moment", "checking your browser")

def main():
    opt = ChromiumOptions()
    # headed -> cần Xvfb (workflow wrap sẵn). KHÔNG override UA: để Chrome thật tự khai UA đúng version.
    opt.set_argument('--no-sandbox')            # bắt buộc trong container GitHub
    opt.set_argument('--disable-dev-shm-usage') # /dev/shm nhỏ trên runner
    opt.set_argument('--disable-gpu')           # Xvfb không GPU thật -> tránh crash (software render)
    # Nếu DrissionPage không tự dò thấy Chrome, bỏ comment dòng dưới:
    # opt.set_browser_path('/usr/bin/google-chrome-stable')

    print(f"[+] Khởi động Chrome thật qua CDP (headed)...")
    page = ChromiumPage(opt)
    verdict = "OTHER"
    try:
        print(f"[+] goto: {TARGET_URL}")
        page.get(TARGET_URL)
        print("[*] chờ 12s cho Cloudflare tự verify (giống WAIT_AFTER_GOTO_MS)...")
        page.wait(12)

        title = page.title or ""
        html = (page.html or "").lower()
        print(f"[*] title = {title!r}")

        try:
            page.get_screenshot(path="drift_test.png")
            print("[*] đã chụp drift_test.png")
        except Exception as e:
            print(f"[!] chụp screenshot lỗi: {e}")

        if UI_MARKER.lower() in html:
            verdict = "PASS"
        elif any(m in html for m in CF_MARKERS):
            verdict = "CF-STUCK"
        else:
            verdict = "OTHER"

        # Nếu PASS, chứng minh đọc được data (không chỉ thấy text)
        if verdict == "PASS":
            sel = page.ele('tag:select', timeout=3)
            txt = page.html or ""
            has_sg = "Singapore" in txt
            print(f"[*] select element = {'FOUND' if sel else 'NONE'} | chứa 'Singapore' = {has_sg}")
            verdict = "PASS+DATA" if (sel or has_sg) else "PASS-NO-DATA"

    except Exception as e:
        print(f"[!] EXCEPTION: {e}")
        verdict = "ERROR"
    finally:
        try: page.quit()
        except Exception: pass

    print("=" * 50)
    print(f"KẾT LUẬN DRIFT TEST: {verdict}")
    print("  PASS+DATA  -> Chrome+CDP vượt CF VÀ đọc được dropdown => PORT sang v5.0")
    print("  PASS-NO-DATA -> vượt CF nhưng chưa đọc data => xem screenshot, chỉnh selector")
    print("  CF-STUCK   -> CF siết cả Chrome+CDP => GitHub hết cửa, tính VPS")
    print("  OTHER/ERROR-> trang lạ/lỗi => xem screenshot + log")
    print("=" * 50)
    sys.exit(0 if verdict.startswith("PASS") else 1)

if __name__ == "__main__":
    main()
