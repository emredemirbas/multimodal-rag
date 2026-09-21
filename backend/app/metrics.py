from __future__ import annotations

from collections import Counter
from threading import Lock


class Metrics:
    def __init__(self) -> None:
        self._counts: Counter[tuple[str, str]] = Counter()
        self._lock = Lock()

    def observe_request(self, method: str, route: str, status: int) -> None:
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
        return "\n".join(lines) + "\n"
