"""外置依赖的动态导入无法被冻结分析发现，显式保留 Windows 可用标准库。"""
import importlib.util
import json
import sys


def modules():
    excluded = {"antigravity", "this", "tkinter", "turtle", "turtledemo", "idlelib", "test", "ensurepip", "venv"}
    return sorted(name for name in sys.stdlib_module_names
                  if name not in excluded and not name.startswith("_") and importlib.util.find_spec(name) is not None)


if __name__ == '__main__':
    print(json.dumps(modules()))
