"""Camera capture thread — continuous preview frames + high-res PNG save."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from config import AppConfig, CameraConfig, SaveConfig


class CameraThread(threading.Thread):
    """Background thread that continuously grabs frames from a USB camera.

    Usage
    -----
    1. Construct and start the thread.
    2. Call :meth:`get_preview_frame` from the GUI thread to get the latest
       down-scaled preview frame (numpy BGR array or ``None`` if not ready).
    3. Call :meth:`capture_hires` to save a full-resolution PNG and get its
       :class:`~pathlib.Path`.
    4. Call :meth:`stop` to terminate the thread gracefully.
    """

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__(daemon=True, name="CameraThread")
        self._cam_cfg: CameraConfig = cfg.camera
        self._save_cfg: SaveConfig = cfg.save
        self._stop_event = threading.Event()

        # The latest captured raw frame (at capture resolution or whatever the
        # camera provides), protected by a lock.
        self._frame_lock = threading.Lock()
        self._frame: np.ndarray | None = None  # type: ignore[type-arg]

        # Capture lock — prevents concurrent high-res captures
        self._capture_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Signal the thread to stop."""
        self._stop_event.set()

    def update_config(self, cfg: AppConfig) -> None:
        """Hot-update camera and save config."""
        self._cam_cfg = cfg.camera
        self._save_cfg = cfg.save

    def get_preview_frame(self) -> np.ndarray | None:  # type: ignore[type-arg]
        """Return the latest preview-sized BGR frame, or ``None``."""
        with self._frame_lock:
            if self._frame is None:
                return None
            pw, ph = self._cam_cfg.preview_width, self._cam_cfg.preview_height
            return cv2.resize(self._frame, (pw, ph), interpolation=cv2.INTER_LINEAR)

    def capture_hires(self, device_label: str = "manual") -> Path | None:
        """Save the current high-res frame to PNG and return the file path.

        Returns ``None`` if no frame is available yet.
        """
        with self._capture_lock, self._frame_lock:
            frame = None if self._frame is None else self._frame.copy()

        if frame is None:
            return None

        save_path = self._build_save_path(device_label)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        params = [cv2.IMWRITE_PNG_COMPRESSION, self._save_cfg.png_compression]
        cv2.imwrite(str(save_path), frame, params)
        return save_path

    # ------------------------------------------------------------------
    # Thread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        while not self._stop_event.is_set():
            cap = self._open_camera()
            if cap is None:
                self._stop_event.wait(timeout=3.0)
                continue
            self._capture_loop(cap)
            cap.release()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _open_camera(self) -> cv2.VideoCapture | None:
        cap = cv2.VideoCapture(self._cam_cfg.index, cv2.CAP_ANY)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._cam_cfg.capture_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cam_cfg.capture_height)
        return cap

    def _capture_loop(self, cap: cv2.VideoCapture) -> None:
        while not self._stop_event.is_set():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.1)
                break
            with self._frame_lock:
                self._frame = frame

    def _build_save_path(self, device_label: str) -> Path:
        now = datetime.now()
        ms = now.microsecond // 1000
        safe_label = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in device_label
        )

        filename = (
            now.strftime(self._save_cfg.filename_format).format(
                ms=ms, device=safe_label
            )
            + ".png"
        )

        base = Path(self._save_cfg.save_path)
        if self._save_cfg.daily_folder:
            base = base / now.strftime("%Y-%m-%d")
        if self._save_cfg.device_subfolder:
            base = base / safe_label
        return base / filename
