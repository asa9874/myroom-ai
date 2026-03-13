"""
RabbitMQ 상태/이벤트 모니터링 저장소
"""

from collections import deque
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional


class RabbitMQMonitor:
    def __init__(self, max_events: int = 300):
        self._lock = Lock()
        self._connections: Dict[str, Dict[str, Any]] = {}
        self._events = deque(maxlen=max_events)
        self._event_seq = 0

    def record_connection(self, queue: str, connected: bool, component: str, detail: str = "") -> None:
        now = datetime.now().isoformat()
        with self._lock:
            self._connections[queue] = {
                "queue": queue,
                "connected": bool(connected),
                "component": component,
                "detail": detail,
                "updated_at": now,
            }

    def record_event(
        self,
        queue: str,
        direction: str,
        details: Optional[Any] = None,
        summary: Optional[str] = None,
    ) -> None:
        now = datetime.now().isoformat()
        normalized_direction = "IN" if str(direction).upper() == "IN" else "OUT"

        with self._lock:
            self._event_seq += 1
            event = {
                "id": self._event_seq,
                "timestamp": now,
                "queue": queue,
                "direction": normalized_direction,
                "summary": summary,
                "details": details,
            }
            self._events.appendleft(event)

    def get_connections(self) -> List[Dict[str, Any]]:
        with self._lock:
            return sorted(self._connections.values(), key=lambda item: item.get("queue", ""))

    def get_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._events)[: max(1, limit)]

    def get_overview(self, limit: int = 50) -> Dict[str, Any]:
        return {
            "connections": self.get_connections(),
            "events": self.get_events(limit=limit),
        }


_mq_monitor = RabbitMQMonitor()


def get_mq_monitor() -> RabbitMQMonitor:
    return _mq_monitor
