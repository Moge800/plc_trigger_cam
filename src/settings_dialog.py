"""設定ダイアログ — PLCトリガーカメラのタブ形式設定UI。"""

from __future__ import annotations

import ipaddress
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from config import (
    PLC_TYPES,
    PROTOCOL_TYPES,
    AppConfig,
    CameraConfig,
    DeviceConfig,
    PlcConfig,
    SaveConfig,
)

if TYPE_CHECKING:
    pass


class SettingsDialog(tk.Toplevel):
    """タブ形式のモーダル設定ダイアログ。

    OKボタン押下後は ``self.result`` に更新済みの
    :class:`~config.AppConfig` が格納される。
    キャンセル時は ``None``。
    """

    def __init__(self, parent: tk.Misc, cfg: AppConfig) -> None:
        """設定ダイアログを初期化する。

        Args:
            parent: 親ウィジェット。
            cfg: 現在の設定値。
        """
        super().__init__(parent)
        self.title("Settings")
        self.resizable(False, False)
        self.result: AppConfig | None = None

        # 作業用コピー
        self._cfg = cfg
        self._devices: list[DeviceConfig] = [
            DeviceConfig(d.address, d.label, d.enabled) for d in cfg.plc.devices
        ]

        self._build_ui()
        self._populate(cfg)

        if isinstance(parent, tk.Wm):
            self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    # ------------------------------------------------------------------
    # UI構築
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """ノートブックと各タブ、ボタン行を生成する。"""
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._tab_plc = self._build_tab_plc(nb)
        self._tab_devices = self._build_tab_devices(nb)
        self._tab_camera = self._build_tab_camera(nb)
        self._tab_save = self._build_tab_save(nb)
        self._tab_options = self._build_tab_options(nb)

        nb.add(self._tab_plc, text="PLC")
        nb.add(self._tab_devices, text="Devices")
        nb.add(self._tab_camera, text="Camera")
        nb.add(self._tab_save, text="Save")
        nb.add(self._tab_options, text="Options")

        # ボタン行
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(
            side="right", padx=4
        )
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel, width=10).pack(
            side="right"
        )

    # ---- PLCタブ ---------------------------------------------------------

    def _build_tab_plc(self, parent: ttk.Notebook) -> ttk.Frame:
        """PLCタブのウィジェットを構築する。

        Args:
            parent: 追加先の Notebook。

        Returns:
            構築したタブフレーム。
        """
        f = ttk.Frame(parent, padding=12)

        self._plc_ip = self._labeled_entry(f, "IP Address:", 0)
        self._plc_port = self._labeled_entry(f, "Port:", 1)

        ttk.Label(f, text="PLC Type:").grid(row=2, column=0, sticky="w", pady=3)
        self._plc_type = ttk.Combobox(f, values=PLC_TYPES, state="readonly", width=18)
        self._plc_type.grid(row=2, column=1, sticky="w", pady=3)

        ttk.Label(f, text="Protocol:").grid(row=3, column=0, sticky="w", pady=3)
        self._plc_protocol = ttk.Combobox(
            f, values=PROTOCOL_TYPES, state="readonly", width=18
        )
        self._plc_protocol.grid(row=3, column=1, sticky="w", pady=3)

        self._plc_poll = self._labeled_entry(f, "Poll interval (ms):", 4)

        return f

    # ---- デバイスタブ -----------------------------------------------------

    def _build_tab_devices(self, parent: ttk.Notebook) -> ttk.Frame:
        """デバイスタブのウィジェットを構築する。

        Args:
            parent: 追加先の Notebook。

        Returns:
            構築したタブフレーム。
        """
        f = ttk.Frame(parent, padding=12)

        cols = ("address", "label", "enabled")
        self._dev_tree = ttk.Treeview(f, columns=cols, show="headings", height=8)
        self._dev_tree.heading("address", text="Device Address")
        self._dev_tree.heading("label", text="Label")
        self._dev_tree.heading("enabled", text="Enabled")
        self._dev_tree.column("address", width=140)
        self._dev_tree.column("label", width=140)
        self._dev_tree.column("enabled", width=70, anchor="center")
        self._dev_tree.grid(row=0, column=0, columnspan=4, sticky="nsew", pady=(0, 6))

        ttk.Button(f, text="Add", command=self._dev_add, width=8).grid(
            row=1, column=0, padx=2
        )
        ttk.Button(f, text="Edit", command=self._dev_edit, width=8).grid(
            row=1, column=1, padx=2
        )
        ttk.Button(f, text="Delete", command=self._dev_delete, width=8).grid(
            row=1, column=2, padx=2
        )
        ttk.Button(f, text="Toggle", command=self._dev_toggle, width=8).grid(
            row=1, column=3, padx=2
        )

        f.columnconfigure(0, weight=1)
        return f

    # ---- カメラタブ ------------------------------------------------------

    def _build_tab_camera(self, parent: ttk.Notebook) -> ttk.Frame:
        """カメラタブのウィジェットを構築する。

        Args:
            parent: 追加先の Notebook。

        Returns:
            構築したタブフレーム。
        """
        f = ttk.Frame(parent, padding=12)

        self._cam_index = self._labeled_entry(f, "Camera Index:", 0)

        ttk.Label(f, text="Capture Resolution:").grid(
            row=1, column=0, sticky="w", pady=3
        )
        cap_frame = ttk.Frame(f)
        cap_frame.grid(row=1, column=1, sticky="w")
        self._cap_w = ttk.Entry(cap_frame, width=7)
        self._cap_w.pack(side="left")
        ttk.Label(cap_frame, text=" × ").pack(side="left")
        self._cap_h = ttk.Entry(cap_frame, width=7)
        self._cap_h.pack(side="left")

        ttk.Label(f, text="Preview Resolution:").grid(
            row=2, column=0, sticky="w", pady=3
        )
        prev_frame = ttk.Frame(f)
        prev_frame.grid(row=2, column=1, sticky="w")
        self._prev_w = ttk.Entry(prev_frame, width=7)
        self._prev_w.pack(side="left")
        ttk.Label(prev_frame, text=" × ").pack(side="left")
        self._prev_h = ttk.Entry(prev_frame, width=7)
        self._prev_h.pack(side="left")

        return f

    # ---- 保存タブ --------------------------------------------------------

    def _build_tab_save(self, parent: ttk.Notebook) -> ttk.Frame:
        """保存タブのウィジェットを構築する。

        Args:
            parent: 追加先の Notebook。

        Returns:
            構築したタブフレーム。
        """
        f = ttk.Frame(parent, padding=12)

        ttk.Label(f, text="Save Folder:").grid(row=0, column=0, sticky="w", pady=3)
        path_frame = ttk.Frame(f)
        path_frame.grid(row=0, column=1, sticky="ew")
        self._save_path = ttk.Entry(path_frame, width=28)
        self._save_path.pack(side="left")
        ttk.Button(path_frame, text="…", width=3, command=self._browse_save_path).pack(
            side="left", padx=(4, 0)
        )

        ttk.Label(f, text="PNG Compression (0–9):").grid(
            row=1, column=0, sticky="w", pady=3
        )
        self._png_compression = tk.IntVar(value=1)
        scale_frame = ttk.Frame(f)
        scale_frame.grid(row=1, column=1, sticky="w")
        ttk.Scale(
            scale_frame,
            from_=0,
            to=9,
            orient="horizontal",
            variable=self._png_compression,
            length=160,
        ).pack(side="left")
        ttk.Label(scale_frame, textvariable=self._png_compression, width=3).pack(
            side="left"
        )

        self._filename_fmt = self._labeled_entry(f, "Filename Format:", 2)
        ttk.Label(
            f, text="  e.g. %Y%m%d_%H%M%S_{ms:03d}_{device}", foreground="gray"
        ).grid(row=3, column=0, columnspan=2, sticky="w")

        return f

    # ---- オプションタブ -----------------------------------------------------

    def _build_tab_options(self, parent: ttk.Notebook) -> ttk.Frame:
        """オプションタブのウィジェットを構築する。

        Args:
            parent: 追加先の Notebook。

        Returns:
            構築したタブフレーム。
        """
        f = ttk.Frame(parent, padding=12)

        self._daily_folder = tk.BooleanVar()
        ttk.Checkbutton(
            f, text="Create daily sub-folder (YYYY-MM-DD)", variable=self._daily_folder
        ).grid(row=0, column=0, sticky="w", pady=4)

        self._device_subfolder = tk.BooleanVar()
        ttk.Checkbutton(
            f,
            text="Create sub-folder per device label",
            variable=self._device_subfolder,
        ).grid(row=1, column=0, sticky="w", pady=4)

        self._beep_on_trigger = tk.BooleanVar()
        ttk.Checkbutton(
            f,
            text="Beep on trigger  (要 beep-lite: uv sync --extra audio)",
            variable=self._beep_on_trigger,
        ).grid(row=2, column=0, sticky="w", pady=4)

        return f

    # ------------------------------------------------------------------
    # 設定値を各ウィジェットへ反映
    # ------------------------------------------------------------------

    def _populate(self, cfg: AppConfig) -> None:
        """設定値を各ウィジェットへ反映する。

        Args:
            cfg: 反映する設定値。
        """
        # PLC設定
        self._plc_ip.delete(0, "end")
        self._plc_ip.insert(0, cfg.plc.ip)
        self._plc_port.delete(0, "end")
        self._plc_port.insert(0, str(cfg.plc.port))
        self._plc_type.set(cfg.plc.plc_type)
        self._plc_protocol.set(cfg.plc.protocol)
        self._plc_poll.delete(0, "end")
        self._plc_poll.insert(0, str(cfg.plc.poll_interval_ms))

        # デバイス設定
        self._refresh_device_tree()

        # カメラ設定
        self._cam_index.delete(0, "end")
        self._cam_index.insert(0, str(cfg.camera.index))
        self._cap_w.delete(0, "end")
        self._cap_w.insert(0, str(cfg.camera.capture_width))
        self._cap_h.delete(0, "end")
        self._cap_h.insert(0, str(cfg.camera.capture_height))
        self._prev_w.delete(0, "end")
        self._prev_w.insert(0, str(cfg.camera.preview_width))
        self._prev_h.delete(0, "end")
        self._prev_h.insert(0, str(cfg.camera.preview_height))

        # 保存設定
        self._save_path.delete(0, "end")
        self._save_path.insert(0, cfg.save.save_path)
        self._png_compression.set(cfg.save.png_compression)
        self._filename_fmt.delete(0, "end")
        self._filename_fmt.insert(0, cfg.save.filename_format)

        # オプション設定
        self._daily_folder.set(cfg.save.daily_folder)
        self._device_subfolder.set(cfg.save.device_subfolder)
        self._beep_on_trigger.set(cfg.save.beep_on_trigger)

    # ------------------------------------------------------------------
    # デバイスリスト操作
    # ------------------------------------------------------------------

    def _refresh_device_tree(self) -> None:
        """デバイスツリーを ``self._devices`` の内容で再描画する。"""
        for item in self._dev_tree.get_children():
            self._dev_tree.delete(item)
        for dev in self._devices:
            self._dev_tree.insert(
                "",
                "end",
                values=(dev.address, dev.label, "Yes" if dev.enabled else "No"),
            )

    def _dev_add(self) -> None:
        """デバイス追加ダイアログを開き、結果をリストへ追記する。"""
        dlg = _DeviceEditDialog(self, DeviceConfig())
        if dlg.result:
            self._devices.append(dlg.result)
            self._refresh_device_tree()

    def _dev_edit(self) -> None:
        """選択中のデバイスを編集ダイアログで更新する。"""
        sel = self._dev_tree.selection()
        if not sel:
            return
        idx = self._dev_tree.index(sel[0])
        dlg = _DeviceEditDialog(self, self._devices[idx])
        if dlg.result:
            self._devices[idx] = dlg.result
            self._refresh_device_tree()

    def _dev_delete(self) -> None:
        """選択中のデバイスをリストから削除する。"""
        sel = self._dev_tree.selection()
        if not sel:
            return
        idx = self._dev_tree.index(sel[0])
        self._devices.pop(idx)
        self._refresh_device_tree()

    def _dev_toggle(self) -> None:
        """選択中のデバイスの有効／無効を切り替える。"""
        sel = self._dev_tree.selection()
        if not sel:
            return
        idx = self._dev_tree.index(sel[0])
        self._devices[idx].enabled = not self._devices[idx].enabled
        self._refresh_device_tree()

    # ------------------------------------------------------------------
    # フォルダ参照
    # ------------------------------------------------------------------

    def _browse_save_path(self) -> None:
        """フォルダ選択ダイアログを開き、保存先パスを更新する。"""
        initial = self._save_path.get() or str(Path.home())
        folder = filedialog.askdirectory(
            parent=self, initialdir=initial, title="Select save folder"
        )
        if folder:
            self._save_path.delete(0, "end")
            self._save_path.insert(0, folder)

    # ------------------------------------------------------------------
    # OK / キャンセル
    # ------------------------------------------------------------------

    def _on_ok(self) -> None:
        """入力値を検証して AppConfig を生成し、ダイアログを閉じる。

        Raises:
            ValueError: IPアドレス・ポート番号などの入力値が不正な場合。
                エラーはキャッチされメッセージボックスで通知される。
        """
        try:
            ip_str = self._plc_ip.get().strip()
            try:
                ipaddress.ip_address(ip_str)
            except ValueError:
                raise ValueError(f"Invalid IP address: {ip_str!r}") from None

            port_val = int(self._plc_port.get())
            if not (1 <= port_val <= 65535):
                raise ValueError(f"Port must be 1\u201365535 (got {port_val})")

            plc = PlcConfig(
                ip=ip_str,
                port=port_val,
                plc_type=self._plc_type.get(),
                protocol=self._plc_protocol.get(),
                poll_interval_ms=int(self._plc_poll.get()),
                devices=list(self._devices),
            )
            camera = CameraConfig(
                index=int(self._cam_index.get()),
                capture_width=int(self._cap_w.get()),
                capture_height=int(self._cap_h.get()),
                preview_width=int(self._prev_w.get()),
                preview_height=int(self._prev_h.get()),
            )
            save = SaveConfig(
                save_path=self._save_path.get().strip(),
                png_compression=self._png_compression.get(),
                filename_format=self._filename_fmt.get().strip(),
                daily_folder=self._daily_folder.get(),
                device_subfolder=self._device_subfolder.get(),
                beep_on_trigger=self._beep_on_trigger.get(),
            )
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc), parent=self)
            return

        self.result = AppConfig(plc=plc, camera=camera, save=save)
        self.destroy()

    def _on_cancel(self) -> None:
        """変更を破棄してダイアログを閉じる。"""
        self.result = None
        self.destroy()

    # ------------------------------------------------------------------
    # ユーティリティ
    # ------------------------------------------------------------------

    @staticmethod
    def _labeled_entry(parent: ttk.Frame, label: str, row: int) -> ttk.Entry:
        """ラベルとエントリをグリッドに配置して返す。

        Args:
            parent: 配置先のフレーム。
            label: ラベルテキスト。
            row: グリッド行番号。

        Returns:
            生成した Entry ウィジェット。
        """
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(parent, width=22)
        entry.grid(row=row, column=1, sticky="w", pady=3)
        return entry


