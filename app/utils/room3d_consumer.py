"""
Room3D RabbitMQ Consumer

Room3D 요청 메시지를 수신하고 응답 메시지를 발행합니다.
"""

import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from io import BytesIO
from threading import Thread
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import pika
import requests
from flask import Flask
from PIL import Image

from .mq_monitor import get_mq_monitor
from .room3d_producer import Room3DResponseProducer
from .s3_manager import S3Manager

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
                room3d_id=room3d_id,
                member_id=member_id,
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
        room3d_id: int,
        member_id: int,
        drawing_image_url: str,
        room_name: str,
        description: Optional[str] = None,
    ) -> Optional[str]:
        api_url = str(self.config.get("ROOM3D_FLOORPLAN_API_URL", "http://localhost:5001/")).strip()
        if not api_url:
            raise ValueError("ROOM3D_FLOORPLAN_API_URL 설정이 필요합니다")

        download_timeout = int(self.config.get("ROOM3D_IMAGE_DOWNLOAD_TIMEOUT", 30))
        api_timeout = int(self.config.get("ROOM3D_FLOORPLAN_API_TIMEOUT", 90))
        xml_prefix = str(self.config.get("ROOM3D_XML_S3_PREFIX", "room3d/xml")).strip("/")

        image_bytes, filename, content_type = self._download_drawing_image(
            drawing_image_url=drawing_image_url,
            timeout=download_timeout,
        )

        payload = self._call_floorplan_api(
            api_url=api_url,
            image_bytes=image_bytes,
            filename=filename,
            content_type=content_type,
            timeout=api_timeout,
        )

        xml_bytes = self._build_room3d_xml(
            payload=payload,
            room_name=room_name,
            description=description,
            drawing_image_url=drawing_image_url,
        )

        s3_manager = S3Manager(self.config)
        if not s3_manager.is_available():
            logger.error("Room3D XML 업로드 실패: S3 사용 불가")
            return None

        timestamp_ms = int(time.time() * 1000)
        s3_key = f"{xml_prefix}/member_{member_id}/room3d_{room3d_id}_{timestamp_ms}.xml"
        success, s3_url = s3_manager.upload_bytes(
            data=xml_bytes,
            s3_key=s3_key,
            content_type="application/xml",
        )
        if not success:
            logger.error("Room3D XML 업로드 실패: %s", s3_url)
            return None

        return s3_url

    def _download_drawing_image(self, drawing_image_url: str, timeout: int) -> Tuple[bytes, str, str]:
        response = requests.get(drawing_image_url, timeout=timeout)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "application/octet-stream")
        filename = os.path.basename(urlparse(drawing_image_url).path) or "drawing"

        try:
            image = Image.open(BytesIO(response.content))
            rgb_image = image.convert("RGB")
            buffer = BytesIO()
            rgb_image.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()
        except Exception as exc:
            raise ValueError("도면 이미지를 RGB로 변환하지 못했습니다") from exc

        base_name = os.path.splitext(filename)[0] or "drawing"
        filename = f"{base_name}.png"
        content_type = "image/png"

        return image_bytes, filename, content_type

    def _call_floorplan_api(
        self,
        api_url: str,
        image_bytes: bytes,
        filename: str,
        content_type: str,
        timeout: int,
    ) -> Dict[str, Any]:
        if not api_url.endswith("/"):
            api_url = f"{api_url}/"

        response = requests.post(
            api_url,
            files={"image": (filename, image_bytes, content_type)},
            timeout=timeout,
        )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("FloorPlanTo3D API 응답이 JSON 형식이 아닙니다") from exc

        if not isinstance(payload, dict):
            raise ValueError("FloorPlanTo3D API 응답이 객체가 아닙니다")

        return payload

    def _build_room3d_xml(
        self,
        payload: Dict[str, Any],
        room_name: str,
        description: Optional[str],
        drawing_image_url: str,
    ) -> bytes:
        root = ET.Element("FloorPlan")
        metadata = ET.SubElement(root, "Metadata")
        metadata.set("roomName", room_name)
        metadata.set("sourceImageUrl", drawing_image_url)
        if description:
            metadata.set("description", description)

        image_meta = ET.SubElement(root, "Image")
        width = payload.get("Width")
        height = payload.get("Height")
        average_door = payload.get("averageDoor")
        if width is not None:
            image_meta.set("width", str(width))
        if height is not None:
            image_meta.set("height", str(height))
        if average_door is not None:
            image_meta.set("averageDoor", str(average_door))

        objects = ET.SubElement(root, "Objects")
        points = payload.get("points") or []
        classes = payload.get("classes") or []

        for index, point in enumerate(points):
            if not isinstance(point, dict):
                continue

            obj = ET.SubElement(objects, "Object")
            obj.set("index", str(index))

            class_name = ""
            if index < len(classes):
                class_item = classes[index]
                if isinstance(class_item, dict):
                    class_name = str(class_item.get("name") or "")
                else:
                    class_name = str(class_item)

            if class_name:
                obj.set("type", class_name)

            for key in ("x1", "y1", "x2", "y2"):
                if key in point:
                    obj.set(key, str(point[key]))

        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def _guess_extension(content_type: str) -> str:
        content_type = content_type.lower()
        if "jpeg" in content_type:
            return ".jpg"
        if "png" in content_type:
            return ".png"
        if "gif" in content_type:
            return ".gif"
        if "webp" in content_type:
            return ".webp"
        return ".img"

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
