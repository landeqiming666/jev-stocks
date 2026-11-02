"""pytest 公共配置：按平台标记自动跳过。

平台判断只在 sentinel.platform 里，本文件不得自行判断平台。
"""

from __future__ import annotations

import pytest

from sentinel import platform as platform_layer


def pytest_collection_modifyitems(config, items):
    current = platform_layer.name()
    for item in items:
        for marker, target in (("macos", "macos"), ("windows", "windows")):
            if item.get_closest_marker(marker) and current != target:
                item.add_marker(pytest.mark.skip(reason=f"只在 {target} 上运行"))
