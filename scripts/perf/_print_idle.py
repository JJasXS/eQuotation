import json
from pathlib import Path

idle = json.loads(Path("perf/results/idle_before.json").read_text(encoding="utf-8-sig"))
print("idle status", idle.get("status"), "min15", idle.get("minutes_15"), "min30", idle.get("minutes_30"))
print("visibility_triggered", idle.get("visibility_triggered_requests"))
for k, v in (idle.get("pages") or {}).items():
    print(f"  {k}: idle15={v.get('idle_requests_15')} idle30={v.get('idle_requests_30')}")
print("server_start", idle.get("server_start"))
print("server_30", idle.get("server_30"))
base = Path("perf/results/baseline_before.json")
print("baseline exists", base.is_file(), "bytes", base.stat().st_size if base.is_file() else 0)
