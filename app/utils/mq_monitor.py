"""
RabbitMQ 상태/이벤트 모니터링 저장소
"""

from collections import deque
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional


class RabbitMQMonitor:
    def __init__(self, max_events: int = 300, max_generations: int = 90):
        self._lock = Lock()
        self._connections: Dict[str, Dict[str, Any]] = {}
        self._events = deque(maxlen=max_events)
        self._event_seq = 0
        self._generation_seq = 0
        self._generations = deque(maxlen=max_generations)
        self._generation_map: Dict[str, Dict[str, Any]] = {}

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

    def start_generation(
        self,
        member_id: Any,
        model3d_id: Any,
        input_image_url: Optional[str] = None,
        input_image_urls: Optional[List[str]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        now = datetime.now().isoformat()
        with self._lock:
            self._generation_seq += 1
            job_id = f"gen-{self._generation_seq}"
            item = {
                "job_id": job_id,
                "status": "processing",
                "member_id": member_id,
                "model3d_id": model3d_id,
                "input_image_url": input_image_url,
                "input_image_urls": input_image_urls or ([] if input_image_url else []),
                "input_image_path": None,
                "model3d_path": None,
                "model3d_url": None,
                "settings": settings or {},
                "message": "3D 모델 생성 진행 중",
                "created_at": now,
                "updated_at": now,
            }
            self._generations.appendleft(item)
            self._generation_map[job_id] = item
            return job_id

    def update_generation(self, job_id: str, **patch: Any) -> None:
        now = datetime.now().isoformat()
        with self._lock:
            item = self._generation_map.get(job_id)
            if not item:
                return
            item.update(patch)
            item["updated_at"] = now

    def get_generations(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._generations)[: max(1, limit)]

    def get_overview(self, limit: int = 50) -> Dict[str, Any]:
        return {
            "connections": self.get_connections(),
            "events": self.get_events(limit=limit),
            "generations": self.get_generations(limit=min(max(1, limit), 30)),
        }


_mq_monitor = RabbitMQMonitor()


def get_mq_monitor() -> RabbitMQMonitor:
    return _mq_monitor
