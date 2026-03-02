# Sound-Pi Ansible ロール仕様

## 概要

Sound-Pi デバイスのセットアップに必要な Ansible ロールの仕様。
既存ロール（sonix-kiosk 等）を再利用しつつ、新規ロールを追加する。

## Playbook 構成

```yaml
# ansible/sound-pi.yml
---
- name: Setup Sound-Pi
  hosts: sound-pi
  become: yes
  gather_facts: yes

  roles:
    - overlay-disable
    - apt-upgrade
    - disable-cloud-init
    - role: disable-services
      vars:
        services_to_disable:
          - cups
          - cups-browsed
          - nfs-blkmap
          - rpcbind
          - apt-daily.timer
          - apt-daily-upgrade.timer
          - udisks2
    - config-persistence
    - usb-gadget          # 新規: USB Composite Gadget (UAC2 + HID)
    - pipewire            # 新規: PipeWire + WirePlumber
    - bluetooth-audio     # 新規: Bluetooth A2DP (PipeWire連携)
    - spi-lcd             # 新規: SPI LCD (ILI9486) + XPT2046 タッチ + fbcp
    - sound-pi-kiosk      # 新規: Electronアプリ kiosk (sonix-kiosk ベース)
    - sound-pi-gpio       # 新規: ロータリーエンコーダ + LED

  post_tasks:
    - name: Enable overlay filesystem
      include_role:
        name: overlay-enable
```

## inventory.yml 追加分

```yaml
    sound-pi:
      hosts:
        pi-sound0:
          ansible_host: pi-sound0

          # spi-lcd
          spi_lcd_driver: "ili9486"
          spi_lcd_overlay: "piscreen"
          spi_lcd_width: 480
          spi_lcd_height: 320
          spi_lcd_rotate: 270
          spi_lcd_fps: 30
          spi_lcd_speed: 24000000
          spi_lcd_touch_enabled: true
          spi_lcd_touch_penirq: 25
          spi_lcd_touch_calibration_matrix: ""  # キャリブレーション後に設定

          # usb-gadget
          gadget_name: "Sound-Pi"
          gadget_manufacturer: "Sound-Pi"
          gadget_serial: "0001"
          gadget_audio_sample_rate: 48000
          gadget_audio_bit_depth: 24
          gadget_audio_channels: 2

          # sound-pi-kiosk
          sound_pi_app_src: "../../sound-pi/release/linux-arm64-unpacked"

          # sound-pi-gpio
          rotary_clk_pin: 19
          rotary_dt_pin: 20
          rotary_sw_pin: 26
          led_pin: 13
```

---

## 新規ロール仕様

---

### 1. usb-gadget

USB Composite Gadget（UAC2 + HID Consumer Control）の設定。
Pi 4 の USB-C ポートを USB Audio デバイス兼メディアコントローラーとして構成する。

**対応環境:**
- Raspberry Pi 4 Model B
- Raspberry Pi OS (64-bit)
- 電源は GPIO ピンヘッダ（Pin4: 5V, Pin6: GND）から供給

**変数:**
| 変数 | デフォルト値 | 説明 |
|------|-------------|------|
| `gadget_name` | `"Sound-Pi"` | USBデバイス名 |
| `gadget_manufacturer` | `"Sound-Pi"` | USBメーカー名 |
| `gadget_serial` | `"0001"` | USBシリアル番号 |
| `gadget_vendor_id` | `"0x1d6b"` | USB Vendor ID (Linux Foundation) |
| `gadget_product_id` | `"0x0104"` | USB Product ID |
| `gadget_audio_sample_rate` | `48000` | サンプルレート (Hz) |
| `gadget_audio_bit_depth` | `24` | ビット深度 |
| `gadget_audio_channels` | `2` | チャンネル数 |

**処理内容:**
1. `dwc2` dtoverlay を config.txt に追加（`dr_mode=peripheral`）
2. `dwc2`, `libcomposite` カーネルモジュールの自動読み込み設定
3. configfs で USB Composite Gadget を構成するスクリプトの配置
   - Function 1: UAC2 (USB Audio Class 2) — Sink (PC→Pi)
   - Function 2: HID Consumer Control — Play/Pause, Next, Previous
4. systemd service の配置（起動時にGadgetを構成）

