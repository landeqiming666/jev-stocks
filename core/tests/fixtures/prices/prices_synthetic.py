"""确定性合成数据只服务于测试，不冒充真实录制。"""

from datetime import date, timedelta
from random import Random


def generate(start: date, count: int, seed: int = 4) -> dict[str, object]:
    random = Random(seed)
    rows = []
    day = start
    while len(rows) < count:
        if day.weekday() < 5:
            close = round(10 + random.random(), 2)
            rows.append([day.isoformat(), "10", str(close), "12", "9", "100"])
        day += timedelta(days=1)
    return {"synthetic": True, "code": 0, "data": {"usZZAR": {"day": rows}}}
