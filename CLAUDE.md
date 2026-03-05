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
- **メディアキー入力**: evdev Consumer Control / BT AVRCP (`/dev/input/eventN`) — 出力デバイスからのボタン操作受信

## 画面遷移

```
起動 → VuMeter（デフォルト）
左上100x100タップ → メインメニュー（3×2タイル: VU/DualVU/Spectrum/Mixer）
右上100x100タップ → 設定メニュー（3×2タイル: System/BT/WiFi/Develop）
ロータリー回転 → 選択デバイスの音量変更 + VolumeOverlay（デバイス未設定時はマスター音量）
ロータリー短押し → Play/Pause (USB HID)
ロータリー長押し → 選択デバイスのMute切替（デバイス未設定時はマスターMute）
出力デバイスの Play/Pause/Next/Prev → PC へ HID 転送
出力デバイスの Volume Up/Down → 該当 Mixer スロットの音量調整 (5%刻み)
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
- **デバイス候補取得**: `aplay -l` → ALSA playback デバイス一覧（内蔵・HDMI・UAC2 は除外）+ `pw-cli ls Node` → `bluez_output.*` BT シンク
- **PipeWire Device マッチ**: `pw-cli ls Device` の `device.nick` == ALSA の long_name（`[]` 内）
- **プロファイル自動選択**: ACP (ALSA Card Profiles) が USB デバイスごとに適切なプロファイルを生成。`ensure_sink_profile` で Audio/Sink を持つプロファイルを自動選択（analog-stereo 優先、pro-audio はフォールバック）
- **BT デバイスはプロファイル切替不要**: `bluez_output.*` の node_name をそのまま pw-loopback のターゲットに使う
- **`wpctl inspect` の UTF-8 問題**: pro-audio プロファイルのノードは `audio.position` に不正な UTF-8 バイトを含む → `decode("utf-8", errors="replace")` が必須
- **`pw-cli ls Node` の制限**: pro-audio プロファイルのノードは `media.class` が出力されないことがある → Sink 検索には `wpctl status` のパースを使う
- **per-sink 音量/ミュート**: `wpctl set-volume/set-mute <node_id> <value>` で個別制御
- **ノード名の変動**: ACP プロファイルにより node_name が変わる（例: `pro-output-0` ↔ `analog-stereo`）。config には `pw_device_name`（安定）も保存し、node_name が見つからない場合はデバイス名からフォールバック解決
- **`remove_route` のキー不一致対策**: `_loopback_procs` のキーと node_name が一致しない場合（プロファイル切替でノード名変動）、`proc.args` から `-P` ターゲットを検索してマッチ
- **`start_routing` 2パス方式**: (1) 全ノード名解決＋プロファイル切替 → 1秒待機 → (2) pw-loopback 一斉起動。プロファイル切替直後は PipeWire がシンクを初期化中のため待機が必要
- **BT sink の `start_routing`**: `bluez_output.*` はプロファイル解決をスキップし、そのまま loopback 起動

### PipeWire 設定の注意点（重要）
- **`default.clock.allowed-rates`**: `[ 44100 48000 96000 ]` を設定済み（`10-sound-pi.conf`）。B10Pro は 96kHz 対応
- **`api.alsa.use-acp=false` は絶対に使わない** — audioconvert が `audio.channels=64` を返すバグ＋ ALSA デバイスロック (-EBUSY) が発生。WirePlumber の `50-usb-audio.conf` は Ansible で明示削除している
- **B10Pro は S24_3LE のみ対応** — S16_LE では ALSA デバイスを開けない（`hw:B10Pro` で "Invalid argument"）。PipeWire/pw-loopback 経由なら自動変換される。`plughw:` も使える

### B10Pro 既知の問題（未解決）
- **詳細**: `b10pro.txt` を参照
- **リブート後**: WirePlumber が毎回 `input:mono-fallback` を選択（Sink なし）
- **アプリの `ensure_sink_profile`** が pro-audio (index 1) に切り替えるが、pro-audio の Sink は `audio.channels=0`、EnumFormat 空で壊れている
- **セッション中の手動操作**（プロファイル切替、WirePlumber 再起動等）を繰り返すと `analog-stereo` プロファイルが出現して動作するが、どの操作が決め手かは未特定
- **EnumProfile**: off(0), pro-audio(1), input:mono-fallback(2) の3つのみ。`analog-stereo` は EnumProfile に存在しないが、特定条件下で出現する

### メディアキー入力 (MediaInputManager)
- **`py/managers/media_input.py`**: evdev Consumer Control / BT AVRCP デバイスからのメディアキー受信
- **デバイス検出**: `/proc/bus/input/devices` をパース、"Consumer Control" または "(AVRCP)" を含むデバイスを検出（ADS7846 は除外）
- **EVIOCGRAB**: デバイスを排他取得 — WirePlumber が同じイベントを処理して音量を二重変更するのを防止
- **デバウンス**: 同一デバイス・同一キーの連打を 300ms 間隔でデバウンス（B10Pro は1回の押下で value=1 イベントを複数回送信する）
- **インクリメンタル rescan**: 10秒間隔で新規デバイスのみ追加（既存 fd は維持）。全 close→reopen するとイベント消失する
- **デバイス → Mixer スロットのマッチング**:
  - USB: evdev の `Uniq`（シリアル番号）が `pw_device_name` に含まれるか
  - BT: `bluez_output.XX_XX_XX_XX_XX_XX` からBTアドレスを抽出し、evdev の `Name` / `Uniq` とマッチ
- **イベント処理**: Play/Pause/Next/Prev → `/dev/hidg0` で PC へ転送、Volume Up/Down → 該当スロットの音量 ±5%

### USB HID ガジェット (`/dev/hidg0`)
- **レポートディスクリプタ**: 1バイトのビットフィールド（bit0=Play/Pause, bit1=Next, bit2=Prev）
- **絶対に 2バイトの Usage ID (`0xCD00` 等) を送らない** — ビットフィールドなので `0xCD` は複数ビットがセットされ、Play/Pause と Prev が同時送信される
- **正しいレポート値**: Play/Pause=`0x01`, Next=`0x02`, Prev=`0x04`, Release=`0x00`
- **O_NONBLOCK + EAGAIN リトライ**: PC がレポートを読み切るまで write が EAGAIN を返す → 5ms 間隔で最大3回リトライ
- **パーミッション**: デフォルト `crw------- root:root` → `usb-gadget-setup.sh` で `chmod 666` を実行

### WirePlumber default-routes
- **起動時クリア**: `~/.local/state/wireplumber/default-routes` をアプリ起動時に truncate（`start_routing()` の前）
- WirePlumber が古いルート情報をキャッシュし、リブート後に不正なプロファイル（`input:mono-fallback` 等）を選択する問題への対策
- overlay FS 環境でも Ansible デプロイ中に WirePlumber が動作していると stale なエントリが残る

### pw-loopback 音量バースト防止
- **問題**: `pw-loopback` 起動直後は PipeWire デフォルト (100%) で音が流れ、その後の `set_sink_volume` まで最大音量になる
- **対策**: `_apply_sink_volume()` で loopback 起動直後に即座に音量設定。wpctl_id が resolve されるまで 200ms 間隔で最大5回リトライ
- `start_routing()` / `add_route()` 両方で loopback 起動と音量設定をセットで実行

### 設定永続化 (config-persistence)
- 設定ファイル: `~/.config/sound-pi/config.json`
- overlayFS 環境では `sudo /boot/firmware/config/save.sh --all` で FAT32 パーティションに永続化
- **`save.sh` は sudo 必須** — root 権限がないとマウント操作が失敗する
- **即時永続化**: デバイス追加/削除時（低頻度の操作）
- **一括永続化**: アプリ終了時（音量変更等の高頻度操作分をまとめて保存）
- Ansible: `sound-pi-pygame` ロールで `save.sh` により config ファイルを登録

### デプロイ
- アプリは `/opt/sound-pi/` にデプロイ（git リポジトリではない）
- git branch 表示: ansible が `VERSION` ファイルを生成（`branch (short-hash)` 形式）
- **Ansible デプロイはユーザーが実行する** — Claude が `ansible-playbook` を実行してはいけない
- **overlay FS**: sound-pi は overlay ファイルシステムを使用。デバイス上の直接変更はリブートで消える。すべての永続設定は Ansible ロールで管理すること
- **scp で直接デプロイ**: `scp py/<file> sound-pi:/opt/sound-pi/<file>` + `sudo systemctl restart sound-pi` で素早く反映可能（テスト用、overlay なのでリブートで消える）

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
- 空スロットタップ → デバイス一覧オーバーレイ（ALSA + BT）→ デバイス追加
- config 保存形式: `output_devices: [{node_name, pw_device_name, card_name, nick, volume, muted}, ...]`

## Bluetooth 設定画面 (BluetoothSettingsScreen)

- **BluetoothManager** (`py/managers/bluetooth.py`): `bluetoothctl` ラッパー
  - エージェント: `NoInputNoOutput`（オーディオデバイスは PIN 不要）
  - スキャン: `bluetoothctl` を interactive mode で Popen、`scan on` → 15秒 → `scan off`
  - スキャン中 2秒ごとにデバイスリスト更新
  - 操作（pair/connect/disconnect/remove）は同期、呼び出し側がスレッドで実行
  - stub モード: `bluetoothctl` 未検出時は空リスト返却（開発機対応）
- **画面レイアウト**: Paired セクション（connected 優先）→ Discovered セクション
  - Scan ボタン: y=104（メニュー領域 y=0〜100 の外に配置）
  - デバイス名があるものを優先表示（MACアドレスだけのデバイスは後ろ）
  - ボタン: Connected→"Discon"(RED), Paired→"Connect"(CYAN), Found→"Pair"(BLUE)
  - Paired + 未接続: 削除ボタン "×"
  - Pair 成功後は自動 connect
- **BT デバイスの OUTPUT CONTROL 連携**:
  - `list_addable_devices()` が `bluez_output.*` の PipeWire sink も返す
  - BT sink は `is_bluez=True` フラグ付き → Mixer で `ensure_sink_profile` をスキップ
  - BT sink は PipeWire 接続後に遅れて出現することがある → wpctl_id=None でも offline にせず nick を表示

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