**configfs 構成:**
```
/sys/kernel/config/usb_gadget/sound-pi/
├── idVendor, idProduct
├── strings/0x409/
│   ├── manufacturer, product, serialnumber
├── configs/c.1/
│   ├── strings/0x409/configuration
│   ├── uac2.usb0 → functions/uac2.usb0
│   └── hid.usb0 → functions/hid.usb0
├── functions/
│   ├── uac2.usb0/
│   │   ├── c_srate (48000)
│   │   ├── c_ssize (3 = 24bit)
│   │   ├── c_chmask (3 = stereo)
│   │   ├── p_srate (0 = capture無効)
│   │   └── ...
│   └── hid.usb0/
│       ├── protocol (1)
│       ├── subclass (1)
│       ├── report_length (1)
│       └── report_desc (Consumer Control descriptor)
└── UDC (bind to controller)
```

**HID Report Descriptor:**
Consumer Control Page (Usage Page 0x0C):
- Play/Pause (Usage 0xCD)
- Next Track (Usage 0xB5)
- Previous Track (Usage 0xB6)

**テンプレート:**
- `usb-gadget-setup.sh.j2` — configfs 構成スクリプト
- `usb-gadget.service.j2` — systemd unit file

**注意事項:**
- Pi 4B の USB-C ポートは `dwc2` コントローラーを使用
- `dr_mode=peripheral` に設定すると USB-C からの給電は不可
- 電源は GPIO Pin4 (5V) / Pin6 (GND) から外部供給が必須
- `otg_mode=1`（CM4用）が既存 config.txt にある場合は競合に注意

---

### 2. pipewire

PipeWire + WirePlumber のインストールと設定。
USB Gadget からの音声入力を複数の出力デバイスへルーティングする。

**対応環境:**
- Raspberry Pi 4 Model B (1GB)
- Raspberry Pi OS (64-bit)

**変数:**
| 変数 | デフォルト値 | 説明 |
|------|-------------|------|
| `pipewire_user` | `"pi"` | PipeWire を実行するユーザー |
| `pipewire_default_sample_rate` | `48000` | デフォルトサンプルレート |
| `pipewire_default_sample_format` | `"S24LE"` | デフォルトサンプル形式 |
| `pipewire_buffer_size` | `1024` | バッファサイズ（フレーム数） |

**処理内容:**
1. PulseAudio の無効化・削除（競合防止）
2. PipeWire パッケージのインストール
   - `pipewire`
   - `pipewire-pulse` (PulseAudio互換)
   - `pipewire-alsa` (ALSA互換)
   - `wireplumber` (セッションマネージャ)
3. PipeWire ユーザーサービスの有効化
   - `pipewire.service`
   - `pipewire-pulse.service`
   - `wireplumber.service`
4. PipeWire 設定ファイルの配置
   - デフォルトサンプルレート・バッファサイズ
5. WirePlumber ルーティングルールの配置
   - USB Gadget Capture → デフォルト入力ソース
   - 出力デバイスの自動検出・接続
6. loopback モジュール設定（入力→出力のルーティング）

**設定ファイル:**
```
~/.config/pipewire/
├── pipewire.conf.d/
│   └── 10-sound-pi.conf        # サンプルレート、バッファ設定
└── wireplumber.conf.d/         # WIP: Electron から動的制御する部分が多い
```

**PipeWire オーディオグラフ:**
```
  USB Gadget (UAC2 Capture) ─┐
                              ├─► [Loopback/Mixer] ─► Output Device 1
  Electron (Chromium Audio) ──┘                    ─► Output Device 2
                                                   ─► Output Device 3
                                                   ─► Output Device 4
```

**注意事項:**
- Pi OS Bookworm では PipeWire はリポジトリから利用可能
- PulseAudio と共存不可。完全に置き換える
- Electron (Chromium) は PipeWire を自動検出して使用する
- 出力先の動的な追加・削除は Electron アプリから `pw-cli` / `wpctl` で制御
- 1GB RAM の Pi 4 ではメモリ使用量に注意

---

### 3. bluetooth-audio

Bluetooth A2DP Sink（出力）の設定。PipeWire と連携して BT スピーカー/ヘッドホンへ出力する。

**対応環境:**
- Raspberry Pi 4 Model B（内蔵Bluetooth 5.0）
- Raspberry Pi OS (64-bit)

