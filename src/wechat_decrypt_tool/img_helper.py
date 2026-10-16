import ctypes
import os
from pathlib import Path
from typing import Optional
from .logging_config import get_logger

logger = get_logger(__name__)


class ImgHelper:
    def __init__(self):
        self._lib: Optional[ctypes.CDLL] = None
        self._enabled = False
        self._lock = __import__("threading").Lock()

    @staticmethod
    def _resolve_dll_path() -> Path:
        # 1. Default (source code layout)
        base = Path(__file__).resolve().parent
        path = base / "native" / "img_helper.dll"
        if path.exists():
            return path

        # 2. Frozen (bundled exe)
        import sys
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            # Try native subfolder or same folder as exe
            for p in [exe_dir / "native" / "img_helper.dll", exe_dir / "img_helper.dll"]:
                if p.exists():
                    return p

        # 3. Current working directory
        for p in [Path.cwd() / "native" / "img_helper.dll", Path.cwd() / "img_helper.dll"]:
            if p.exists():
                return p

        return path  # Fallback to default for error message

    def _load_lib(self):
        if self._lib is not None:
            return self._lib

        dll_path = self._resolve_dll_path()
        if not dll_path.exists():
            raise FileNotFoundError(f"Missing img_helper.dll at: {dll_path}")

        try:
            # On Windows, ensure the DLL's directory is in the search path for dependencies
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(str(dll_path.parent))
                except Exception:
                    pass

            lib = ctypes.CDLL(str(dll_path))

            lib.InitImgHelper.argtypes = [ctypes.c_uint32]
            lib.InitImgHelper.restype = ctypes.c_bool

            lib.UninstallImgHelper.argtypes = []
            lib.UninstallImgHelper.restype = None

            lib.GetImgHelperError.argtypes = []
            lib.GetImgHelperError.restype = ctypes.c_char_p

            self._lib = lib
            return lib
        except Exception as e:
            logger.error(f"Failed to load img_helper.dll: {e}")
            raise

    def enable(self, pid: int) -> tuple[bool, str]:
        with self._lock:
            try:
                lib = self._load_lib()
                if self._enabled:
                    # If already enabled, we uninstall first to be safe as per DLL docs suggestion
                    # about being designed to hook one process at a time.
                    lib.UninstallImgHelper()

                if lib.InitImgHelper(pid):
                    self._enabled = True
                    logger.info(f"ImgHelper hook applied to PID {pid}")
                    return True, "Success"
                else:
                    err_ptr = lib.GetImgHelperError()
                    err_msg = err_ptr.decode('utf-8', errors='ignore') if err_ptr else "Unknown error"
                    logger.error(f"ImgHelper hook failed: {err_msg}")
                    return False, err_msg
            except Exception as e:
                logger.error(f"ImgHelper enable exception: {e}")
                return False, str(e)

    def disable(self) -> bool:
        with self._lock:
            if not self._enabled:
                return True
            try:
                lib = self._load_lib()
                lib.UninstallImgHelper()
                self._enabled = False
                logger.info("ImgHelper hook uninstalled")
                return True
            except Exception as e:
                logger.error(f"Failed to uninstall img helper: {e}")
                return False

    @property
    def is_enabled(self) -> bool:
        return self._enabled


IMG_HELPER = ImgHelper()
