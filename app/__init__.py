import os
import sys
from pathlib import Path


def _set_default_env_path(name: str, path: Path, *, replace_system_drive: bool = False) -> None:
    current = os.environ.get(name, "")
    if not current or (replace_system_drive and Path(current).drive.upper() == "C:"):
        os.environ[name] = str(path)
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)


ROOT_DIR = Path(__file__).resolve().parents[1]
STORAGE_DIR = ROOT_DIR / "storage"
CACHE_DIR = STORAGE_DIR / "cache"
TEMP_DIR = STORAGE_DIR / "temp"

_set_default_env_path("TMP", TEMP_DIR, replace_system_drive=True)
_set_default_env_path("TEMP", TEMP_DIR, replace_system_drive=True)
_set_default_env_path("TMPDIR", TEMP_DIR, replace_system_drive=True)
_set_default_env_path("XDG_CACHE_HOME", CACHE_DIR / "xdg")
_set_default_env_path("HF_HOME", CACHE_DIR / "huggingface")
_set_default_env_path("HUGGINGFACE_HUB_CACHE", CACHE_DIR / "huggingface" / "hub")
_set_default_env_path("TRANSFORMERS_CACHE", CACHE_DIR / "huggingface" / "transformers")
_set_default_env_path("HF_DATASETS_CACHE", CACHE_DIR / "huggingface" / "datasets")
_set_default_env_path("TORCH_HOME", CACHE_DIR / "torch")
_set_default_env_path("MPLCONFIGDIR", CACHE_DIR / "matplotlib")
_set_default_env_path("PIP_CACHE_DIR", CACHE_DIR / "pip")
_set_default_env_path("YOLO_CONFIG_DIR", CACHE_DIR / "yolo")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