**変数:**
| 変数 | デフォルト値 | 説明 |
|------|-------------|------|
| `bt_auto_power_on` | `true` | 起動時に BT を自動 ON |
| `bt_discoverable_timeout` | `0` | 探索可能タイムアウト（0=無制限、ペアリング時のみ使用） |
| `bt_keepalive_enabled` | `true` | BT キープアライブ有効化 |
| `bt_keepalive_interval` | `30` | キープアライブ間隔（秒） |

**処理内容:**
1. Bluetooth 関連パッケージのインストール
   - `bluez` (Bluetoothスタック)
   - `bluez-tools`
2. Bluetooth サービスの有効化・設定
   - `bluetooth.service` 有効化
   - `/etc/bluetooth/main.conf` の設定
     - `AutoEnable=true`
     - `FastConnectable=true`
3. PipeWire Bluetooth モジュールの設定
   - `pipewire-module-bluetooth` の有効化（WirePlumber 経由）
   - A2DP コーデック設定（SBC, AAC, aptX 等、デバイス対応に応じて自動選択）
4. BT キープアライブ用 systemd service の配置
   - 接続済み A2DP デバイスに対して無音データを定期送信
   - PipeWire の null sink を利用
5. D-Bus 権限設定（Electron アプリから bluetoothctl を使用するため）

**キープアライブの仕組み:**
```
systemd timer (30秒間隔)
  → スクリプト実行
    → 接続済みBTデバイスの確認
    → 音声出力がない場合、無音データを短時間送信
    → BT接続がタイムアウトで切断されるのを防止
```

**テンプレート:**
- `bt-keepalive.sh.j2` — キープアライブスクリプト
- `bt-keepalive.service.j2` — systemd service
- `bt-keepalive.timer.j2` — systemd timer
- `main.conf.j2` — Bluetooth 設定

**注意事項:**
- Pi 4 内蔵 BT は同時 A2DP 接続数に制限あり（通常 1-2 台）
- 3台以上同時接続する場合は外付け BT アダプタが必要な可能性
- ペアリング・接続操作は Electron アプリの UI から実施（D-Bus 経由）
- bluetooth.service は disable-services ロールで無効化しない

---

### 4. spi-lcd

SPI 接続 LCD ディスプレイ（ILI9486）と XPT2046 タッチコントローラーの設定。
Trixie の `piscreen` dtoverlay は DRM ドライバ (`ili9486`) として動作し、
`/dev/dri/card1` に独立した DRM デバイスを作成する。
fbcp は不要（DRM ドライバが直接 SPI LCD を駆動する）。

**対応ハードウェア:**
- 3.5インチ SPI LCD 480x320（ILI9486 ドライバ IC）
- XPT2046 タッチコントローラー（SPI接続、ads7846互換）
- 26ピンコネクタ（40ピン互換、上位26ピン使用）

**変数:**
| 変数 | デフォルト値 | 説明 |
|------|-------------|------|
| `spi_lcd_driver` | `"ili9486"` | LCD ドライバ IC |
| `spi_lcd_overlay` | `"piscreen"` | dtoverlay 名 |
| `spi_lcd_width` | `480` | 画面幅 |
| `spi_lcd_height` | `320` | 画面高さ |
| `spi_lcd_rotate` | `0` | dtoverlay の rotate パラメータ |
| `spi_lcd_speed` | `24000000` | SPI 速度 (Hz) |
| `spi_lcd_touch_enabled` | `true` | タッチ有効化 |
| `spi_lcd_touch_penirq` | `25` | タッチ割り込み GPIO ピン |
| `spi_lcd_touch_speed` | `50000` | タッチ SPI 速度 |
| `spi_lcd_touch_calibration_matrix` | `""` | キャリブレーションマトリクス |

**処理内容:**
1. SPI 有効化（config.txt に `dtparam=spi=on`）
2. dtoverlay 設定（`piscreen` — ILI9486 DRM ドライバ + ads7846）
   - config.txt に `dtoverlay=piscreen,drm,speed=24000000,rotate=0`
   - `drm` パラメータ付きで DRM モードで動作（fbtft ではなく）
3. Xorg が SPI LCD を プライマリディスプレイとして使用する設定
   - `/etc/X11/xorg.conf.d/10-spi-lcd.conf` の配置
   - `/etc/X11/xorg.conf.d/99-v3d.conf` から `PrimaryGPU` を削除
