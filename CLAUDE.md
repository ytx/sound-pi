# Sound-Pi

Raspberry Pi 4 + 3.5インチ SPI LCD (480x320) で動作するオーディオルーティングデバイス。
PC/Mac からの USB Audio 入力と本機ブラウザ音声をミキシングし、最大4台の出力デバイス（USB/BT）へルーティングする。

## 技術スタック

- **Python 3** + **pygame** (SDL_VIDEODRIVER=dummy, offscreen rendering)
- **fbdev 直接書き込み** — `/dev/fb*` mmap で ili9486 SPI LCD に描画
- **evdev** — タッチ入力 (`/dev/input/eventN`, ADS7846)
- **numpy** — FFT（スペクトラムアナライザ）
- **PipeWire** — `wpctl` / `pw-cat` コマンド経由でオーディオ制御
- **libgpiod** (`gpiomon`/`gpioget`) — ロータリーエンコーダ読み取り
- **sysfs PWM** (`/sys/class/pwm/`) — LED PWM制御（dtoverlay=pwm,pin=13,func=4 が必要）
- **bluetoothctl** — Bluetooth制御（subprocess）
- **nmcli** — WiFi制御（subprocess）
- **USB HID** — `/dev/hidg0` 経由でConsumer Control送信

> **注**: Electron 実装はペンディング。詳細は `docs/electron.md` を参照。

## 表示パイプライン

```
pygame Surface (offscreen, dummy driver)
    ↓ tobytes("BGRA")
mmap → /dev/fb* (ili9486, 480x320 32bpp)
    ↓ SPI
LCD表示
```

- X11/Xorg 不要
- HDMI 不要
- fbcp 不要

## 入力

- **タッチ**: `/dev/input/eventN` (ADS7846, evdev直読み, 0-4095 → 480x320 マッピング)
- **ロータリーエンコーダ**: libgpiod `gpiomon` (CLK=19, DT=20, SW=26)
- **USB HID出力**: `/dev/hidg0` (Play/Pause, Next, Prev)

## 画面遷移

```
起動 → VuMeter（デフォルト）
左上100x100タップ → Menu（3×2タイル） → 画面選択
ロータリー回転 → VolumeOverlay（2秒後消える）
ロータリー短押し → Play/Pause (USB HID)
ロータリー長押し → Mute切替
```

## 重要な注意点

### fbdev
- fb デバイス番号は起動毎に変わりうる → `/sys/class/graphics/fb*/name` で "ili9486" を検索して特定
- Xorg が動いている場合は framebuffer を占有する → pygame アプリ使用時は Xorg を停止
- ili9486 DRM fb: 480x320, 32bpp (BGRX), stride=1920

### GPIO
- pigpio は Trixie で利用不可。libgpiod (gpiomon) + sysfs PWM を使う
- LED hardware PWM には `dtoverlay=pwm,pin=13,func=4` が必要（sound-pi-gpio ansibleロール）

### SPI LCD (spi-lcd ansible ロール)
- `hdmi_ignore_hotplug:0=1`, `hdmi_ignore_hotplug:1=1` で HDMI 無効化
- `rp1-test.service` はマスクしない
- `xserver-xorg-legacy` はインストールしない

## Ansible ロール

- 設定: `/home/pi/git/pi-setup/ansible/roles/spi-lcd/`
- 仕様: `docs/ansible-roles-spec.md`

## 参考にした既存コード

| パターン | 参考元 |
|---------|--------|
| Electron実装 | `docs/electron.md` |
| BluetoothManager | `/home/pi/git/pi-obd2/electron/bluetooth/` |
| WiFiManager | `/home/pi/git/pi-obd2/electron/network/` |
| GpioManager | `/home/pi/git/pi-obd2/electron/gpio/` |
| Logger | `/home/pi/git/pi-obd2/electron/logger.ts` |
