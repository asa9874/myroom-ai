"""
헬스 체크 API

서버의 상태를 확인하는 간단한 API 엔드포인트
"""

from flask import current_app
from flask_restx import Namespace, Resource, fields
from datetime import datetime


# 네임스페이스 생성
ns = Namespace('health', description='헬스 체크 관련 API')

# 응답 모델 정의
health_model = ns.model('Health', {
    'status': fields.String(required=True, description='서버 상태', example='healthy'),
    'timestamp': fields.String(required=True, description='응답 시간', example='2026-01-08T12:00:00'),
    'version': fields.String(required=True, description='API 버전', example='1.0')
})


@ns.route('/')
class HealthCheck(Resource):
    """헬스 체크 리소스"""
    
    @ns.doc('health_check')
    @ns.marshal_with(health_model)
    @ns.response(200, '성공')
    def get(self):
        """
        서버 헬스 체크
        
        서버가 정상적으로 동작하는지 확인합니다.
        """
        return {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': current_app.config['API_VERSION']
        }


@ns.route('/ping')
class Ping(Resource):
    """핑 리소스"""
    
    @ns.doc('ping')
    @ns.response(200, '성공')
    def get(self):
        """
        핑 테스트
        
        간단한 핑 요청에 응답합니다.
        """
        return {'message': 'pong'}
