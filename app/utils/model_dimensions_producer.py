"""
가구 치수 추출 응답 RabbitMQ Producer
"""

import json
import logging
import time
from typing import Any, Dict

import pika

from .mq_monitor import get_mq_monitor

logger = logging.getLogger(__name__)


class ModelDimensionsProducer:
    """치수 추출 결과를 RabbitMQ 응답 큐로 발행"""

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
        self.exchange = config["DIMENSIONS_EXCHANGE"]
        self.response_queue = config["DIMENSIONS_RESPONSE_QUEUE"]
        self.response_routing_key = config["DIMENSIONS_RESPONSE_ROUTING_KEY"]
        self.monitor = get_mq_monitor()

    def send_dimensions_response(self, response_message: Dict[str, Any]) -> bool:
        """치수 추출 응답 메시지 발행"""
        connection = None
        try:
            connection = pika.BlockingConnection(self.parameters)
            channel = connection.channel()

            channel.exchange_declare(
                exchange=self.exchange,
                exchange_type="topic",
                durable=True,
            )

            channel.queue_declare(queue=self.response_queue, durable=True)
            channel.queue_bind(
                exchange=self.exchange,
                queue=self.response_queue,
                routing_key=self.response_routing_key,
            )

            message = dict(response_message)
            if "timestamp" not in message:
                message["timestamp"] = int(time.time() * 1000)

            message_body = json.dumps(message, ensure_ascii=False)
            channel.basic_publish(
                exchange=self.exchange,
                routing_key=self.response_routing_key,
                body=message_body,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                ),
            )

            self.monitor.record_event(
                queue=self.response_routing_key,
                direction="OUT",
                details=message,
            )

            logger.info(
                "[SUCCESS] 치수 응답 발행 완료: model3d_id=%s status=%s",
                message.get("model3d_id"),
                message.get("status"),
            )
            return True
        except Exception as exc:
            logger.error("[FAILED] 치수 응답 발행 실패: %s", exc, exc_info=True)
            return False
        finally:
            if connection and not connection.is_closed:
                connection.close()
