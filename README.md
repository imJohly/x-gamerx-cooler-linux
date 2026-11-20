# gamerx-cooler-linux

Linux driver for Power Train's **X-GamerX Z-1300** CPU cooler's 7-segment temperature display
(USB HID `5131:2007`).

## How it works

The cooler exposes a single 64-byte HID output report. **Byte 2** holds the
temperature in °C as a plain integer. Values ≥ 99 are displayed as `HI` by the
firmware. There is no readable state — the device is write-only.

The protocol was reverse-engineered interactively: sending `byte[2] = 0x0A`
showed `10`, `0x32` showed `50`, `0x63` showed `HI`, confirming numeric encoding
(no BCD, no bitmask).

## Requirements

- NixOS (or any Linux with a `/dev/hidraw*` device for `5131:2007`)
- `python3` (any recent version — the script is pure stdlib)
- udev rule for the device (see configuration.nix snippet below)

## NixOS configuration

```nix
services.udev.extraRules = ''
  KERNEL=="hidraw*", SUBSYSTEM=="hidraw", \
    ATTRS{idVendor}=="5131", ATTRS{idProduct}=="2007", \
    MODE="0660", GROUP="users"
'';

