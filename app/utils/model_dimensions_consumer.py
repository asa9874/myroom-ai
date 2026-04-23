"""
가구 치수 이미지 추출 RabbitMQ Consumer

요청 큐에서 model3d_id/member_id/image_url을 받아 Gemini로 치수를 추출하고
응답 큐로 결과를 발행합니다.
"""

import json
import logging
import time
from threading import Thread
from typing import Any, Dict

import pika
from flask import Flask

from .model_dimensions_extractor import ModelDimensionsExtractor
from .model_dimensions_producer import ModelDimensionsProducer
from .mq_monitor import get_mq_monitor

logger = logging.getLogger(__name__)


class ModelDimensionsConsumer:
    """치수 추출 요청 큐 Consumer"""

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
        self.request_queue = config["DIMENSIONS_REQUEST_QUEUE"]
        self.request_routing_key = config["DIMENSIONS_REQUEST_ROUTING_KEY"]
        self.response_queue = config["DIMENSIONS_RESPONSE_QUEUE"]
        self.response_routing_key = config["DIMENSIONS_RESPONSE_ROUTING_KEY"]

        self.connection = None
        self.channel = None
        self.monitor = get_mq_monitor()
        self.producer = ModelDimensionsProducer(config)
        self.extractor = ModelDimensionsExtractor(config)

    def connect(self):
        """RabbitMQ 연결 및 큐 설정"""
        try:
            self.connection = pika.BlockingConnection(self.parameters)
            self.channel = self.connection.channel()

            self.channel.exchange_declare(
                exchange=self.exchange,
                exchange_type="topic",
                durable=True,
            )

            self.channel.queue_declare(queue=self.request_queue, durable=True)
            self.channel.queue_bind(
                exchange=self.exchange,
                queue=self.request_queue,
                routing_key=self.request_routing_key,
            )

            self.channel.queue_declare(queue=self.response_queue, durable=True)
            self.channel.queue_bind(
                exchange=self.exchange,
                queue=self.response_queue,
                routing_key=self.response_routing_key,
            )

            self.channel.basic_qos(prefetch_count=1)

            self.monitor.record_connection(
                queue=self.request_queue,
                connected=True,
                component="model_dimensions_consumer",
            )
            self.monitor.record_connection(
                queue=self.response_queue,
                connected=True,
                component="model_dimensions_consumer",
                detail="response queue bound",
            )

            logger.info("[SUCCESS] 치수 Consumer RabbitMQ 연결 성공: %s", self.request_queue)
        except Exception as exc:
            self.monitor.record_connection(
                queue=self.request_queue,
                connected=False,
                component="model_dimensions_consumer",
                detail=str(exc),
            )
            logger.error("[FAILED] 치수 Consumer RabbitMQ 연결 실패: %s", exc, exc_info=True)
            raise

    def start_consuming(self):
        """메시지 수신 시작"""
        if self.channel is None:
            raise RuntimeError("ModelDimensionsConsumer.connect()를 먼저 호출해야 합니다")

        logger.info("[*] 치수 추출 요청 수신 대기 중: %s", self.request_queue)
        self.channel.basic_consume(
            queue=self.request_queue,
            on_message_callback=self.callback,
            auto_ack=False,
        )
        self.channel.start_consuming()

    def callback(self, ch, method, properties, body):
        """메시지 콜백"""
        raw_payload = body.decode("utf-8", errors="replace")
        self.monitor.record_event(
            queue=self.request_queue,
            direction="IN",
            details=raw_payload[:1500],
        )

        message: Dict[str, Any] = {}
        try:
            message = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            logger.error("치수 요청 JSON 파싱 오류: %s", exc)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        try:
            model3d_id = message.get("model3d_id")
            member_id = message.get("member_id")
            image_url = message.get("image_url")

            if model3d_id is None:
                raise ValueError("model3d_id는 필수입니다")
            if member_id is None:
                raise ValueError("member_id는 필수입니다")
            if not image_url:
                raise ValueError("image_url은 필수입니다")

            dimensions = self.extractor.extract_dimensions(str(image_url))

            response_message = {
                "model3d_id": int(model3d_id),
                "member_id": int(member_id),
                "status": "SUCCESS",
                "message": "completed",
                "timestamp": int(time.time() * 1000),
                "dimensions": dimensions,
            }

            published = self.producer.send_dimensions_response(response_message)
            if published:
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.info("[COMPLETE] 치수 추출 처리 완료: model3d_id=%s", model3d_id)
            else:
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        except Exception as exc:
            logger.error("치수 추출 처리 실패: %s", exc, exc_info=True)
            failed = self._send_failed_response(message=message, reason=str(exc))
            if failed:
                ch.basic_ack(delivery_tag=method.delivery_tag)
            else:
                # 필수 ID가 없는 잘못된 메시지는 재처리해도 실패하므로 재큐하지 않습니다.
                has_ids = message.get("model3d_id") is not None and message.get("member_id") is not None
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=bool(has_ids))

    def _send_failed_response(self, message: Dict[str, Any], reason: str) -> bool:
        try:
            model3d_id = message.get("model3d_id")
            member_id = message.get("member_id")
            if model3d_id is None or member_id is None:
                logger.warning("FAILED 응답 생략: model3d_id/member_id 누락")
                return False

            response_message = {
                "model3d_id": int(model3d_id),
                "member_id": int(member_id),
                "status": "FAILED",
                "message": reason[:300],
                "timestamp": int(time.time() * 1000),
            }
            return self.producer.send_dimensions_response(response_message)
        except Exception as exc:
            logger.error("FAILED 응답 발행 처리 중 오류: %s", exc, exc_info=True)
            return False

    def close(self):
        """연결 종료"""
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
            self.monitor.record_connection(
                queue=self.request_queue,
                connected=False,
                component="model_dimensions_consumer",
                detail="closed",
            )
            self.monitor.record_connection(
                queue=self.response_queue,
                connected=False,
                component="model_dimensions_consumer",
                detail="closed",
            )
        except Exception as exc:
            logger.error("치수 Consumer 종료 중 오류: %s", exc)


def start_model_dimensions_consumer_thread(app: Flask):
    """치수 Consumer 백그라운드 실행"""

    def consumer_loop():
        with app.app_context():
            retry_count = 0
            max_retries = 5

            while retry_count < max_retries:
                consumer = None
                try:
                    consumer = ModelDimensionsConsumer(app.config)
                    consumer.connect()
                    consumer.start_consuming()
                    return
                except Exception as exc:
                    retry_count += 1
                    logger.error("치수 Consumer 실행 중 오류: %s", exc, exc_info=True)
                    if consumer is not None:
                        consumer.close()

                    if retry_count < max_retries:
                        logger.info("치수 Consumer 재연결 시도 (%s/%s)", retry_count, max_retries)
                        time.sleep(5)
                    else:
                        logger.error("치수 Consumer 최대 재연결 시도 횟수 초과")

    thread = Thread(
        target=consumer_loop,
        daemon=True,
        name="ModelDimensionsConsumer",
    )
    thread.start()
    logger.info("치수 Consumer 스레드 시작됨")
    return thread
