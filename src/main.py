"""PLC トリガーカメラ — メインアプリケーションウィンドウ。"""

from __future__ import annotations

import contextlib
import os
import queue
import sys
import tkinter as tk
import types
from datetime import datetime
from pathlib import Path
from queue import Queue
from tkinter import messagebox, scrolledtext, ttk
from typing import TYPE_CHECKING, Any

import cv2
from PIL import Image, ImageTk

from camera import CameraThread
from config import load_config, save_config
from plc_monitor import BitStateEvent, PlcMonitor, PlcStatus, StatusEvent, TriggerEvent
from settings_dialog import SettingsDialog

_beep: types.ModuleType | None = None
with contextlib.suppress(ModuleNotFoundError):
    import beep_lite as _beep  # オプション依存: pip install beep-lite

if TYPE_CHECKING:
    pass

# GUI 更新間隔（ミリ秒）— 細4⁠ 30 fps
_REFRESH_MS = 33

# tkinter スレッド安全性のため: スレッド間のイベントはこのキュー経由
_GUI_EVENT_QUEUE: Queue[TriggerEvent | StatusEvent | BitStateEvent] = Queue()

# キャプチャログの最大行数
_LOG_MAX_LINES = 500


# ---------------------------------------------------------------------------
# ステータスインジケータウィジェット
# ---------------------------------------------------------------------------


class _StatusLight(tk.Canvas):
    """丸形の色付きインジケータウィジェット。"""

    _RADIUS = 8
    _SIZE = _RADIUS * 2 + 4

    def __init__(self, parent: tk.Misc, **kwargs: Any) -> None:
        """インジケータを初期化する。

        Args:
            parent: 親ウィジェット。
            **kwargs: :class:`tk.Canvas` に渡す追加オプション。
        """
        super().__init__(
            parent, width=self._SIZE, height=self._SIZE, highlightthickness=0, **kwargs
        )
        self._oval = self.create_oval(
            2, 2, self._SIZE - 2, self._SIZE - 2, fill="gray", outline=""
        )

    def set_color(self, color: str) -> None:
        """インジケータの色を変更する。

        Args:
            color: tkinter が認識する色文字列。
        """
        self.itemconfig(self._oval, fill=color)


# ---------------------------------------------------------------------------
# メインアプリケーション
# ---------------------------------------------------------------------------


