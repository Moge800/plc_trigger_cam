"""Settings dialog — tabbed configuration UI for PLC Trigger Camera."""

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
    """Modal settings dialog with tabbed layout.

    After the user presses OK, ``self.result`` contains the updated
    :class:`~config.AppConfig`; on Cancel it is ``None``.
    """

    def __init__(self, parent: tk.Misc, cfg: AppConfig) -> None:
        super().__init__(parent)
        self.title("Settings")
        self.resizable(False, False)
        self.result: AppConfig | None = None

        # Working copies
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
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
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

        # Bottom buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(
            side="right", padx=4
        )
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel, width=10).pack(
            side="right"
        )

    # ---- PLC tab ---------------------------------------------------------

    def _build_tab_plc(self, parent: ttk.Notebook) -> ttk.Frame:
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

    # ---- Devices tab -----------------------------------------------------

    def _build_tab_devices(self, parent: ttk.Notebook) -> ttk.Frame:
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

    # ---- Camera tab ------------------------------------------------------

    def _build_tab_camera(self, parent: ttk.Notebook) -> ttk.Frame:
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

    # ---- Save tab --------------------------------------------------------

    def _build_tab_save(self, parent: ttk.Notebook) -> ttk.Frame:
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

    # ---- Options tab -----------------------------------------------------

    def _build_tab_options(self, parent: ttk.Notebook) -> ttk.Frame:
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

        return f

    # ------------------------------------------------------------------
    # Populate from config
    # ------------------------------------------------------------------

    def _populate(self, cfg: AppConfig) -> None:
        # PLC
        self._plc_ip.delete(0, "end")
        self._plc_ip.insert(0, cfg.plc.ip)
        self._plc_port.delete(0, "end")
        self._plc_port.insert(0, str(cfg.plc.port))
        self._plc_type.set(cfg.plc.plc_type)
        self._plc_protocol.set(cfg.plc.protocol)
        self._plc_poll.delete(0, "end")
        self._plc_poll.insert(0, str(cfg.plc.poll_interval_ms))

        # Devices
        self._refresh_device_tree()

        # Camera
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

        # Save
        self._save_path.delete(0, "end")
        self._save_path.insert(0, cfg.save.save_path)
        self._png_compression.set(cfg.save.png_compression)
        self._filename_fmt.delete(0, "end")
        self._filename_fmt.insert(0, cfg.save.filename_format)

        # Options
        self._daily_folder.set(cfg.save.daily_folder)
        self._device_subfolder.set(cfg.save.device_subfolder)

    # ------------------------------------------------------------------
    # Device list management
    # ------------------------------------------------------------------

    def _refresh_device_tree(self) -> None:
        for item in self._dev_tree.get_children():
            self._dev_tree.delete(item)
        for dev in self._devices:
            self._dev_tree.insert(
                "",
                "end",
                values=(dev.address, dev.label, "Yes" if dev.enabled else "No"),
            )

    def _dev_add(self) -> None:
        dlg = _DeviceEditDialog(self, DeviceConfig())
        if dlg.result:
            self._devices.append(dlg.result)
            self._refresh_device_tree()

    def _dev_edit(self) -> None:
        sel = self._dev_tree.selection()
        if not sel:
            return
        idx = self._dev_tree.index(sel[0])
        dlg = _DeviceEditDialog(self, self._devices[idx])
        if dlg.result:
            self._devices[idx] = dlg.result
            self._refresh_device_tree()

    def _dev_delete(self) -> None:
        sel = self._dev_tree.selection()
        if not sel:
            return
        idx = self._dev_tree.index(sel[0])
        self._devices.pop(idx)
        self._refresh_device_tree()

    def _dev_toggle(self) -> None:
        sel = self._dev_tree.selection()
        if not sel:
            return
        idx = self._dev_tree.index(sel[0])
        self._devices[idx].enabled = not self._devices[idx].enabled
        self._refresh_device_tree()

    # ------------------------------------------------------------------
    # Browse helpers
    # ------------------------------------------------------------------

    def _browse_save_path(self) -> None:
        initial = self._save_path.get() or str(Path.home())
        folder = filedialog.askdirectory(
            parent=self, initialdir=initial, title="Select save folder"
        )
        if folder:
            self._save_path.delete(0, "end")
            self._save_path.insert(0, folder)

    # ------------------------------------------------------------------
    # OK / Cancel
    # ------------------------------------------------------------------

    def _on_ok(self) -> None:
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
            )
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc), parent=self)
            return

        self.result = AppConfig(plc=plc, camera=camera, save=save)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _labeled_entry(parent: ttk.Frame, label: str, row: int) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(parent, width=22)
        entry.grid(row=row, column=1, sticky="w", pady=3)
        return entry


# ---------------------------------------------------------------------------
# Device add/edit sub-dialog
# ---------------------------------------------------------------------------


class _DeviceEditDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, dev: DeviceConfig) -> None:
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
