# Sound-Pi

Raspberry Pi 4 + 3.5インチ SPI LCD (480x320) で動作するオーディオルーティングデバイス。
PC/Mac からの USB Audio (UAC2 ガジェット) 入力を受け取り、最大4台の USB/BT 出力デバイスへ同時ルーティングする。

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
    ↓ pw-loopback (デバイスごとに独立プロセス)
USB/BT 出力デバイス1 (PipeWire sink)
USB/BT 出力デバイス2 (PipeWire sink)  ← 最大4台同時
    ↓ 同時に
pw-cat --record → numpy FFT → VU メーター / スペクトラム表示
```

- **マルチシンクルーティング**: デバイスごとに独立した `pw-loopback` プロセスを起動
- **デバイス識別**: `node.name` で保存（USB シリアル番号含む、リブート跨ぎで安定）、ランタイムは wpctl ID
- **プロファイル自動切替**: `aplay -l` で ALSA playback デバイスを検出、PipeWire Device の `device.nick` でマッチ、Sink がなければ `wpctl set-profile <id> 1` (pro-audio) に自動切替
- **出力なし時**: OUTPUT CONTROL にデバイスがなければ `pw-loopback` を起動しない（デフォルトシンクへのフォールバックなし）
- **メータリング**: `AudioCapture` が `pw-cat` でUAC2ソースをキャプチャ、RMS/FFT計算（dBスケール）

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
ロータリー回転 → 選択デバイスの音量変更 + VolumeOverlay（デバイス未設定時はマスター音量）
ロータリー短押し → Play/Pause (USB HID)
ロータリー長押し → 選択デバイスのMute切替（デバイス未設定時はマスターMute）
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

### PipeWire マルチシンク
- **デバイス候補取得**: `aplay -l` → ALSA playback デバイス一覧（内蔵・HDMI・UAC2 は除外）
- **PipeWire Device マッチ**: `pw-cli ls Device` の `device.nick` == ALSA の long_name（`[]` 内）
- **プロファイル問題**: USB ヘッドセット等で WirePlumber が入力のみのプロファイルを選ぶことがある → `wpctl set-profile <device_id> 1` (pro-audio) で Sink を出現させる
- **`wpctl inspect` の UTF-8 問題**: pro-audio プロファイルのノードは `audio.position` に不正な UTF-8 バイトを含む → `decode("utf-8", errors="replace")` が必須
- **`pw-cli ls Node` の制限**: pro-audio プロファイルのノードは `media.class` が出力されないことがある → Sink 検索には `wpctl status` のパースを使う
- **per-sink 音量/ミュート**: `wpctl set-volume/set-mute <node_id> <value>` で個別制御

### 設定永続化 (config-persistence)
- 設定ファイル: `~/.config/sound-pi/config.json`
- overlayFS 環境では `/boot/firmware/config/save.sh --all` で FAT32 パーティションに永続化
- **即時永続化**: デバイス追加/削除時（低頻度の操作）
- **一括永続化**: アプリ終了時（音量変更等の高頻度操作分をまとめて保存）
- Ansible: `sound-pi-pygame` ロールで `save.sh` により config ファイルを登録

### デプロイ
- アプリは `/opt/sound-pi/` にデプロイ（git リポジトリではない）
- git branch 表示: ansible が `VERSION` ファイルを生成（`branch (short-hash)` 形式）
- **scp で直接デプロイ**: `scp py/<file> sound-pi:/opt/sound-pi/<file>` + `sudo systemctl restart sound-pi` で素早く反映可能

## OUTPUT CONTROL 画面 (MixerScreen)

```
┌────────────────────────────────────────────────┐
│            OUTPUT CONTROL                      │
├──────────┬──────────┬──────────┬──────────┬────┤
│  XROUND  │  B10Pro  │    +     │    +     │    │  ← 空スロットタップで追加
│  ┃████┃  │  ┃████┃  │          │          │    │
│  ┃████┃  │  ┃██  ┃  │          │          │    │  ← 縦スライダー(タッチドラッグ)
│   75%    │   50%    │          │          │    │
│   [M]    │   [M]    │          │          │    │  ← ミュートボタン
│   [×]    │   [×]    │          │          │    │  ← 削除ボタン
└──────────┴──────────┴──────────┴──────────┴────┘
```

- 4スロット固定、選択中スロットはシアン枠（ロータリーエンコーダのターゲット）
- 空スロットタップ → ALSA デバイス一覧オーバーレイ → デバイス追加
- config 保存形式: `output_devices: [{node_name, pw_device_name, volume, muted}, ...]`

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