4. タッチキャリブレーションツールのインストール（xlibinput_calibrator）
5. タッチキャリブレーション設定の配置

**表示パイプライン（Trixie DRM 方式）:**
```
X11 (Electron) → modesetting drv → /dev/dri/card1 (ili9486 DRM) → SPI → LCD
```

**DRM デバイス構成（Pi 4 + piscreen overlay）:**
```
/dev/dri/card0 — V3D (3Dアクセラレータ)
/dev/dri/card1 — ili9486 (SPI LCD) ← Xorg はこれをプライマリにする
/dev/dri/card2 — vc4-drm (HDMI)    ← PrimaryGPU を外す
```

**Xorg 設定テンプレート:**

`10-spi-lcd.conf.j2`:
```
Section "Device"
  Identifier "SPI-LCD"
  Driver "modesetting"
  Option "kmsdev" "/dev/dri/card1"
EndSection

Section "Screen"
  Identifier "SPI-Screen"
  Device "SPI-LCD"
  SubSection "Display"
    Modes "{{ spi_lcd_width }}x{{ spi_lcd_height }}"
  EndSubSection
EndSection

Section "ServerLayout"
  Identifier "Default Layout"
  Screen 0 "SPI-Screen"
EndSection
```

`99-v3d.conf` (PrimaryGPU なし):
```
Section "OutputClass"
  Identifier "vc4"
  MatchDriver "vc4"
  Driver "modesetting"
EndSection
```

**lcd-touchscreen ロールとの違い:**
- lcd-touchscreen: HDMI接続LCD + SPIタッチのみ
- spi-lcd: SPI接続LCD（DRM ili9486）+ SPIタッチ

**注意事項:**
- Trixie の `piscreen` overlay は DRM モードで動作し、fbtft/fbcp は不要
- card 番号はデバイス検出順に依存する。安定性のため `/dev/dri/by-path/` の利用も検討
- `DefaultDepth 16` を Xorg 設定に付けると `failed to add fb` エラーで起動しない → 付けない
- SPI バスを LCD (spi0.0) とタッチ (spi0.1) で共有
- 26ピンコネクタのため、GPIO 26 以降（ロータリーエンコーダ等）は空きピンとして使用可能
- タッチコントローラーの penirq (GPIO25) が SPI CS1 と競合する場合がある（dmesg に警告が出る）

---

### 5. sound-pi-kiosk

Sound-Pi 用 Electron アプリの kiosk モード設定。
既存の sonix-kiosk ロールをベースに、Sound-Pi 固有の設定を追加。

**対応環境:**
- Raspberry Pi 4 Model B
- Raspberry Pi OS with Desktop (64-bit, CUIモードで使用)
- 480x320 SPI LCD (横置き)

**変数:**
| 変数 | デフォルト値 | 説明 |
|------|-------------|------|
| `kiosk_user` | `"pi"` | ユーザー |
| `sound_pi_app_src` | `"../../sound-pi/release/linux-arm64-unpacked"` | アプリソースパス |
| `sound_pi_app_dest` | `"/opt/sound-pi"` | アプリ配置先 |
| `screen_physical_width` | `480` | 画面幅 |
| `screen_physical_height` | `320` | 画面高さ |
| `screen_refresh` | `60` | リフレッシュレート |
| `display_rotate` | `0` | 画面回転（0=回転なし） |
| `cursor_hide_timeout` | `0.1` | カーソル非表示タイムアウト（秒） |

**処理内容:**
1. X11 パッケージのインストール（xserver-xorg-core, xinput, unclutter, dbus-x11）
2. Electron アプリの rsync デプロイ
3. CUI モードに設定（multi-user.target）
4. getty autologin 設定（tty1）
5. `.bash_profile` 配置（startx 自動起動）
6. `.xinitrc` 配置（Electron kiosk 起動）
   - `--kiosk --no-sandbox --window-size=480,320`
   - 環境変数: `PIPEWIRE_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS`

**sonix-kiosk との違い:**
- アプリ名・パスが異なる（sound-pi）
- PipeWire 連携のための環境変数設定
- D-Bus セッションバスの設定（BT/WiFi 制御用）
- GPIO アクセス権限の設定