# ---------------------------------------------------------------------------
# デバイス追加/編集サブダイアログ
# ---------------------------------------------------------------------------


class _DeviceEditDialog(tk.Toplevel):
    """デバイスの追加／編集を行うサブダイアログ。

    OKボタン押下後は ``self.result`` に :class:`~config.DeviceConfig` が格納される。
    キャンセル時は ``None``。
    """

    def __init__(self, parent: tk.Misc, dev: DeviceConfig) -> None:
        """デバイス編集ダイアログを初期化する。

        Args:
            parent: 親ウィジェット。
            dev: 編集対象のデバイス設定。新規追加時はデフォルト値を渡す。
        """
        super().__init__(parent)
        self.title("Edit Device")
        self.resizable(False, False)
        self.result: DeviceConfig | None = None

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Device Address:").grid(row=0, column=0, sticky="w", pady=4)
        self._address = ttk.Entry(f, width=18)
        self._address.insert(0, dev.address)
        self._address.grid(row=0, column=1, pady=4)

        ttk.Label(f, text="Label:").grid(row=1, column=0, sticky="w", pady=4)
        self._label = ttk.Entry(f, width=18)
        self._label.insert(0, dev.label)
        self._label.grid(row=1, column=1, pady=4)

        self._enabled = tk.BooleanVar(value=dev.enabled)
        ttk.Checkbutton(f, text="Enabled", variable=self._enabled).grid(
            row=2, column=0, columnspan=2, sticky="w"
        )

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=8).pack(
            side="right", padx=4
        )
        ttk.Button(btn_frame, text="Cancel", command=self.destroy, width=8).pack(
            side="right"
        )

        if isinstance(parent, tk.Wm):
            self.transient(parent)
        self.grab_set()

    def _on_ok(self) -> None:
        """入力値を検証して DeviceConfig を生成し、ダイアログを閉じる。"""
        addr = self._address.get().strip()
        lbl = self._label.get().strip()
        if not addr:
            messagebox.showerror(
                "Invalid input", "Device address cannot be empty.", parent=self
            )
            return
        self.result = DeviceConfig(
            address=addr, label=lbl or addr, enabled=self._enabled.get()
        )
        self.destroy()
