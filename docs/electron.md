# Electron 実装（ペンディング）

Electron + React による UI 実装の記録。pygame + fbdev 方式への移行を検討中のため、現在ペンディング。

## 技術スタック

- **Electron 28** + **React 18** + **Vite 5** + **TypeScript 5**
- **TailwindCSS 3** — スタイリング
- **Canvas API** — VUメーター / スペクトラムアナライザ描画
- **electron-store** — 設定永続化

## ビルド・実行

```bash
npm run dev              # Vite dev server のみ
npm run electron:dev     # Vite + Electron 同時起動（開発用）
npm run build            # プロダクションビルド
npm run package:linux-arm64  # ARM64パッケージング
```

## プロジェクト構成

```
sound-pi/
├── package.json            # "type": "module" は使わない（Electron CJS互換）
├── vite.config.ts          # base: './', @/ alias, __GIT_COMMIT__ define
├── tsconfig.json           # Renderer用（ESNext, noEmit, bundler resolution）
├── tsconfig.electron.json  # Main process用（CommonJS → dist-electron/）
├── tsconfig.node.json      # Vite config用
├── index.html              # lang="ja", CSP設定済み
├── postcss.config.mjs      # ESMなので .mjs
├── tailwind.config.mjs     # ESMなので .mjs
├── electron/
│   ├── main.ts             # メインプロセス（IPC登録、Window作成、マネージャ管理）
│   ├── preload.ts          # contextBridge → window.soundPiAPI
│   ├── git-version.ts      # ビルド時自動生成
│   ├── audio/
│   │   ├── pipewire-manager.ts  # wpctl ラッパー（デバイス一覧、音量、ミュート）
│   │   └── audio-capture.ts     # pw-cat でPCMキャプチャ → FFT → renderer送信
│   ├── usb-hid/
│   │   └── hid-controller.ts    # /dev/hidg0 書き込み（Play/Pause, Next, Prev）
│   ├── bluetooth/
│   │   └── bluetooth-manager.ts # bluetoothctl ラッパー
│   ├── network/
│   │   └── wifi-manager.ts      # nmcli ラッパー
│   ├── gpio/
│   │   └── gpio-manager.ts      # gpiomon + sysfs PWM（CLK=19, DT=20, SW=26, LED=13）
│   └── utils/
│       └── logger.ts            # タグ付きロガー（メモリバッファ500件）
└── src/
    ├── main.tsx                 # React エントリ
    ├── App.tsx                  # 画面ルーティング + ロータリー連動
    ├── index.css                # Tailwind + 480x320固定、cursor:none
    ├── types/
    │   └── api.d.ts             # SoundPiAPI型定義 + Window拡張
    ├── hooks/
    │   ├── useAudioData.ts      # IPC audio:data 受信
    │   ├── useRotaryEncoder.ts  # IPC rotary イベント受信
    │   └── useVolume.ts         # 音量状態 + オーバーレイ表示管理
    ├── components/
    │   ├── Menu.tsx             # 3×2 タイルメニュー
    │   ├── MenuTrigger.tsx      # 左上100x100 タップ領域
    │   ├── VolumeOverlay.tsx    # 音量バー（2秒フェードアウト）
    │   └── MuteOverlay.tsx      # ミュート表示
    └── screens/
        ├── VuMeter.tsx          # アナログ針VUメーター（Canvas）
        ├── DualVuMeter.tsx      # L/R 2連VUメーター（Canvas）
        ├── SpectrumAnalyzer.tsx # 32バンドFFTアナライザ（Canvas）
        ├── InputMixer.tsx       # USB/Browser入力ミックス + 出力デバイス音量
        ├── BluetoothSettings.tsx # BTスキャン・ペアリング・接続管理
        └── WifiSettings.tsx     # WiFiスキャン・接続管理
```

## IPC設計

チャネル名は `カテゴリ:アクション` 形式（例: `audio:set-master-volume`, `bt:scan`, `gpio:rotary-turn`）。

- **invoke** (Promise) — `audio:*`, `bt:*`, `wifi:*`, `system:*`
- **send** (fire-and-forget) — `hid:*`, `gpio:set-led-*`, `renderer-log`
- **on** (main→renderer) — `audio:data`, `gpio:rotary-turn/press/long-press`, `bt:device-changed`, `wifi:status-changed`

## 画面遷移

```
起動 → VuMeter（デフォルト）
左上100x100タップ → Menu（3×2タイル） → 画面選択
ロータリー回転 → VolumeOverlay（2秒後消える）
ロータリー短押し → Play/Pause (USB HID)
ロータリー長押し → Mute切替
```

## ビルド・コードの注意点

- `package.json` に `"type": "module"` を入れてはいけない（Electron main processがCJS）
- ESM形式のconfig（postcss, tailwind）は `.mjs` 拡張子を使う
- 開発時は480x320ウィンドウ、本番はkioskモード全画面
- GPIO非搭載環境（開発マシン）ではstubモードで動作

## SPI LCD + Xorg (spi-lcd ansible ロール)

- card 番号は起動毎に変わる → `kmsdev` で `/dev/dri/by-path/platform-fe204000.spi-cs-0-card` を使用
- `rp1-test.service` はマスクしない（99-v3d.conf に PrimaryGPU "true" を設定してくれる）
- `PrimaryGPU "true"` は必須: logind が vc4 で DRM master を取り、SPI LCD の fd が空く
- `xserver-xorg-legacy` をインストールすると X が root で動作し drmSetMaster が競合する → インストールしない
- `DefaultDepth 16` を付けると `failed to add fb` エラー → 付けない
- `hdmi_ignore_hotplug` で HDMI を無効化しないと vc4 が HDMI fb を作ろうとして起動が 3〜5 分遅延

## Electron kiosk フラグ

- 必須: `--kiosk --no-sandbox --disable-gpu --disable-gpu-compositing --ozone-platform=x11`
- 禁止: `--disable-software-rasterizer`（白画面クラッシュ）
- 禁止: `--in-process-gpu`（白画面クラッシュ）

## 参考にした既存コード

| パターン | 参考元 |
|---------|--------|
| Electron基本構成 | `/home/pi/git/Sonix/sonix2/` |
| BluetoothManager | `/home/pi/git/pi-obd2/electron/bluetooth/` |
| WiFiManager | `/home/pi/git/pi-obd2/electron/network/` |
| GpioManager | `/home/pi/git/pi-obd2/electron/gpio/` |
| Logger | `/home/pi/git/pi-obd2/electron/logger.ts` |

## HDMI ミラーリング試行（断念）

GPU アクセラレーションのため HDMI 出力 + fbcp ミラーリングを試みたが断念。

- ファームウェアの `hdmi_force_hotplug` は KMS/DRM ドライバに効かない
- `video=HDMI-A-1:640x480@60D` (cmdline.txt) で HDMI 強制有効化は可能
- 480x320 は HDMI 標準モードにない → 640x480 + クロップが必要
- SDL2 KMSDRM バックエンドは ili9486 DRM で EACCES (-13) → logind が DRM master を保持
- 最終的に pygame + fbdev 直接書き込み方式に移行を決定
