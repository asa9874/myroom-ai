"""
Room3D RabbitMQ Producer

Room3D 요청/응답 메시지 발행을 담당합니다.
"""

import json
import logging
import time
from typing import Any, Dict

import pika

from .mq_monitor import get_mq_monitor

logger = logging.getLogger(__name__)

PLACEHOLDER_XML_URL_TEXT = "이 텍스트는 임시텍스트입니다."


class _BaseRoom3DProducer:
    """Room3D RabbitMQ 발행 공통 로직"""

    def __init__(self, config):
        self.config = config
        self.credentials = pika.PlainCredentials(
            config["RABBITMQ_USERNAME"],
            config["RABBITMQ_PASSWORD"],
        )
        self.parameters = pika.ConnectionParameters(
            host=config["RABBITMQ_HOST"],
            port=config["RABBITMQ_PORT"],
            credentials=self.credentials,
            heartbeat=600,
            blocked_connection_timeout=300,
        )
        self.exchange = config["ROOM3D_EXCHANGE"]
        self.request_queue = config["ROOM3D_REQUEST_QUEUE"]
        self.request_routing_key = config["ROOM3D_REQUEST_ROUTING_KEY"]
        self.response_queue = config["ROOM3D_RESPONSE_QUEUE"]
        self.response_routing_key = config["ROOM3D_RESPONSE_ROUTING_KEY"]
        self.monitor = get_mq_monitor()

    def _declare_topology(self, channel) -> None:
        channel.exchange_declare(exchange=self.exchange, exchange_type="topic", durable=True)

        channel.queue_declare(queue=self.request_queue, durable=True)
        channel.queue_bind(
            exchange=self.exchange,
            queue=self.request_queue,
            routing_key=self.request_routing_key,
        )

        channel.queue_declare(queue=self.response_queue, durable=True)
        channel.queue_bind(
            exchange=self.exchange,
            queue=self.response_queue,
            routing_key=self.response_routing_key,
        )

    def _publish(self, routing_key: str, payload: Dict[str, Any]) -> bool:
        connection = None
        try:
            connection = pika.BlockingConnection(self.parameters)
            channel = connection.channel()
            self._declare_topology(channel)

            message = dict(payload)
            if "timestamp" not in message:
                message["timestamp"] = int(time.time() * 1000)

            channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=json.dumps(message, ensure_ascii=False),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                ),
            )

            self.monitor.record_event(
                queue=routing_key,
                direction="OUT",
                details=message,
            )
            return True
        except Exception as exc:
            logger.error("Room3D 메시지 발행 실패: %s", exc, exc_info=True)
            return False
        finally:
            if connection and not connection.is_closed:
                connection.close()


class Room3DRequestProducer(_BaseRoom3DProducer):
    """Room3D 요청 메시지 발행"""

    def send_room3d_request(self, request_message: Dict[str, Any]) -> bool:
        return self._publish(self.request_routing_key, request_message)


class Room3DResponseProducer(_BaseRoom3DProducer):
    """Room3D 응답 메시지 발행"""

    def send_room3d_response(self, response_message: Dict[str, Any]) -> bool:
        message = dict(response_message)
        status = str(message.get("status", "SUCCESS")).upper()
        message["status"] = status

        if status == "SUCCESS" and not message.get("xmlFileUrl"):
            message["xmlFileUrl"] = self.config.get("ROOM3D_XML_PLACEHOLDER_TEXT", PLACEHOLDER_XML_URL_TEXT)

        return self._publish(self.response_routing_key, message)
