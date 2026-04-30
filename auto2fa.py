#!/usr/bin/env python3
"""Auto-enter TOTP for IB Gateway 2FA - handles device selection + code entry."""
import subprocess, time, sys, os

os.environ["DISPLAY"] = ":1"
TOTP_SECRET = "3LIWICNOAIU3D6WOL3627WN3A3HGDEBP"


def get_totp():
    import pyotp
    return pyotp.TOTP(TOTP_SECRET).now()


def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r


def find_window(title):
    r = run('xdotool search --name "' + title + '" 2>/dev/null')
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().split("\n")[0]
    return None


def get_window_geometry(wid):
    r = run("xdotool getwindowgeometry --shell " + wid)
    if r.returncode != 0:
        return None
    geo = {}
    for line in r.stdout.strip().split("\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            geo[k] = int(v)
    return geo


def screenshot(name):
    run("scrot /tmp/ibgw_%s.png" % name)
    print("[2FA-bot] Screenshot saved: /tmp/ibgw_%s.png" % name, flush=True)


def wait_for_fresh_totp_window(used_codes):
    """Wait for a TOTP code that hasn't been used yet with plenty of time remaining."""
    while True:
        remaining = 30 - (int(time.time()) % 30)
        code = get_totp()
        if code not in used_codes and remaining >= 15:
            print("[2FA-bot] Fresh code %s with %ds remaining" % (code, remaining), flush=True)
            return code
        wait = remaining + 1
        print("[2FA-bot] Waiting %ds for unused TOTP window (remaining=%ds, code=%s used=%s)..." % (
            wait, remaining, code, code in used_codes), flush=True)
        time.sleep(wait)


def main():
    print("[2FA-bot] Started. Watching for 2FA dialog...", flush=True)

    for i in range(120):
        wid = find_window("Second Factor Authentication")
        if wid:
            break
        time.sleep(1)
    else:
        print("[2FA-bot] Timeout waiting for 2FA dialog", flush=True)
        return 1

    print("[2FA-bot] Found 2FA dialog (wid=%s)" % wid, flush=True)
    time.sleep(2)
    screenshot("step1_dialog_found")

    geo = get_window_geometry(wid)
    if not geo:
        print("[2FA-bot] Can't get window geometry", flush=True)
        return 1

    wx, wy = geo.get("X", 0), geo.get("Y", 0)
    ww, wh = geo.get("WIDTH", 300), geo.get("HEIGHT", 200)
    print("[2FA-bot] Dialog geometry: x=%d y=%d w=%d h=%d" % (wx, wy, ww, wh), flush=True)

    # Wait for IBC to select the device (it should do this within 3-5s)
    print("[2FA-bot] Waiting 5s for IBC device selection...", flush=True)
    time.sleep(5)
    screenshot("step2_after_device_select")

    # Re-check window - it may have changed
    wid = find_window("Second Factor Authentication")
    if not wid:
        print("[2FA-bot] 2FA dialog gone after device selection - may have succeeded", flush=True)
        return 0

    geo = get_window_geometry(wid)
    if geo:
        wx, wy = geo.get("X", 0), geo.get("Y", 0)
        ww, wh = geo.get("WIDTH", 300), geo.get("HEIGHT", 200)
        print("[2FA-bot] Updated geometry: x=%d y=%d w=%d h=%d" % (wx, wy, ww, wh), flush=True)

    used_codes = set()

    for attempt in range(3):
        wid = find_window("Second Factor Authentication")
        if not wid:
            print("[2FA-bot] 2FA dialog gone - Success!", flush=True)
            return 0

        # Focus the window
        run("xdotool windowfocus --sync %s windowactivate %s" % (wid, wid))
        time.sleep(0.3)

        # Click on text input field (center-x, 35% height)
        field_x = wx + ww // 2
        field_y = wy + int(wh * 0.35)
        print("[2FA-bot] Clicking field at %d,%d" % (field_x, field_y), flush=True)
        run("xte 'mousemove %d %d' 'mouseclick 1'" % (field_x, field_y))
        time.sleep(0.3)

        # Select all text and delete
        run("xte 'keydown Control_L' 'key a' 'keyup Control_L'")
        time.sleep(0.1)
        run("xte 'key Delete'")
        time.sleep(0.2)

        # Wait for a fresh, unused TOTP code with plenty of time
        code = wait_for_fresh_totp_window(used_codes)
        used_codes.add(code)
        remaining = 30 - (int(time.time()) % 30)
        print("[2FA-bot] Attempt %d: TOTP=%s remaining=%ds" % (attempt + 1, code, remaining), flush=True)

        # Type each digit individually for reliability
        for ch in code:
            run("xte 'key %s'" % ch)
            time.sleep(0.05)
        time.sleep(0.3)

        screenshot("step3_code_entered_%d" % (attempt + 1))

        # Click OK button (35% from left, 82% height)
        ok_x = wx + int(ww * 0.35)
        ok_y = wy + int(wh * 0.82)
        print("[2FA-bot] Clicking OK at %d,%d" % (ok_x, ok_y), flush=True)
        run("xte 'mousemove %d %d' 'mouseclick 1'" % (ok_x, ok_y))

        # Wait and check result
        print("[2FA-bot] Waiting 20s for result...", flush=True)
        time.sleep(20)

        screenshot("step4_result_%d" % (attempt + 1))

        wid2 = find_window("Second Factor Authentication")
        if not wid2:
            # Check if login succeeded or error appeared
            err_wid = find_window("Gateway")
            if err_wid:
                print("[2FA-bot] Gateway error dialog appeared - code rejected", flush=True)
                # Click OK on the error dialog to dismiss it
                err_geo = get_window_geometry(err_wid)
                if err_geo:
                    ex, ey = err_geo.get("X", 0), err_geo.get("Y", 0)
                    ew, eh = err_geo.get("WIDTH", 300), err_geo.get("HEIGHT", 200)
                    run("xte 'mousemove %d %d' 'mouseclick 1'" % (ex + ew // 2, ey + int(eh * 0.75)))
                    time.sleep(2)
                # The login will restart, wait for new 2FA dialog
                print("[2FA-bot] Waiting for new 2FA dialog...", flush=True)
                for i in range(60):
                    wid = find_window("Second Factor Authentication")
                    if wid:
                        geo = get_window_geometry(wid)
                        if geo:
                            wx, wy = geo.get("X", 0), geo.get("Y", 0)
                            ww, wh = geo.get("WIDTH", 300), geo.get("HEIGHT", 200)
                        time.sleep(5)
                        screenshot("step5_new_dialog_%d" % (attempt + 1))
                        break
                    time.sleep(1)
                else:
                    print("[2FA-bot] No new 2FA dialog appeared", flush=True)
                    return 1
                continue
            else:
                print("[2FA-bot] 2FA completed successfully!", flush=True)
                return 0

        print("[2FA-bot] 2FA dialog still showing, retry...", flush=True)
        time.sleep(3)

    print("[2FA-bot] Failed after all attempts", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
