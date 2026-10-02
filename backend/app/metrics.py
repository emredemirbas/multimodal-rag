from __future__ import annotations

from collections import Counter
from threading import Lock


class Metrics:
    def __init__(self) -> None:
        self._counts: Counter[tuple[str, str]] = Counter()
        self._lock = Lock()
        self._chat_counts: Counter[str] = Counter()
        self._chat_duration = 0

    def observe_chat(self, abstained: bool, duration_ms: int) -> None:
        with self._lock:
            self._chat_counts["abstained" if abstained else "answered"] += 1
            self._chat_duration += duration_ms

    def observe_request(self, method: str, route: str, status: int) -> None:
        method = method if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"} else "OTHER"
        route_label = route or "unmatched"
        with self._lock:
            self._counts[(f"{method} {route_label}", str(status))] += 1

    def render(self) -> str:
        lines = [
            "# HELP tutorial_http_requests_total HTTP requests handled.",
            "# TYPE tutorial_http_requests_total counter",
        ]
        with self._lock:
            for (route, status), count in sorted(self._counts.items()):
                safe_route = route.replace('"', '\\"')
                lines.append(
                    f'tutorial_http_requests_total{{route="{safe_route}",status="{status}"}} {count}'
                )
            lines.extend(["# TYPE tutorial_chat_turns_total counter", "# TYPE tutorial_chat_duration_ms_total counter"])
            for outcome, count in sorted(self._chat_counts.items()):
                lines.append(f'tutorial_chat_turns_total{{outcome="{outcome}"}} {count}')
            lines.append(f"tutorial_chat_duration_ms_total {self._chat_duration}")
        return "\n".join(lines) + "\n"
