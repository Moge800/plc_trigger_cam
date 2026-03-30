"""Configuration dataclasses and JSON persistence for PLC Trigger Camera."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent / "config.json"

# ---------------------------------------------------------------------------
# PLC types and protocol types
# ---------------------------------------------------------------------------
PLC_TYPES = ["Q", "L", "QnA", "iQ-L", "iQ-R"]
PROTOCOL_TYPES = ["3E", "4E"]


# ---------------------------------------------------------------------------
# Sub-config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DeviceConfig:
    """A single PLC bit device to monitor."""

    address: str = "M100"
    label: str = "Trigger"
    enabled: bool = True


@dataclass
class PlcConfig:
    """PLC connection settings."""

    ip: str = "192.168.1.10"
    port: int = 1025
    plc_type: str = "Q"  # one of PLC_TYPES
    protocol: str = "3E"  # "3E" or "4E"
    poll_interval_ms: int = 100  # polling interval in milliseconds
    devices: list[DeviceConfig] = field(default_factory=lambda: [DeviceConfig()])


@dataclass
class CameraConfig:
    """USB camera settings."""

    index: int = 0
    capture_width: int = 1920
    capture_height: int = 1080
    preview_width: int = 640
    preview_height: int = 480


@dataclass
class SaveConfig:
    """Image save settings."""

    save_path: str = str(Path.home() / "Pictures" / "plc_trigger_cam")
    png_compression: int = 1  # 0=fastest/largest … 9=slowest/smallest
    filename_format: str = "%Y%m%d_%H%M%S_{ms:03d}_{device}"
    daily_folder: bool = True  # create YYYY-MM-DD sub-folder
    device_subfolder: bool = False  # create sub-folder per device label


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


@dataclass
class AppConfig:
    """Root application config."""

    plc: PlcConfig = field(default_factory=PlcConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    save: SaveConfig = field(default_factory=SaveConfig)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _plc_from_dict(d: dict) -> PlcConfig:  # type: ignore[type-arg]
    devices = [DeviceConfig(**dev) for dev in d.pop("devices", [])]
    return PlcConfig(**d, devices=devices)


def config_from_dict(d: dict) -> AppConfig:  # type: ignore[type-arg]
    plc = _plc_from_dict(d.get("plc", {}))
    camera = CameraConfig(**d.get("camera", {}))
    save = SaveConfig(**d.get("save", {}))
    return AppConfig(plc=plc, camera=camera, save=save)


def load_config(path: Path = CONFIG_FILE) -> AppConfig:
    """Load config from *path*; return defaults if file does not exist."""
    if not path.exists():
        return AppConfig()
    try:
        with path.open(encoding="utf-8") as fh:
            raw = json.load(fh)
        return config_from_dict(raw)
    except Exception:
        return AppConfig()


def save_config(cfg: AppConfig, path: Path = CONFIG_FILE) -> None:
    """Persist *cfg* to *path* as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(asdict(cfg), fh, indent=2, ensure_ascii=False)
