"""
Room3D RabbitMQ Consumer

Room3D 요청 메시지를 수신하고 응답 메시지를 발행합니다.
"""

import json
import logging
import time
from threading import Thread
from typing import Any, Dict, Optional

import pika
from flask import Flask

from .mq_monitor import get_mq_monitor
from .room3d_producer import Room3DResponseProducer

logger = logging.getLogger(__name__)


class Room3DConsumer:
    """Room3D 요청 큐 Consumer"""

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

        self.connection = None
        self.channel = None
        self.monitor = get_mq_monitor()
        self.response_producer = Room3DResponseProducer(config)

    def connect(self) -> None:
        """RabbitMQ 연결 및 큐/바인딩 설정"""
        try:
            self.connection = pika.BlockingConnection(self.parameters)
            self.channel = self.connection.channel()

            self.channel.exchange_declare(exchange=self.exchange, exchange_type="topic", durable=True)

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
                component="room3d_consumer",
            )
            self.monitor.record_connection(
                queue=self.response_queue,
                connected=True,
                component="room3d_consumer",
                detail="response queue bound",
            )

            logger.info("[SUCCESS] Room3D RabbitMQ 연결 성공 (queue=%s)", self.request_queue)
        except Exception as exc:
            self.monitor.record_connection(
                queue=self.request_queue,
                connected=False,
                component="room3d_consumer",
                detail=str(exc),
            )
            logger.error("[FAILED] Room3D RabbitMQ 연결 실패: %s", exc, exc_info=True)
            raise

    def start_consuming(self) -> None:
        """메시지 수신 시작"""
        if self.channel is None:
            raise RuntimeError("Room3DConsumer.connect()를 먼저 호출해야 합니다.")

        logger.info("[*] Room3D 요청 수신 대기 중: %s", self.request_queue)
        self.channel.basic_consume(
            queue=self.request_queue,
            on_message_callback=self.callback,
            auto_ack=False,
        )
        self.channel.start_consuming()

    def callback(self, ch, method, properties, body) -> None:
        """Room3D 메시지 콜백"""
        raw_payload = body.decode("utf-8", errors="replace")
        self.monitor.record_event(
            queue=self.request_queue,
            direction="IN",
            details=raw_payload[:1500],
        )

        try:
            message = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            logger.error("Room3D JSON 파싱 오류: %s", exc)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        response_sent = self._handle_room3d_request(message)
        if response_sent:
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def _handle_room3d_request(self, message: Dict[str, Any]) -> bool:
        """Room3D 요청 처리 후 응답 발행"""
        try:
            room3d_id = message.get("room3dId")
            member_id = message.get("memberId")
            drawing_image_url = message.get("drawingImageUrl")
            room_name = message.get("roomName")
            description = message.get("description")

            if room3d_id is None:
                raise ValueError("room3dId는 필수입니다")
            if member_id is None:
                raise ValueError("memberId는 필수입니다")
            if not drawing_image_url:
                raise ValueError("drawingImageUrl은 필수입니다")
            if not room_name:
                raise ValueError("roomName은 필수입니다")

            xml_file_url = self._convert_drawing_to_xml(
                drawing_image_url=drawing_image_url,
                room_name=room_name,
                description=description,
            )

            if not xml_file_url:
                xml_file_url = self.config.get("ROOM3D_XML_PLACEHOLDER_TEXT", "이 텍스트는 임시텍스트입니다.")

            response_message = {
                "room3dId": room3d_id,
                "memberId": member_id,
                "status": "SUCCESS",
                "xmlFileUrl": xml_file_url,
                "message": "completed",
                "timestamp": int(time.time() * 1000),
            }

            success = self.response_producer.send_room3d_response(response_message)
            if success:
                logger.info("[SUCCESS] Room3D 응답 발행 완료 room3dId=%s", room3d_id)
            return success

        except Exception as exc:
            logger.error("Room3D 요청 처리 실패: %s", exc, exc_info=True)
            fail_message = {
                "room3dId": message.get("room3dId"),
                "memberId": message.get("memberId"),
                "status": "FAILED",
                "xmlFileUrl": None,
                "message": str(exc),
                "timestamp": int(time.time() * 1000),
            }
            return self.response_producer.send_room3d_response(fail_message)

    def _convert_drawing_to_xml(
        self,
        drawing_image_url: str,
        room_name: str,
        description: Optional[str] = None,
    ) -> Optional[str]:
        # //TODO: 도면 이미지 -> XML 생성 AI 로직을 추후 이 함수에 구현할 예정입니다.
        _ = (drawing_image_url, room_name, description)
        return None

    def close(self) -> None:
        """연결 종료"""
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
            self.monitor.record_connection(
                queue=self.request_queue,
                connected=False,
                component="room3d_consumer",
                detail="closed",
            )
            self.monitor.record_connection(
                queue=self.response_queue,
                connected=False,
                component="room3d_consumer",
                detail="closed",
            )
        except Exception as exc:
            logger.error("Room3D Consumer 종료 중 오류: %s", exc)


def start_room3d_consumer_thread(app: Flask):
    """Room3D Consumer 백그라운드 실행"""

    def consumer_loop() -> None:
        retry_count = 0
        max_retries = 5

        with app.app_context():
            while retry_count < max_retries:
                consumer = None
                try:
                    consumer = Room3DConsumer(app.config)
                    consumer.connect()
                    consumer.start_consuming()
                    return
                except Exception as exc:
                    retry_count += 1
                    logger.error("Room3D Consumer 실행 중 오류: %s", exc, exc_info=True)
                    if consumer is not None:
                        consumer.close()

                    if retry_count < max_retries:
                        logger.info("Room3D Consumer 재연결 시도 (%s/%s)", retry_count, max_retries)
                        time.sleep(5)
                    else:
                        logger.error("Room3D Consumer 최대 재연결 시도 횟수 초과")

    consumer_thread = Thread(
        target=consumer_loop,
        daemon=True,
        name="Room3DConsumer",
    )
    consumer_thread.start()
    logger.info("Room3D Consumer 스레드 시작됨")
    return consumer_thread
