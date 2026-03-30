"""PLC Trigger Camera — main application window."""

from __future__ import annotations

import os
import queue
import sys
import tkinter as tk
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

if TYPE_CHECKING:
    pass

# Interval between GUI refresh ticks (ms) — approximately 30 fps
_REFRESH_MS = 33

# For tkinter thread safety: events pumped between threads via this queue
_GUI_EVENT_QUEUE: Queue[TriggerEvent | StatusEvent | BitStateEvent] = Queue()

# Maximum lines in the capture log
_LOG_MAX_LINES = 500


# ---------------------------------------------------------------------------
# Status indicator widget
# ---------------------------------------------------------------------------


class _StatusLight(tk.Canvas):
    """A coloured circle indicator."""

    _RADIUS = 8
    _SIZE = _RADIUS * 2 + 4

    def __init__(self, parent: tk.Misc, **kwargs: Any) -> None:
        super().__init__(
            parent, width=self._SIZE, height=self._SIZE, highlightthickness=0, **kwargs
        )
        self._oval = self.create_oval(
            2, 2, self._SIZE - 2, self._SIZE - 2, fill="gray", outline=""
        )

    def set_color(self, color: str) -> None:
        self.itemconfig(self._oval, fill=color)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PLC Trigger Camera")
        self.resizable(True, True)

        self._cfg = load_config()
        self._simulate_mode = False
        self._closing = False

        # Background threads (started on connect)
        self._plc_monitor: PlcMonitor | None = None
        self._camera: CameraThread | None = None

        self._build_ui()
        self._apply_config_to_ui()
        self._start_camera()
        self._schedule_refresh()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._build_menu()
        self._build_toolbar()
        self._build_main_panel()
        self._build_status_bar()

    def _build_menu(self) -> None:
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

        # Simulation trigger button (only relevant in sim mode)
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
        self._sim_frame.pack_forget()  # hidden until sim mode enabled

    def _build_main_panel(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=4, pady=4)

        # --- Left: camera preview ---
        left = ttk.LabelFrame(paned, text="Camera Preview")
        paned.add(left, weight=3)

        self._preview_canvas = tk.Canvas(left, bg="black", width=640, height=480)
        self._preview_canvas.pack(fill="both", expand=True)
        self._preview_image_id = self._preview_canvas.create_image(0, 0, anchor="nw")
        self._preview_tk_img: ImageTk.PhotoImage | None = None

        # --- Right: status + log ---
        right = ttk.Frame(paned)
        paned.add(right, weight=1)

        # PLC connection panel
        plc_panel = ttk.LabelFrame(right, text="PLC Status")
        plc_panel.pack(fill="x", padx=4, pady=(0, 4))

        row = ttk.Frame(plc_panel)
        row.pack(fill="x", padx=6, pady=4)
        # ttk.LabelFrame does not support cget("background"); resolve via Style instead
        bg = ttk.Style().lookup("TFrame", "background") or "SystemButtonFace"
        self._plc_light = _StatusLight(row, bg=bg)
        self._plc_light.pack(side="left")
        self._plc_status_label = ttk.Label(row, text="Disconnected")
        self._plc_status_label.pack(side="left", padx=4)

        # Device state panel
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

        # Last capture info
        info_panel = ttk.LabelFrame(right, text="Last Capture")
        info_panel.pack(fill="x", padx=4, pady=(0, 4))
        self._last_capture_label = ttk.Label(info_panel, text="—", wraplength=260)
        self._last_capture_label.pack(padx=6, pady=4)

        # Capture log
        log_panel = ttk.LabelFrame(right, text="Capture Log")
        log_panel.pack(fill="both", expand=True, padx=4)
        self._log = scrolledtext.ScrolledText(
            log_panel, height=10, state="disabled", font=("Courier", 9)
        )
        self._log.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_status_bar(self) -> None:
        sb = ttk.Frame(self, relief="sunken")
        sb.pack(fill="x", side="bottom")
        self._status_bar_label = ttk.Label(sb, text="Ready", anchor="w")
        self._status_bar_label.pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # Config application
    # ------------------------------------------------------------------

    def _apply_config_to_ui(self) -> None:
        """Refresh device tree rows from config."""
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

        # Update simulation combo
        enabled_addrs = [d.address for d in self._cfg.plc.devices if d.enabled]
        self._sim_combo["values"] = enabled_addrs
        if enabled_addrs:
            self._sim_combo.current(0)

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def _start_camera(self) -> None:
        if self._camera:
            self._camera.stop()
        self._camera = CameraThread(self._cfg)
        self._camera.start()

    def _update_preview(self) -> None:
        if self._camera is None:
            return
        frame = self._camera.get_preview_frame()
        if frame is None:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)

        # Scale to fit canvas
        cw = self._preview_canvas.winfo_width() or self._cfg.camera.preview_width
        ch = self._preview_canvas.winfo_height() or self._cfg.camera.preview_height
        img.thumbnail((cw, ch), Image.Resampling.LANCZOS)

        self._preview_tk_img = ImageTk.PhotoImage(img)
        self._preview_canvas.itemconfig(
            self._preview_image_id, image=self._preview_tk_img
        )

    # ------------------------------------------------------------------
    # PLC connection
    # ------------------------------------------------------------------

    def _toggle_plc_connection(self) -> None:
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
        self._plc_monitor = PlcMonitor(
            self._cfg.plc, _GUI_EVENT_QUEUE, simulate=self._simulate_mode
        )
        self._plc_monitor.start()
        self._btn_connect.config(text="Disconnect PLC")
        self._set_status(f"Connecting to {self._cfg.plc.ip}:{self._cfg.plc.port}…")

    # ------------------------------------------------------------------
    # Simulation mode
    # ------------------------------------------------------------------

    def _toggle_simulation(self) -> None:
        self._simulate_mode = not self._simulate_mode
        if self._simulate_mode:
            self._sim_frame.pack(side="right", padx=2, pady=2)
            messagebox.showinfo(
                "Simulation Mode",
                "Simulation mode enabled.\nNo real PLC connection will be made.",
            )
        else:
            self._sim_frame.pack_forget()
        # Restart monitor with new mode if running
        if self._plc_monitor and self._plc_monitor.is_alive():
            self._plc_monitor.stop()
            self._plc_monitor.join(timeout=2.0)
            self._start_plc_monitor()

    def _sim_fire_trigger(self) -> None:
        addr = self._sim_combo.get()
        if addr and self._plc_monitor:
            self._plc_monitor.simulate_trigger(addr)

    # ------------------------------------------------------------------
    # Manual capture
    # ------------------------------------------------------------------

    def _manual_capture(self) -> None:
        self._do_capture("manual")

    def _do_capture(self, device_label: str) -> None:
        if self._camera is None:
            return
        path = self._camera.capture_hires(device_label)
        if path:
            self._log_capture(path, device_label)
            self._last_capture_label.config(text=str(path))
        else:
            self._set_status("Capture failed: no frame available.")

    def _log_capture(self, path: Path, device_label: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"[{ts}]  {device_label}  →  {path.name}\n"
        self._log.config(state="normal")
        self._log.insert("end", line)

        # Trim old lines
        lines = int(self._log.index("end-1c").split(".")[0])
        if lines > _LOG_MAX_LINES:
            self._log.delete("1.0", f"{lines - _LOG_MAX_LINES}.0")

        self._log.see("end")
        self._log.config(state="disabled")
        self._set_status(f"Captured: {path}")

    # ------------------------------------------------------------------
    # Settings dialog
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
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
    # Event processing from PLC monitor
    # ------------------------------------------------------------------

    def _process_plc_events(self) -> None:
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
        self._do_capture(event.label)

    def _handle_bit_state_event(self, event: BitStateEvent) -> None:
        for addr, state in event.states.items():
            try:
                tag = "on" if state else "off"
                self._dev_tree.set(addr, "state", "ON" if state else "OFF")
                self._dev_tree.item(addr, tags=(tag,))
            except tk.TclError:
                pass  # row may not exist if config was changed

    # ------------------------------------------------------------------
    # Main refresh loop
    # ------------------------------------------------------------------

    def _schedule_refresh(self) -> None:
        if self._closing:
            return
        self._update_preview()
        self._process_plc_events()
        self.after(_REFRESH_MS, self._schedule_refresh)

    # ------------------------------------------------------------------
    # Status bar helper
    # ------------------------------------------------------------------

    def _set_status(self, msg: str) -> None:
        self._status_bar_label.config(text=msg)

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        self._closing = True
        if self._plc_monitor:
            self._plc_monitor.stop()
        if self._camera:
            self._camera.stop()
        save_config(self._cfg)
        # Join with timeout — cv2 internal threads may block cap.read()
        if self._plc_monitor:
            self._plc_monitor.join(timeout=2.0)
        if self._camera:
            self._camera.join(timeout=2.0)
        self.destroy()
        os._exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    # Add src/ to sys.path so that sibling modules resolve when run via
    # `uv run src/main.py` (the CWD is the project root)
    src_dir = str(Path(__file__).parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