**テンプレート:**
- `autologin.conf.j2` — getty autologin
- `bash_profile.j2` — startx 自動起動 + 環境変数
- `xinitrc.j2` — X11 + Electron kiosk 起動

---

### 6. sound-pi-gpio

GPIO デバイスの設定。ロータリーエンコーダーと LED PWM の制御環境を構築する。

**対応環境:**
- Raspberry Pi 4 Model B
- Raspberry Pi OS (64-bit)

**変数:**
| 変数 | デフォルト値 | 説明 |
|------|-------------|------|
| `rotary_clk_pin` | `19` | ロータリーエンコーダー CLK ピン |
| `rotary_dt_pin` | `20` | ロータリーエンコーダー DT ピン |
| `rotary_sw_pin` | `26` | ロータリーエンコーダー SW（押下）ピン |
| `led_pin` | `13` | LED (PWM制御) ピン |
| `gpio_user` | `"pi"` | GPIO アクセスユーザー |

**処理内容:**
1. GPIO 関連パッケージの確認（libgpiod は Trixie にプリインストール済み）
   - `gpiod`（gpiomon, gpioset, gpioget）
   - `python3-libgpiod`（検証用）
2. hardware PWM dtoverlay の有効化（LED PWM 制御に使用）
   - `/boot/firmware/config.txt` に `dtoverlay=pwm,pin=13,func=4` 追加
   - GPIO13 を PWM1 チャネルとして sysfs (`/sys/class/pwm/pwmchip0/`) 経由で制御
3. ユーザーを `gpio` グループに追加
4. udev ルールの配置（GPIO / PWM デバイスのパーミッション設定）
5. 電源供給ピン（Pin4: 5V, Pin6: GND）の文書化（ハードウェア配線のみ）

**GPIO ピン配置:**
```
Pin  4 (5V)    : 外部電源入力 (5V)
Pin  6 (GND)   : 外部電源入力 (GND)
Pin 13 (GPIO13): LED PWM出力
Pin 19 (GPIO19): ロータリーエンコーダー CLK
Pin 20 (GPIO20): ロータリーエンコーダー DT
Pin 26 (GPIO26): ロータリーエンコーダー SW
```

**注意事項:**
- GPIO の実際の読み取り・制御は Electron アプリ（Node.js）側で実装
- このロールはハードウェアアクセスに必要な権限と基盤ソフトウェアのみを設定
- ロータリーエンコーダーは libgpiod (`gpiomon`) で edge 検出、内部プルアップ使用（外付け抵抗不要）
- LED PWM はカーネル sysfs hardware PWM を使用（GPIO13 = PWM1、dtoverlay で有効化）
- pigpio は Trixie で利用不可のため使用しない

---

## 既存ロールの利用

| ロール | 用途 | 備考 |
|------|------|------|
| `overlay-disable` | セットアップ前の overlayFS 解除 | 最初に実行 |
| `overlay-enable` | セットアップ後の overlayFS 有効化 | 最後に実行 |
| `apt-upgrade` | システムアップデート | |
| `disable-cloud-init` | cloud-init 無効化 | |
| `disable-services` | 不要サービス無効化 | BT は除外 |
| `config-persistence` | 設定ファイルの永続化 | overlayFS 環境用 |
| ~~`lcd-touchscreen`~~ | ~~HDMI LCD + タッチ設定~~ | 使用しない（HDMI用のため） |
| `boot-splash` | 起動画面カスタマイズ | 任意 |
| `keep-wifi` | WiFi 接続維持 | 任意 |
| `rpi-clone` | SDカード複製 | 任意 |

## ロール実行順序の依存関係

```
overlay-disable          (最初: overlayFS解除)
  ↓
apt-upgrade              (システム更新)
disable-cloud-init
disable-services
config-persistence
  ↓
usb-gadget               (config.txt 変更あり → 後続ロールの前に)
  ↓
pipewire                 (オーディオ基盤 → BT, kiosk より先に)
  ↓
bluetooth-audio          (PipeWire に依存)
  ↓
spi-lcd                  (SPI LCD + fbcp → kiosk より先に)
  ↓
sound-pi-kiosk           (PipeWire, LCD に依存)
  ↓
sound-pi-gpio            (独立、順序は任意)
  ↓
overlay-enable           (最後: overlayFS有効化)
```
