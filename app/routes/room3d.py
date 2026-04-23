"""
Room3D RabbitMQ 연동/테스트 API
"""

import time
from typing import Any, Dict

from flask import current_app, request
from flask_restx import Namespace, Resource, fields

from app.utils.mq_monitor import get_mq_monitor
from app.utils.room3d_producer import (
    PLACEHOLDER_XML_URL_TEXT,
    Room3DRequestProducer,
    Room3DResponseProducer,
)

ns = Namespace("room3d", description="Room3D 연동 및 테스트 API", path="/room3d")

contract_model = ns.model(
    "Room3DContract",
    {
        "exchange": fields.String(description="Room3D exchange"),
        "requestQueue": fields.String(description="요청 queue"),
        "requestRoutingKey": fields.String(description="요청 routing key"),
        "responseQueue": fields.String(description="응답 queue"),
        "responseRoutingKey": fields.String(description="응답 routing key"),
        "placeholderXmlText": fields.String(description="임시 xmlFileUrl 텍스트"),
    },
)

room3d_message_model = ns.model(
    "Room3DMessage",
    {
        "room3dId": fields.Raw(description="Room3D 식별자"),
        "memberId": fields.Raw(description="회원 식별자"),
        "status": fields.String(description="SUCCESS 또는 FAILED"),
        "xmlFileUrl": fields.Raw(description="XML URL 또는 null"),
        "message": fields.String(description="상세 메시지"),
        "timestamp": fields.Integer(description="unix timestamp (ms)"),
    },
)

room3d_overview_model = ns.model(
    "Room3DOverview",
    {
        "success": fields.Boolean(description="성공 여부"),
        "connections": fields.List(fields.Raw, description="Room3D 관련 연결 상태"),
        "events": fields.List(fields.Raw, description="Room3D 관련 이벤트"),
    },
)


def _coerce_int(value: Any, default_value: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default_value)


def _build_request_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    now_ms = int(time.time() * 1000)
    room3d_id = _coerce_int(payload.get("room3dId"), now_ms % 1_000_000)
    member_id = _coerce_int(payload.get("memberId"), 1)

    drawing_image_url = str(
        payload.get("drawingImageUrl")
        or "https://asa-room.s3.amazonaws.com/room3d/images/sample-drawing.png"
    ).strip()
    room_name = str(payload.get("roomName") or "테스트 방").strip()

    description = payload.get("description")
    if description is not None:
        description = str(description)

    return {
        "room3dId": room3d_id,
        "memberId": member_id,
        "drawingImageUrl": drawing_image_url,
        "roomName": room_name,
        "description": description,
        "timestamp": _coerce_int(payload.get("timestamp"), now_ms),
    }


def _build_response_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    now_ms = int(time.time() * 1000)
    status = str(payload.get("status") or "SUCCESS").upper()
    if status not in {"SUCCESS", "FAILED"}:
        raise ValueError("status는 SUCCESS 또는 FAILED만 허용됩니다")

    room3d_id = _coerce_int(payload.get("room3dId"), now_ms % 1_000_000)
    member_id = _coerce_int(payload.get("memberId"), 1)
    message = str(payload.get("message") or ("completed" if status == "SUCCESS" else "failed"))

    xml_file_url = None
    if status == "SUCCESS":
        xml_file_url = current_app.config.get("ROOM3D_XML_PLACEHOLDER_TEXT", PLACEHOLDER_XML_URL_TEXT)

    return {
        "room3dId": room3d_id,
        "memberId": member_id,
        "status": status,
        "xmlFileUrl": xml_file_url,
        "message": message,
        "timestamp": _coerce_int(payload.get("timestamp"), now_ms),
    }


@ns.route("/contract")
class Room3DContract(Resource):
    @ns.doc("get_room3d_contract")
    @ns.marshal_with(contract_model)
    def get(self):
        """Room3D RabbitMQ 계약 정보"""
        return {
            "exchange": current_app.config["ROOM3D_EXCHANGE"],
            "requestQueue": current_app.config["ROOM3D_REQUEST_QUEUE"],
            "requestRoutingKey": current_app.config["ROOM3D_REQUEST_ROUTING_KEY"],
            "responseQueue": current_app.config["ROOM3D_RESPONSE_QUEUE"],
            "responseRoutingKey": current_app.config["ROOM3D_RESPONSE_ROUTING_KEY"],
            "placeholderXmlText": current_app.config.get("ROOM3D_XML_PLACEHOLDER_TEXT", PLACEHOLDER_XML_URL_TEXT),
        }


@ns.route("/overview")
class Room3DOverview(Resource):
    @ns.doc("get_room3d_overview")
    @ns.marshal_with(room3d_overview_model)
    def get(self):
        """Room3D 관련 MQ 연결/이벤트 조회"""
        limit = request.args.get("limit", default=120, type=int)
        limit = max(20, min(limit, 500))

        monitor = get_mq_monitor()
        snapshot = monitor.get_overview(limit=limit)

        connections = [
            item for item in snapshot.get("connections", [])
            if str(item.get("queue", "")).startswith("room3d.")
        ]
        events = [
            item for item in snapshot.get("events", [])
            if "room3d." in str(item.get("queue", ""))
        ]

        return {
            "success": True,
            "connections": connections,
            "events": events,
        }


@ns.route("/test/publish-request")
class Room3DPublishRequest(Resource):
    @ns.doc("publish_room3d_request")
    def post(self):
        """Room3D 요청 메시지 테스트 발행"""
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return {"success": False, "message": "JSON 객체를 요청 본문으로 보내주세요."}, 400

        message = _build_request_message(payload)
        producer = Room3DRequestProducer(current_app.config)
        success = producer.send_room3d_request(message)
        if not success:
            return {
                "success": False,
                "message": "Room3D 요청 메시지 발행에 실패했습니다.",
                "request": message,
            }, 500

        return {
            "success": True,
            "message": "Room3D 요청 메시지 발행 완료",
            "request": message,
        }, 200


@ns.route("/test/publish-response")
class Room3DPublishResponse(Resource):
    @ns.doc("publish_room3d_response")
    @ns.marshal_with(room3d_message_model)
    def post(self):
        """Room3D 응답 메시지 테스트 발행"""
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            ns.abort(400, "JSON 객체를 요청 본문으로 보내주세요.")

        try:
            message = _build_response_message(payload)
        except ValueError as exc:
            ns.abort(400, str(exc))

        producer = Room3DResponseProducer(current_app.config)
        success = producer.send_room3d_response(message)
        if not success:
            ns.abort(500, "Room3D 응답 메시지 발행에 실패했습니다.")

        return message
