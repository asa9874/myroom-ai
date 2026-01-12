"""
Flask 애플리케이션 팩토리

이 모듈은 Flask 애플리케이션을 생성하고 초기화하는 팩토리 함수를 제공합니다.
"""

import os
import logging
import json
from datetime import datetime
from flask import Flask, request
from flask_cors import CORS
from flask_restx import Api
from config import config


def create_app(config_name=None):
    """
    Flask 애플리케이션 팩토리 함수
    
    Args:
        config_name (str): 설정 이름 ('development', 'production', 'testing')
                          None인 경우 환경 변수 FLASK_ENV를 사용하거나 'default' 사용
    
    Returns:
        Flask: 초기화된 Flask 애플리케이션 인스턴스
    """
    # 설정 이름 결정
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'default')
    
    # Flask 앱 생성
    app = Flask(__name__)
    
    # 설정 로드
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # CORS 설정 (모든 도메인에서 접근 허용)
    CORS(app, resources={
        r"/api/*": {
            "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type"]
        }
    })
    
    # 로깅 설정
    setup_logging(app)
    
    # API 요청/응답 로깅 미들웨어 추가
    setup_api_logging(app)
    
    # Flask-RESTX API 초기화
    api = Api(
        app,
        version=app.config['API_VERSION'],
        title=app.config['API_TITLE'],
        description=app.config['API_DESCRIPTION'],
        doc='/docs',  # Swagger UI 경로
        prefix='/api'  # API 기본 경로 (v1 제거 - recommendation 라우트와 매칭)
    )
    
    # 라우트 등록
    register_routes(api)
    
    # 에러 핸들러 등록
    register_error_handlers(app)
    
    # 애플리케이션 컨텍스트에 API 저장 (다른 모듈에서 접근 가능)
    app.api = api
    
    app.logger.info(f'MyRoom AI 애플리케이션이 {config_name} 모드로 시작되었습니다.')
    
    return app


def setup_logging(app):
    """
    로깅 설정
    
    Args:
        app (Flask): Flask 애플리케이션 인스턴스
    """
    # 로그 레벨 설정
    log_level = getattr(logging, app.config['LOG_LEVEL'].upper(), logging.INFO)
    
    # 로그 포맷 설정
    formatter = logging.Formatter(app.config['LOG_FORMAT'])
    
    # 콘솔 핸들러 설정
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # 파일 핸들러 설정 (API 로그)
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    
    file_handler = logging.FileHandler(os.path.join(log_dir, 'app.log'))
    file_handler.setFormatter(formatter)
    
    # Flask 앱 로거 설정
    app.logger.setLevel(log_level)
    app.logger.addHandler(console_handler)
    app.logger.addHandler(file_handler)


def setup_api_logging(app):
    """
    API 요청/응답 로깅 미들웨어 설정
    
    Args:
        app (Flask): Flask 애플리케이션 인스턴스
    """
    # API 로그 파일 경로
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    api_log_path = os.path.join(log_dir, 'api.log')
    
    # API 로거 설정
    api_logger = logging.getLogger('api_logger')
    api_logger.setLevel(logging.INFO)
    
    # 파일 핸들러
    api_handler = logging.FileHandler(api_log_path)
    api_formatter = logging.Formatter(
        '%(asctime)s - [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    api_handler.setFormatter(api_formatter)
    
    # 콘솔 핸들러도 추가
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(api_formatter)
    
    api_logger.addHandler(api_handler)
    api_logger.addHandler(console_handler)
    
    @app.before_request
    def log_request():
        """요청 로깅"""
        if request.path.startswith('/api'):
            # 요청 정보 수집
            request.start_time = datetime.now()
            
            # 요청 데이터
            if request.is_json:
                request_data = request.get_json()
            elif request.method == 'GET':
                request_data = dict(request.args)
            elif request.form:
                request_data = dict(request.form)
            else:
                request_data = {}
            
            # 요청 로그 작성
            log_message = {
                'type': 'REQUEST',
                'timestamp': datetime.now().isoformat(),
                'method': request.method,
                'path': request.path,
                'url': request.url,
                'remote_addr': request.remote_addr,
                'data': request_data if request_data else 'No data'
            }
            api_logger.info(json.dumps(log_message, ensure_ascii=False, indent=2))
    
    @app.after_request
    def log_response(response):
        """응답 로깅"""
        if request.path.startswith('/api'):
            # 응답 시간 계산
            duration = None
            if hasattr(request, 'start_time'):
                duration = (datetime.now() - request.start_time).total_seconds()
            
            # 응답 데이터 수집
            try:
                response_data = response.get_json() if response.is_json else response.get_data(as_text=True)
            except Exception:
                response_data = 'Unable to parse response'
            
            # 응답 로그 작성
            log_message = {
                'type': 'RESPONSE',
                'timestamp': datetime.now().isoformat(),
                'status_code': response.status_code,
                'duration_seconds': duration,
                'content_type': response.content_type,
                'data': response_data
            }
            api_logger.info(json.dumps(log_message, ensure_ascii=False, indent=2))
        
        return response


def register_routes(api):
    """
    API 라우트 등록
    
    Args:
        api (Api): Flask-RESTX API 인스턴스
    """
    from app.routes.health import ns as health_ns
    from app.routes.recommendation import api as recommendation_ns
    from app.routes.recommendation import init_recommendation_system
    
    # 네임스페이스 추가
    api.add_namespace(health_ns, path='/health')
    api.add_namespace(recommendation_ns)
    
    # 추천 시스템 초기화
    try:
        init_recommendation_system()
    except Exception as e:
        api.logger.warning(f'추천 시스템 초기화 실패: {e}')


def register_error_handlers(app):
    """
    전역 에러 핸들러 등록
    
    Args:
        app (Flask): Flask 애플리케이션 인스턴스
    """
    
    @app.errorhandler(404)
    def not_found(error):
        """404 에러 핸들러"""
        return {'message': '요청한 리소스를 찾을 수 없습니다.'}, 404
    
    @app.errorhandler(500)
    def internal_error(error):
        """500 에러 핸들러"""
        app.logger.error(f'서버 내부 오류: {error}')
        return {'message': '서버 내부 오류가 발생했습니다.'}, 500
    
    @app.errorhandler(Exception)
    def handle_exception(error):
        """일반 예외 핸들러"""
        app.logger.error(f'처리되지 않은 예외: {error}', exc_info=True)
        return {'message': '예기치 않은 오류가 발생했습니다.'}, 500
