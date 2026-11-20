#!/usr/bin/env python3
"""Power Train X-GamerX Z-1300 CPU cooler 7-segment display driver (5131:2007).

Writes CPU temperature in °C to byte 2 of a 64-byte HID output report.
Values >= 99 are displayed as "HI" by the cooler's firmware.
Pure stdlib — no hidapi, no psutil.
"""
import argparse
import glob
import os
import signal
import sys
import time

VID, PID   = 0x5131, 0x2007
TEMP_BYTE  = 2
HWMON_PREF = ("k10temp", "zenpower", "coretemp", "cpu_thermal")

_running = True

def _sigterm(*_):
    global _running
    _running = False

def find_hidraw():
    """Locate /dev/hidrawN matching VID:PID by reading sysfs uevents."""
    for d in glob.glob("/sys/class/hidraw/hidraw*"):
        try:
            with open(os.path.join(d, "device", "uevent")) as f:
                for line in f:
                    if not line.startswith("HID_ID="):
                        continue
                    parts = line.split("=", 1)[1].strip().split(":")
                    if len(parts) != 3:
                        break
                    try:
                        v, p = int(parts[1], 16), int(parts[2], 16)
                    except ValueError:
                        break
                    if v == VID and p == PID:
                        return "/dev/" + os.path.basename(d)
                    break
        except OSError:
            continue
    return None

def _hwmon_temp(hwmon_dir):
    """Return the best temperature from a hwmon dir, or None."""
    best = None
    for inp in sorted(glob.glob(os.path.join(hwmon_dir, "temp*_input"))):
        try:
            with open(inp) as f:
                val = int(f.read().strip()) // 1000
        except (OSError, ValueError):
            continue
        label = ""
        try:
            with open(inp[:-len("_input")] + "_label") as f:
                label = f.read().strip().lower()
        except OSError:
            pass
        if label in ("tctl", "tdie", "package"):
            return val
        if best is None:
            best = val
    return best

def read_cpu_temp():
    """Return CPU temperature in °C, or None if no sensor is found."""
    for name in HWMON_PREF:
        for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
            try:
                with open(os.path.join(hwmon, "name")) as f:
                    if f.read().strip() != name:
                        continue
            except OSError:
                continue
            t = _hwmon_temp(hwmon)
            if t is not None:
                return t
    # Fallback: any hwmon whose name looks CPU-ish
    for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            with open(os.path.join(hwmon, "name")) as f:
                name = f.read().strip().lower()
        except OSError:
            continue
        if any(k in name for k in ("cpu", "core", "pkg")):
            t = _hwmon_temp(hwmon)
            if t is not None:
                return t
    return None

def wait_for_device(timeout):
    deadline = time.time() + timeout
    announced = False
    while _running and time.time() < deadline:
        path = find_hidraw()
        if path:
            return path
        if not announced:
            print(f"waiting for {VID:04x}:{PID:04x}…", file=sys.stderr, flush=True)
            announced = True
        sl = min(time.time() + 0.5, deadline)
        while _running and time.time() < sl:
            time.sleep(0.1)
    raise RuntimeError(f"device not found within {timeout:.0f}s")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout",  type=float, default=10.0,
                    help="seconds to wait for the device on startup (default 10)")
    ap.add_argument("--interval", type=float, default=1.0,
                    help="seconds between updates (default 1.0)")
    args = ap.parse_args()

    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT,  _sigterm)

    try:
        path = wait_for_device(args.timeout)
    except KeyboardInterrupt:
        return 130
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"Opened {path}", flush=True)

    fd = None
    last = None
    try:
        while _running:
            if fd is None:
                path = find_hidraw()
                if path is None:
                    time.sleep(1.0)
                    continue
                try:
                    fd = os.open(path, os.O_RDWR)
                    print(f"connected to {path}", flush=True)
                except OSError as e:
                    print(f"open failed: {e}", file=sys.stderr, flush=True)
                    time.sleep(1.0)
                    continue

            temp = read_cpu_temp()
            if temp is None:
                print("WARN: no CPU temperature sensor found",
                      file=sys.stderr, flush=True)
            else:
                payload = min(max(temp, 0), 99)   # 99+ → "HI" on the display
                pkt = bytes([0x00] * TEMP_BYTE + [payload] + [0x00] * (63 - TEMP_BYTE))
                try:
                    os.write(fd, pkt)
                    if temp != last:
                        print(f"temp={temp}°C  byte[{TEMP_BYTE}]=0x{payload:02x}",
                              flush=True)
                        last = temp
                except OSError as e:
                    print(f"write failed: {e}; reconnecting…",
                          file=sys.stderr, flush=True)
                    try: os.close(fd)
                    except Exception: pass
                    fd = None
                    time.sleep(2.0)
                    continue

            deadline = time.time() + args.interval
            while _running and time.time() < deadline:
                time.sleep(0.1)
    finally:
        if fd is not None:
            try: os.write(fd, bytes([0x00] * 64))
            except Exception: pass
            try: os.close(fd)
            except Exception: pass
        print("shut down cleanly", flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
