# Sound-Pi

Raspberry Pi 4 + 3.5インチ SPI LCD (480x320) で動作するオーディオルーティングデバイス。
PC/Mac からの USB Audio (UAC2 ガジェット) 入力を受け取り、USB/BT 出力デバイスへルーティングする。

## 技術スタック

- **Python 3** + **pygame** (SDL_VIDEODRIVER=dummy, offscreen rendering)
- **fbdev 直接書き込み** — `/dev/fb*` mmap で ili9486 SPI LCD に描画
- **evdev** — タッチ入力 (`/dev/input/eventN`, ADS7846)
- **numpy** — FFT（スペクトラムアナライザ）
- **PipeWire** — `wpctl` (ボリューム制御)、`pw-cat` (オーディオキャプチャ)、`pw-loopback` (ルーティング)
- **libgpiod v2** (`gpiomon`/`gpioget`) — ロータリーエンコーダ読み取り
- **sysfs PWM** (`/sys/class/pwm/pwmchip0/pwm1`) — LED PWM制御（200kHz、pin13 = PWM0_1 → channel 1）
- **USB Audio Class 2 ガジェット** — dwc2 + configfs (`/sys/kernel/config/usb_gadget/sound-pi/`)
- **USB HID** — `/dev/hidg0` 経由でConsumer Control送信
- **bluetoothctl** — Bluetooth制御（subprocess）
- **nmcli** — WiFi制御（subprocess）

## オーディオパイプライン

```
PC/Mac (USB-C) → UAC2 Gadget (dwc2, S16_LE 48kHz) → PipeWire capture
    ↓ pw-loopback (自動起動)
USB/BT 出力デバイス (PipeWire sink)
    ↓ 同時に
pw-cat --record → numpy FFT → VU メーター / スペクトラム表示
```

- **ルーティング**: `PipeWireManager.start_routing()` がアプリ起動時に `pw-loopback` を自動起動
- **メータリング**: `AudioCapture` が `pw-cat` でUAC2ソースをキャプチャ、RMS/FFT計算

## 表示パイプライン

```
pygame Surface (offscreen, dummy driver)
    ↓ get_buffer().raw (BGRA)
mmap → /dev/fb* (ili9486, 480x320 32bpp)
    ↓ SPI
LCD表示
```

- X11/Xorg 不要
- HDMI 不要
- fbcp 不要

## 入力

- **タッチ**: `/dev/input/eventN` (ADS7846, evdev直読み, 0-4095 → 480x320 マッピング)
- **ロータリーエンコーダ**: libgpiod v2 `gpiomon` (CLK=19, DT=20, SW=26, pull-up)
- **USB HID出力**: `/dev/hidg0` (Play/Pause, Next, Prev)

## 画面遷移

```
起動 → VuMeter（デフォルト）
左上100x100タップ → メインメニュー（3×2タイル: VU/DualVU/Spectrum/Mixer）
右上100x100タップ → 設定メニュー（3×2タイル: System/BT/WiFi/Develop）
ロータリー回転 → VolumeOverlay（2秒後消える）
ロータリー短押し → Play/Pause (USB HID)
ロータリー長押し → Mute切替
```

## 重要な注意点

### UAC2 ガジェット
- **必ず S16_LE (16bit) を使う** — S24_3LE (24bit) は dwc2 ドライバの DMA でパケット破損が発生する
- configfs: `/sys/kernel/config/usb_gadget/sound-pi/functions/uac2.usb0/`
- `c_ssize=2` (16bit)、`c_srate=48000`、`c_chmask=3` (stereo)
- Ansible ロール: `usb-gadget` (`gadget_audio_bit_depth: 16`)

### fbdev
- fb デバイス番号は起動毎に変わりうる → `/sys/class/graphics/fb*/name` で "ili9486" を検索して特定
- Xorg が動いている場合は framebuffer を占有する → pygame アプリ使用時は Xorg を停止
- ili9486 DRM fb: 480x320, 32bpp (BGRX), stride=1920
- VTカーソル非表示: `sudo setterm --cursor off` + `cursor_blink=0` (root権限必要)

### GPIO / libgpiod v2
- pigpio は Trixie で利用不可。libgpiod v2 (gpiomon) + sysfs PWM を使う
- **libgpiod v2 の CLI 構文**: `-c gpiochip0` (`--chip` ではない)、`-e both`、`-b pull-up`、`--format "%o %e"`
- gpiomon 出力: `<offset> <edge_type>` (1=rising, 2=falling)
- gpioget 出力: `"19"=active` / `"19"=inactive`
- gpiomon がピンを占有中は gpioget で同じピンを読めない → `pin_states` dict でイベントから追跡
- LED hardware PWM: pin13 = PWM0_1 → **channel 1** (`pwm1`)、`dtoverlay=pwm,pin=13,func=4` が必要
- PWM周波数: **200kHz** (5000ns period) — 1kHz だとオーディオにノイズが乗る
- PWM export 後の udev 権限待ち: `os.access(period_path, os.W_OK)` のリトライループが必要

### SPI LCD (spi-lcd ansible ロール)
- `hdmi_ignore_hotplug:0=1`, `hdmi_ignore_hotplug:1=1` で HDMI 無効化
- `rp1-test.service` はマスクしない
- `xserver-xorg-legacy` はインストールしない

### デプロイ
- アプリは `/opt/sound-pi/` にデプロイ（git リポジトリではない）
- git branch 表示: ansible が `VERSION` ファイルを生成（`branch (short-hash)` 形式）

## Ansible ロール

| ロール | 内容 |
|--------|------|
| `usb-gadget` | UAC2 + HID ガジェット (configfs) |
| `sound-pi-pygame` | Python アプリデプロイ、venv、systemd サービス |
| `spi-lcd` | SPI LCD (ili9486) + タッチ設定 |
| `sound-pi-gpio` | GPIO dtoverlay (PWM, ロータリーエンコーダ) |

- 設定: `/home/pi/git/pi-setup/ansible/roles/`
- 仕様: `docs/ansible-roles-spec.md`

## 参考にした既存コード

| パターン | 参考元 |
|---------|--------|
| Electron実装 | `docs/electron.md` |
| BluetoothManager | `/home/pi/git/pi-obd2/electron/bluetooth/` |
| WiFiManager | `/home/pi/git/pi-obd2/electron/network/` |
| GpioManager | `/home/pi/git/pi-obd2/electron/gpio/` |
| Logger | `/home/pi/git/pi-obd2/electron/logger.ts` |
