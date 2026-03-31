"""PLCトリガーカメラの設定データクラスおよびJSON永続化。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent / "config.json"

# ---------------------------------------------------------------------------
# PLCタイプとプロトコルタイプ
# ---------------------------------------------------------------------------
PLC_TYPES = ["Q", "L", "QnA", "iQ-L", "iQ-R"]
PROTOCOL_TYPES = ["3E", "4E"]


# ---------------------------------------------------------------------------
# サブ設定データクラス
# ---------------------------------------------------------------------------


@dataclass
class DeviceConfig:
    """監視対象の PLC ビットデバイスの設定。

    Attributes:
        address: デバイスアドレス（例: ``M100``）。
        label: 表示ラベル。
        enabled: 有効フラグ。
    """

    address: str = "M100"
    label: str = "Trigger"
    enabled: bool = True


@dataclass
class PlcConfig:
    """接続先 PLC の設定。

    Attributes:
        ip: PLC の IP アドレス。
        port: 接続ポート番号。
        plc_type: PLCタイプ（:data:`PLC_TYPES` のいずれか）。
        protocol: 通信プロトコル（``"3E"`` または ``"4E"``）。
        poll_interval_ms: ポーリング間隔（ミリ秒）。
        devices: 監視対象デバイスのリスト。
    """

    ip: str = "192.168.1.10"
    port: int = 1025
    plc_type: str = "Q"  # PLC_TYPES のいずれか
    protocol: str = "3E"  # "3E" または "4E"
    poll_interval_ms: int = 100  # ポーリング間隔（ミリ秒）
    devices: list[DeviceConfig] = field(default_factory=lambda: [DeviceConfig()])


@dataclass
class CameraConfig:
    """USBカメラの設定。

    Attributes:
        index: OpenCVカメラインデックス。
        capture_width: キャプチャ解像度の幅。
        capture_height: キャプチャ解像度の高さ。
        preview_width: プレビュー解像度の幅。
        preview_height: プレビュー解像度の高さ。
    """

    index: int = 0
    capture_width: int = 1920
    capture_height: int = 1080
    preview_width: int = 640
    preview_height: int = 480


@dataclass
class SaveConfig:
    """画像保存の設定。

    Attributes:
        save_path: 保存先ディレクトリのパス。
        png_compression: PNG圧縮レベル（0=最速/最大 … 9=最遅/最小）。
        filename_format: ファイル名フォーマット（strftime + {ms}, {device}）。
        daily_folder: ``True`` の場合は YYYY-MM-DD サブフォルダを作成。
        device_subfolder: ``True`` の場合はデバイスラベルごとのサブフォルダを作成。
        beep_on_trigger: ``True`` の場合はトリガー時に通知音を再生する（beep-lite 必須）。
    """

    save_path: str = str(Path.home() / "Pictures" / "plc_trigger_cam")
    png_compression: int = 1  # 0=最速/最大サイズ … 9=最遅/最小サイズ
    filename_format: str = "%Y%m%d_%H%M%S_{ms:03d}_{device}"
    daily_folder: bool = True  # YYYY-MM-DD サブフォルダを作成
    device_subfolder: bool = False  # デバイスラベルごとのサブフォルダを作成
    beep_on_trigger: bool = False  # トリガー時に通知音を再生


# ---------------------------------------------------------------------------
# ルート設定
# ---------------------------------------------------------------------------


@dataclass
class AppConfig:
    """アプリケーションのルート設定。

    Attributes:
        plc: PLC接続設定。
        camera: カメラ設定。
        save: 保存設定。
    """

    plc: PlcConfig = field(default_factory=PlcConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    save: SaveConfig = field(default_factory=SaveConfig)


# ---------------------------------------------------------------------------
# シリアライズヘルパー
# ---------------------------------------------------------------------------


def _plc_from_dict(d: dict) -> PlcConfig:  # type: ignore[type-arg]
    """dict から :class:`PlcConfig` を生成するプライベートヘルパー。

    Args:
        d: ``"devices"`` キーを含む可能性のある辞書。

    Returns:
        復元された :class:`PlcConfig` インスタンス。
    """
    d = d.copy()
    devices = [DeviceConfig(**dev) for dev in d.pop("devices", [])]
    return PlcConfig(**d, devices=devices)


def config_from_dict(d: dict) -> AppConfig:  # type: ignore[type-arg]
    """dict から :class:`AppConfig` を生成する。

    Args:
        d: JSON読み込み結果の辞書。

    Returns:
        復元された :class:`AppConfig` インスタンス。
    """
    plc = _plc_from_dict(d.get("plc", {}))
    camera = CameraConfig(**d.get("camera", {}))
    save = SaveConfig(**d.get("save", {}))
    return AppConfig(plc=plc, camera=camera, save=save)


def load_config(path: Path = CONFIG_FILE) -> AppConfig:
    """*path* から設定を読み込む。ファイルが存在しない場合はデフォルト値を返す。

    Args:
        path: 設定JSONファイルのパス。

    Returns:
        読み込んだ :class:`AppConfig`。パース失敗時はデフォルト値。
    """
    if not path.exists():
        return AppConfig()
    try:
        with path.open(encoding="utf-8") as fh:
            raw = json.load(fh)
        return config_from_dict(raw)
    except Exception:
        return AppConfig()


def save_config(cfg: AppConfig, path: Path = CONFIG_FILE) -> None:
    """*cfg* を *path* に JSON として保存する。

    Args:
        cfg: 保存する設定値。
        path: 保存先の JSON ファイルパス。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(asdict(cfg), fh, indent=2, ensure_ascii=False)
