# PLC Trigger Camera

PLCの指定ビットがON（立ち上がりエッジ）になったとき、USBカメラで自動撮影してPNGを保存するGUIツールです。

- **対応PLC**: 三菱電機 MELSEC Q / L / QnA / iQ-L / iQ-R シリーズ（MCプロトコル 3E / 4E タイプ）
- **動作環境**: Windows 10/11、Raspberry Pi OS（64-bit）
- **Python**: 3.11 以上

---

## スクリーンショット

![PLC Trigger Camera — メインウィンドウ](2026-03-31-2.png)

---

## 機能

| 機能 | 説明 |
|---|---|
| PLC ビット監視 | 複数デバイスを指定間隔でポーリング、立ち上がりエッジを検出 |
| 自動撮影 | ビットON時にカメラキャプチャ → PNG保存 |
| リアルタイムプレビュー | ~30fps でカメラ映像を表示（解像度は設定可能） |
| 手動撮影 | ツールバーの「Manual Capture」ボタンでいつでも撮影 |
| 設定ダイアログ | PLC / デバイス / カメラ / 保存 / オプション の5タブ |
| 設定の永続化 | `config.json` に自動保存、次回起動時に復元 |
| シミュレーションモード | PLC未接続でも動作確認が可能（Debug メニューから有効化） |
| 日付フォルダ | 日ごとに `YYYY-MM-DD/` サブフォルダを作成（オプション） |
| デバイスサブフォルダ | デバイスラベルごとにサブフォルダを作成（オプション） |
| ビープ音 | キャプチャ成功時に OK 音、失敗時に NG 音（[beep-lite](https://pypi.org/project/beep-lite/) インストール時のみ） |

---

## 必要なもの

- [uv](https://docs.astral.sh/uv/) — パッケージマネージャ
- Python 3.11 以上（uv が自動でインストール）
- tkinter（Python 標準ライブラリ）
  - Windows: Python インストール時に同梱
  - Raspberry Pi OS: `sudo apt install python3-tk`
- USBカメラ

---

## インストールと起動

### Windows

```powershell
git clone https://github.com/your-repo/plc_trigger_cam.git
cd plc_trigger_cam
.\run.ps1
```

初回実行時に `uv sync` で仮想環境と依存パッケージが自動作成されます。

> **ビープ音を有効にする場合（オプション）**
> ```powershell
> uv sync --extra audio
> ```
> [beep-lite](https://pypi.org/project/beep-lite/) がインストールされると、キャプチャ成功時に OK 音、フレーム未取得時に NG 音が鳴ります。  
> インストールしない場合は音なしで通常動作します。

### Linux / Raspberry Pi

```bash
git clone https://github.com/your-repo/plc_trigger_cam.git
cd plc_trigger_cam
chmod +x run.sh
./run.sh
```

---

## 使い方

### 1. PLC を設定する

**File → Settings… → PLC タブ** で以下を設定します。

| 項目 | 説明 | デフォルト |
|---|---|---|
| IP Address | PLC の IP アドレス | `192.168.1.10` |
| Port | MCプロトコルのポート番号 | `1025` |
| PLC Type | Q / L / QnA / iQ-L / iQ-R | `Q` |
| Protocol | 3E / 4E | `3E` |
| Poll interval (ms) | ビット読み取り間隔 | `100` |

> PLCの事前設定（GxWorks2 / GxWorks3 でのポート開放）については  
> https://qiita.com/satosisotas/items/38f64c872d161b612071 を参照してください。

### 2. 監視デバイスを設定する

**Settings → Devices タブ** でビットデバイスを追加します。

- **Add**: デバイスアドレス（例: `M100`, `X10`）とラベルを入力
- **Toggle**: 有効 / 無効を切り替え
- **Edit / Delete**: 既存デバイスの編集・削除

### 3. カメラ・保存先を設定する

| タブ | 主な設定項目 |
|---|---|
| Camera | カメラインデックス・キャプチャ解像度・プレビュー解像度 |
| Save | 保存先フォルダ・PNG圧縮レベル（0=高速/大 〜 9=低速/小）・ファイル名形式 |
| Options | 日付フォルダ（YYYY-MM-DD）・デバイスサブフォルダ・トリガー通知音 |

### 4. PLC に接続して監視開始

ツールバーの **「Connect PLC」** をクリックします。  
接続に成功すると右ペインの状態インジケータが **緑** になり、監視が開始されます。

### 5. 自動撮影

ビットが OFF → ON になると自動撮影されます。  
撮影ファイルは以下のパスに保存されます（デフォルト設定の場合）。

```
<保存先>/
└── 2026-03-30/          ← daily_folder=true の場合
    └── 20260330_153000_042_Trigger.png
```

---

## ファイル名の形式

`filename_format` には Python の `strftime` 書式 ＋ 以下のプレースホルダが使えます。

| プレースホルダ | 説明 |
|---|---|
| `%Y%m%d` | 日付（例: `20260330`） |
| `%H%M%S` | 時刻（例: `153000`） |
| `{ms:03d}` | ミリ秒（3桁ゼロ埋め） |
| `{device}` | デバイスラベル（英数字・`-_` 以外は `_` に置換） |

デフォルト: `%Y%m%d_%H%M%S_{ms:03d}_{device}` → `20260330_153000_042_Trigger.png`

---

## シミュレーションモード

PLC が手元にない場合でも動作確認ができます。

1. **Debug → Toggle Simulation Mode** でシミュレーションを有効化
2. ツールバー右端にトリガー発火コントロールが表示される
3. デバイスを選択して **「Fire!」** をクリックすると疑似トリガーが発生し撮影される

---

## 開発

```powershell
# 依存パッケージのインストール（dev含む）
uv sync

# ビープ音機能を有効にする場合（オプション）
uv sync --extra audio

# Lint チェック
uv run ruff check src/

# フォーマット
uv run ruff format src/

# 型チェック
uv run ty check src/

# 起動
uv run src/main.py
```

### ファイル構成

```
plc_trigger_cam/
├── run.ps1               # Windows 起動スクリプト
├── run.sh                # Linux / Raspberry Pi 起動スクリプト
├── pyproject.toml        # uv / ruff / ty 設定
├── config.json           # 設定ファイル（実行時自動生成）
└── src/
    ├── main.py           # メインウィンドウ（GUI）
    ├── plc_monitor.py    # PLC監視スレッド
    ├── camera.py         # カメラキャプチャスレッド
    ├── config.py         # 設定 dataclass + JSON 永続化
    └── settings_dialog.py # 設定ダイアログ
```

---

## ライセンス

MIT
