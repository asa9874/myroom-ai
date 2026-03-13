"""RabbitMQ 모니터링 API"""

from flask import request
from flask_restx import Namespace, Resource, fields

from app.utils.mq_monitor import get_mq_monitor

ns = Namespace('mq-monitor', description='RabbitMQ 연결 상태 및 메시지 이벤트 모니터링 API')

connection_model = ns.model('MqConnection', {
    'queue': fields.String(description='큐 이름'),
    'connected': fields.Boolean(description='연결 여부'),
    'component': fields.String(description='연결 컴포넌트'),
    'detail': fields.String(description='추가 상세'),
    'updated_at': fields.String(description='마지막 갱신 시각(ISO)')
})

event_model = ns.model('MqEvent', {
    'id': fields.Integer(description='이벤트 ID'),
    'timestamp': fields.String(description='이벤트 시각(ISO)'),
    'queue': fields.String(description='큐 이름'),
    'direction': fields.String(description='IN 또는 OUT'),
    'summary': fields.String(description='요약'),
    'details': fields.Raw(description='상세 데이터')
})

generation_model = ns.model('GenerationItem', {
    'job_id': fields.String(description='작업 ID'),
    'status': fields.String(description='processing/completed/failed'),
    'member_id': fields.Raw(description='회원 ID'),
    'model3d_id': fields.Raw(description='모델 ID'),
    'input_image_url': fields.String(description='입력 이미지 URL'),
    'input_image_urls': fields.List(fields.String(description='멀티뷰 입력 이미지 URL 목록')),
    'input_image_path': fields.String(description='저장된 입력 이미지 경로'),
    'model3d_path': fields.String(description='생성된 모델 파일 경로'),
    'model3d_url': fields.String(description='생성된 모델 URL'),
    'settings': fields.Raw(description='생성 시점 설정값'),
    'message': fields.String(description='상태 메시지'),
    'created_at': fields.String(description='생성 시각'),
    'updated_at': fields.String(description='갱신 시각')
})

overview_model = ns.model('MqOverview', {
    'success': fields.Boolean(description='성공 여부'),
    'connections': fields.List(fields.Nested(connection_model)),
    'events': fields.List(fields.Nested(event_model)),
    'generations': fields.List(fields.Nested(generation_model)),
})


@ns.route('/overview')
class MqOverview(Resource):
    @ns.doc('get_mq_overview')
    @ns.marshal_with(overview_model)
    def get(self):
        """RabbitMQ 연결 상태 + 이벤트 조회"""
        limit = request.args.get('limit', default=50, type=int)
        monitor = get_mq_monitor()
        snapshot = monitor.get_overview(limit=limit)
        return {
            'success': True,
            'connections': snapshot['connections'],
            'events': snapshot['events'],
            'generations': snapshot['generations'],
        }