class App(tk.Tk):
    """アプリケーションメインウィンドウ。

    プレビューパネル・デバイスステータス・キャプチャログを一画面にまとめた
    タブレットレイアウト。PLCモニターとカメラスレッドを通じて自動キャプチャを行う。
    """

    def __init__(self) -> None:
        """アプリケーションを初期化し、UI を構築しカメラなどを起動する。"""
        super().__init__()
        self.title("PLC Trigger Camera")
        self.resizable(True, True)

        self._cfg = load_config()
        self._simulate_mode = False
        self._closing = False

        # バックグラウンドスレッド（PLC 接続時に開始）
        self._plc_monitor: PlcMonitor | None = None
        self._camera: CameraThread | None = None

        self._build_ui()
        self._apply_config_to_ui()
        self._start_camera()
        self._schedule_refresh()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """メニュー・ツールバー・メインパネル・ステータスバーを生成する。"""
        self._build_menu()
        self._build_toolbar()
        self._build_main_panel()
        self._build_status_bar()

    def _build_menu(self) -> None:
        """アプリケーションのメニューバーを構築する。"""
        mb = tk.Menu(self)
        self.config(menu=mb)

        file_menu = tk.Menu(mb, tearoff=False)
        file_menu.add_command(
            label="Settings…", accelerator="Ctrl+,", command=self._open_settings
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        mb.add_cascade(label="File", menu=file_menu)
        self.bind_all("<Control-comma>", lambda _: self._open_settings())

        sim_menu = tk.Menu(mb, tearoff=False)
        sim_menu.add_command(
            label="Toggle Simulation Mode", command=self._toggle_simulation
        )
        mb.add_cascade(label="Debug", menu=sim_menu)

    def _build_toolbar(self) -> None:
        """ツールバーボタンとシミュレーションパネルを構築する。"""
        tb = ttk.Frame(self, relief="groove")
        tb.pack(fill="x", padx=4, pady=(4, 0))

        self._btn_connect = ttk.Button(
            tb, text="Connect PLC", command=self._toggle_plc_connection
        )
        self._btn_connect.pack(side="left", padx=2, pady=2)

        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=4)

        self._btn_capture = ttk.Button(
            tb, text="Manual Capture", command=self._manual_capture
        )
        self._btn_capture.pack(side="left", padx=2, pady=2)

        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=4)

        ttk.Button(tb, text="Settings…", command=self._open_settings).pack(
            side="left", padx=2, pady=2
        )

        # シミュレーショントリガーボタン（シミュレーションモード時のみ表示）
        self._sim_frame = ttk.Frame(tb)
        self._sim_frame.pack(side="right", padx=2, pady=2)
        self._sim_label = ttk.Label(self._sim_frame, text="[SIM] Trigger device:")
        self._sim_label.pack(side="left")
        self._sim_combo: ttk.Combobox = ttk.Combobox(
            self._sim_frame, width=14, state="readonly"
        )
        self._sim_combo.pack(side="left", padx=2)
        self._btn_sim_fire = ttk.Button(
            self._sim_frame, text="Fire!", command=self._sim_fire_trigger
        )
        self._btn_sim_fire.pack(side="left")
        self._sim_frame.pack_forget()  # シミュレーションモード有効時まで非表示

    def _build_main_panel(self) -> None:
        """左ペイン（カメラプレビュー）と右ペイン（ステータス／ログ）を構築する。"""
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=4, pady=4)

        # --- 左: カメラプレビュー ---
        left = ttk.LabelFrame(paned, text="Camera Preview")
        paned.add(left, weight=3)

        self._preview_canvas = tk.Canvas(left, bg="black", width=640, height=480)
        self._preview_canvas.pack(fill="both", expand=True)
        self._preview_image_id = self._preview_canvas.create_image(0, 0, anchor="nw")
        self._preview_tk_img: ImageTk.PhotoImage | None = None

        # --- 右: ステータス + ログ ---
        right = ttk.Frame(paned)
        paned.add(right, weight=1)

        # PLC 接続パネル
        plc_panel = ttk.LabelFrame(right, text="PLC Status")
        plc_panel.pack(fill="x", padx=4, pady=(0, 4))

        row = ttk.Frame(plc_panel)
        row.pack(fill="x", padx=6, pady=4)
        # ttk.LabelFrame は cget("background") 非対応のため Style で解決
        bg = ttk.Style().lookup("TFrame", "background") or "SystemButtonFace"
        self._plc_light = _StatusLight(row, bg=bg)
        self._plc_light.pack(side="left")
        self._plc_status_label = ttk.Label(row, text="Disconnected")
        self._plc_status_label.pack(side="left", padx=4)

        # デバイス状態パネル
        dev_panel = ttk.LabelFrame(right, text="Device States")
        dev_panel.pack(fill="x", padx=4, pady=(0, 4))

        cols = ("address", "label", "state")
        self._dev_tree = ttk.Treeview(
            dev_panel, columns=cols, show="headings", height=6
        )
        self._dev_tree.heading("address", text="Address")
        self._dev_tree.heading("label", text="Label")
        self._dev_tree.heading("state", text="State")
        self._dev_tree.column("address", width=100)
        self._dev_tree.column("label", width=110)
        self._dev_tree.column("state", width=60, anchor="center")
        self._dev_tree.pack(fill="x", padx=4, pady=4)
        self._dev_tree.tag_configure("on", foreground="green")
        self._dev_tree.tag_configure("off", foreground="gray")

        # 最後のキャプチャ情報
        info_panel = ttk.LabelFrame(right, text="Last Capture")
        info_panel.pack(fill="x", padx=4, pady=(0, 4))
        self._last_capture_label = ttk.Label(info_panel, text="—", wraplength=260)
        self._last_capture_label.pack(padx=6, pady=4)

        # キャプチャログ
        log_panel = ttk.LabelFrame(right, text="Capture Log")
        log_panel.pack(fill="both", expand=True, padx=4)
        self._log = scrolledtext.ScrolledText(
            log_panel, height=10, state="disabled", font=("Courier", 9)
        )
        self._log.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_status_bar(self) -> None:
        """ウィンドウ下部のステータスバーを構築する。"""
        sb = ttk.Frame(self, relief="sunken")
        sb.pack(fill="x", side="bottom")
        self._status_bar_label = ttk.Label(sb, text="Ready", anchor="w")
        self._status_bar_label.pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # 設定の反映
    # ------------------------------------------------------------------

    def _apply_config_to_ui(self) -> None:
        """設定値を元にデバイスツリー行を再構築する。"""
        for item in self._dev_tree.get_children():
            self._dev_tree.delete(item)
        for dev in self._cfg.plc.devices:
            if dev.enabled:
                self._dev_tree.insert(
                    "",
                    "end",
                    iid=dev.address,
                    values=(dev.address, dev.label, "—"),
                    tags=("off",),
                )

        # シミュレーションコンボを更新
        enabled_addrs = [d.address for d in self._cfg.plc.devices if d.enabled]
        self._sim_combo["values"] = enabled_addrs
        if enabled_addrs:
            self._sim_combo.current(0)

    # ------------------------------------------------------------------
    # カメラ
    # ------------------------------------------------------------------

    def _start_camera(self) -> None:
        """既存スレッドを停止してカメラスレッドを再起動する。"""
        if self._camera:
            self._camera.stop()
        self._camera = CameraThread(self._cfg)
        self._camera.start()

    def _update_preview(self) -> None:
        """最新フレームをプレビューキャンバスに描画する。"""
        if self._camera is None:
            return
        frame = self._camera.get_preview_frame()
        if frame is None:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)

        # キャンバスに合わせてスケール
        cw = self._preview_canvas.winfo_width() or self._cfg.camera.preview_width
        ch = self._preview_canvas.winfo_height() or self._cfg.camera.preview_height
        img.thumbnail((cw, ch), Image.Resampling.LANCZOS)

        self._preview_tk_img = ImageTk.PhotoImage(img)
        self._preview_canvas.itemconfig(
            self._preview_image_id, image=self._preview_tk_img
        )

    # ------------------------------------------------------------------
    # PLC 接続
    # ------------------------------------------------------------------

    def _toggle_plc_connection(self) -> None:
        """接続中なら切断、未接続ならモニターを起動する。"""
        if self._plc_monitor and self._plc_monitor.is_alive():
            self._plc_monitor.stop()
            self._plc_monitor.join(timeout=2.0)
            self._plc_monitor = None
            self._btn_connect.config(text="Connect PLC")
            self._plc_light.set_color("gray")
            self._plc_status_label.config(text="Disconnected")
            self._set_status("PLC disconnected.")
        else:
            self._start_plc_monitor()

    def _start_plc_monitor(self) -> None:
        """新たに PLCモニタースレッドを生成・起動する。"""
        self._plc_monitor = PlcMonitor(
            self._cfg.plc, _GUI_EVENT_QUEUE, simulate=self._simulate_mode
        )
        self._plc_monitor.start()
        self._btn_connect.config(text="Disconnect PLC")
        self._set_status(f"Connecting to {self._cfg.plc.ip}:{self._cfg.plc.port}…")

    # ------------------------------------------------------------------
    # シミュレーションモード
    # ------------------------------------------------------------------

    def _toggle_simulation(self) -> None:
        """シミュレーションモードの有効／無効を切り替える。"""
        self._simulate_mode = not self._simulate_mode
        if self._simulate_mode:
            self._sim_frame.pack(side="right", padx=2, pady=2)
            messagebox.showinfo(
                "Simulation Mode",
                "Simulation mode enabled.\nNo real PLC connection will be made.",
            )
        else:
            self._sim_frame.pack_forget()
        # 動作中なら新モードでモニターを再起動
        if self._plc_monitor and self._plc_monitor.is_alive():
            self._plc_monitor.stop()
            self._plc_monitor.join(timeout=2.0)
            self._start_plc_monitor()

    def _sim_fire_trigger(self) -> None:
        """シミュレーションコンボで選択中のデバイスにトリガーを送信する。"""
        addr = self._sim_combo.get()
        if addr and self._plc_monitor:
            self._plc_monitor.simulate_trigger(addr)

    # ------------------------------------------------------------------
    # 手動キャプチャ
    # ------------------------------------------------------------------

    def _manual_capture(self) -> None:
        """手動トリガーで高解像度キャプチャを実行する。"""
        self._do_capture("manual")

    def _do_capture(self, device_label: str) -> None:
        """高解像度キャプチャを実行しログに記録する。

        Args:
            device_label: キャプチャをトリガーしたデバイスのラベル。
        """
        if self._camera is None:
            return
        path = self._camera.capture_hires(device_label)
        if path:
            self._log_capture(path, device_label)
            self._last_capture_label.config(text=str(path))
            if _beep:
                _beep.ok()
        else:
            self._set_status("Capture failed: no frame available.")
            if _beep:
                _beep.ng()

    def _log_capture(self, path: Path, device_label: str) -> None:
        """キャプチャリストにパスとタイムスタンプを追記する。

        Args:
            path: 保存されたファイルのパス。
            device_label: トリガーデバイスのラベル。
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"[{ts}]  {device_label}  →  {path.name}\n"
        self._log.config(state="normal")
        self._log.insert("end", line)

        # 古い行を削除
        lines = int(self._log.index("end-1c").split(".")[0])
        if lines > _LOG_MAX_LINES:
            self._log.delete("1.0", f"{lines - _LOG_MAX_LINES}.0")

        self._log.see("end")
        self._log.config(state="disabled")
        self._set_status(f"Captured: {path}")

    # ------------------------------------------------------------------
    # 設定ダイアログ
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        """設定ダイアログを開き、OK時は設定を保存しカメラを再起動する。"""
        running = bool(self._plc_monitor and self._plc_monitor.is_alive())
        if running:
            self._toggle_plc_connection()

        dlg = SettingsDialog(self, self._cfg)
        self.wait_window(dlg)

        if dlg.result is not None:
            self._cfg = dlg.result
            save_config(self._cfg)
            self._apply_config_to_ui()
            self._start_camera()
            self._set_status("Settings saved.")

        if running:
            self._start_plc_monitor()

    # ------------------------------------------------------------------
    # PLC モニターからのイベント処理
    # ------------------------------------------------------------------

    def _process_plc_events(self) -> None:
        """イベントキューに溜まった全イベントを处理する。"""
        try:
            while True:
                event = _GUI_EVENT_QUEUE.get_nowait()
                if isinstance(event, StatusEvent):
                    self._handle_status_event(event)
                elif isinstance(event, TriggerEvent):
                    self._handle_trigger_event(event)
                elif isinstance(event, BitStateEvent):
                    self._handle_bit_state_event(event)
        except queue.Empty:
            pass

    def _handle_status_event(self, event: StatusEvent) -> None:
        """ステータス変化イベントに応じて PLC インジケータを更新する。

        Args:
            event: 受信した :class:`~plc_monitor.StatusEvent`。
        """
        color_map = {
            PlcStatus.DISCONNECTED: "gray",
            PlcStatus.CONNECTING: "yellow",
            PlcStatus.CONNECTED: "green",
            PlcStatus.ERROR: "red",
        }
        self._plc_light.set_color(color_map[event.status])
        self._plc_status_label.config(text=event.status.name.capitalize())
        self._set_status(event.message)

    def _handle_trigger_event(self, event: TriggerEvent) -> None:
        """トリガーイベントに応じてキャプチャを実行する。

        Args:
            event: 受信した :class:`~plc_monitor.TriggerEvent`。
        """
        self._do_capture(event.label)

    def _handle_bit_state_event(self, event: BitStateEvent) -> None:
        """ビット状態イベントでデバイスツリーを更新する。

        Args:
            event: 受信した :class:`~plc_monitor.BitStateEvent`。
        """
        for addr, state in event.states.items():
            try:
                tag = "on" if state else "off"
                self._dev_tree.set(addr, "state", "ON" if state else "OFF")
                self._dev_tree.item(addr, tags=(tag,))
            except tk.TclError:
                pass  # 設定変更後は行が存在しない可能性がある

    # ------------------------------------------------------------------
    # メイン更新ループ
    # ------------------------------------------------------------------

    def _schedule_refresh(self) -> None:
        """プレビューとイベント処理を毎 tick 実行し、次回をスケジュールする。"""
        if self._closing:
            return
        self._update_preview()
        self._process_plc_events()
        self.after(_REFRESH_MS, self._schedule_refresh)

    # ------------------------------------------------------------------
    # ステータスバーヘルパー
    # ------------------------------------------------------------------

    def _set_status(self, msg: str) -> None:
        """ステータスバーのメッセージを更新する。

        Args:
            msg: 表示するメッセージ。
        """
        self._status_bar_label.config(text=msg)

    # ------------------------------------------------------------------
    # 終了処理
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        """全スレッドを安全に停止し設定を保存してウィンドウを閉じる。"""
        self._closing = True
        if self._plc_monitor:
            self._plc_monitor.stop()
        if self._camera:
            self._camera.stop()
        save_config(self._cfg)
        # タイムアウト付き join — cv2 内部スレッドが cap.read() をブロックする可能性あり
        if self._plc_monitor:
            self._plc_monitor.join(timeout=2.0)
        if self._camera:
            self._camera.join(timeout=2.0)
        self.destroy()
        os._exit(0)


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------


def main() -> None:
    """アプリケーションのエントリポイント。

    ``uv run src/main.py`` 実行時にサイドモジュールを解決できるように
    ``src/`` を ``sys.path`` に追加する。
    """
    # src/ を sys.path に追加（プロジェクトルートから実行時に同階モジュールを解決するため）
    src_dir = str(Path(__file__).parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
