"""
애플리케이션 설정 파일

이 파일은 Flask 애플리케이션의 모든 설정을 중앙에서 관리합니다.
환경별로 다른 설정을 사용할 수 있도록 구성되어 있습니다.
"""

import os
from datetime import timedelta


class Config:
    """기본 설정 클래스"""
    
    # Flask 기본 설정
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-this-in-production'
    
    # API 설정
    API_TITLE = 'MyRoom AI API'
    API_VERSION = '1.0'
    API_DESCRIPTION = 'MyRoom AI REST API 서버'
    
    # CORS 설정
    CORS_HEADERS = 'Content-Type'
    
    # Swagger UI 설정
    SWAGGER_UI_DOC_EXPANSION = 'list'  # 'none', 'list', 'full'
    RESTX_MASK_SWAGGER = False  # Swagger UI에서 모든 필드 표시
    
    # 업로드 설정
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB 최대 파일 크기
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    
    # 로깅 설정
    LOG_LEVEL = os.environ.get('LOG_LEVEL') or 'INFO'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # RabbitMQ 설정
    RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST') or 'localhost'
    RABBITMQ_PORT = int(os.environ.get('RABBITMQ_PORT') or 5672)
    RABBITMQ_USERNAME = os.environ.get('RABBITMQ_USERNAME') or 'guest'
    RABBITMQ_PASSWORD = os.environ.get('RABBITMQ_PASSWORD') or 'guest'
    RABBITMQ_QUEUE = 'model3d.upload.queue'
    
    # 3D 모델 저장 경로
    MODEL3D_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads', 'models')
    
    # 데이터베이스 설정 (필요시 활성화)
    # SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///myroom.db'
    # SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    @staticmethod
    def init_app(app):
        """애플리케이션 초기화 시 호출되는 메서드"""
        # 업로드 폴더가 없으면 생성
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        # 3D 모델 폴더가 없으면 생성
        os.makedirs(Config.MODEL3D_FOLDER, exist_ok=True)


class DevelopmentConfig(Config):
    """개발 환경 설정"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """프로덕션 환경 설정"""
    DEBUG = False
    TESTING = False
    
    # 프로덕션에서는 반드시 환경 변수에서 SECRET_KEY를 가져와야 함
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        
        # 프로덕션 환경에서 SECRET_KEY가 설정되지 않은 경우 경고
        if not cls.SECRET_KEY:
            raise ValueError("프로덕션 환경에서는 SECRET_KEY 환경 변수를 설정해야 합니다.")


class TestingConfig(Config):
    """테스트 환경 설정"""
    DEBUG = True
    TESTING = True


# 환경별 설정 매핑
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
