"""
애플리케이션 설정 파일

이 파일은 Flask 애플리케이션의 모든 설정을 중앙에서 관리합니다.
환경별로 다른 설정을 사용할 수 있도록 구성되어 있습니다.
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


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
    
    # RabbitMQ Producer 설정 (Flask → Spring Boot)
    RABBITMQ_EXCHANGE = 'model3d.exchange'
    RABBITMQ_RESPONSE_ROUTING_KEY = 'model3d.response'
    
    # RabbitMQ 추천 설정 (Flask AI 서버 ↔ Spring Boot)
    RECOMMAND_REQUEST_QUEUE = os.environ.get('RECOMMAND_REQUEST_QUEUE') or 'recommand.request.queue'
    RECOMMAND_RESPONSE_QUEUE = os.environ.get('RECOMMAND_RESPONSE_QUEUE') or 'recommand.response.queue'
    RECOMMAND_EXCHANGE = os.environ.get('RECOMMAND_EXCHANGE') or 'recommand.exchange'
    RECOMMAND_RESPONSE_ROUTING_KEY = os.environ.get('RECOMMAND_RESPONSE_ROUTING_KEY') or 'recommand.response'
    
    # RabbitMQ VectorDB 메타데이터 업데이트 설정 (Spring Boot → Flask)
    METADATA_UPDATE_QUEUE = os.environ.get('METADATA_UPDATE_QUEUE') or 'model3d.metadata.update.queue'
    METADATA_UPDATE_ROUTING_KEY = os.environ.get('METADATA_UPDATE_ROUTING_KEY') or 'model3d.metadata.update'
    
    # RabbitMQ VectorDB 삭제 설정 (Spring Boot → Flask)
    MODEL3D_DELETE_QUEUE = os.environ.get('MODEL3D_DELETE_QUEUE') or 'model3d.delete.queue'
    MODEL3D_DELETE_ROUTING_KEY = os.environ.get('MODEL3D_DELETE_ROUTING_KEY') or 'model3d.delete'
    
    # 3D 모델 저장 경로
    MODEL3D_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads', 'models')
    
    # 이미지 품질 검증 설정
    # QUALITY_CHECK_ENABLED: 품질 검증 활성화 여부
    # QUALITY_CHECK_STRICT_MODE: 엄격 모드 (True: 80점 이상, False: 50점 이상)
    QUALITY_CHECK_ENABLED = os.environ.get('QUALITY_CHECK_ENABLED', 'true').lower() == 'true'
    QUALITY_CHECK_STRICT_MODE = os.environ.get('QUALITY_CHECK_STRICT_MODE', 'false').lower() == 'true'
    
    # 벡터DB 설정 (CLIP 모델 기반 메타데이터 저장)
    # 메타데이터: 3d_model_id, furniture_type, image_path, is_shared, member_id
    VECTORDB_PATH = os.path.join(os.path.dirname(__file__), 'uploads', 'vectordb')
    VECTORDB_INDEX_FILE = 'furniture_index.pkl'
    VECTORDB_METADATA_FILE = 'furniture_metadata.json'
    
    # AWS S3 설정
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_S3_BUCKET_NAME = os.environ.get('AWS_S3_BUCKET_NAME', 'myroom-ai-models')
    AWS_S3_REGION = os.environ.get('AWS_S3_REGION', 'ap-northeast-2')
    AWS_S3_FOLDER = os.environ.get('AWS_S3_FOLDER', '3d-models')
    
    # Gemini API 설정 (google-genai 패키지용 올바른 모델명)
    # 공식 모델: gemini-2.5-flash, gemini-2.5-pro, gemini-3-flash, gemini-3-pro
    GEMINI_PRIMARY_MODEL = os.environ.get('GEMINI_PRIMARY_MODEL') or 'gemini-2.5-flash'
    GEMINI_FALLBACK_MODELS = [
        'gemini-2.5-flash',
        'gemini-2.5-pro',
        'gemini-3-flash',
    ]
    GEMINI_MAX_RETRIES = 3
    GEMINI_TIMEOUT = 30
    
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
        # 벡터DB 폴더가 없으면 생성
        os.makedirs(Config.VECTORDB_PATH, exist_ok=True)


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
    
    # 프로덕션 환경에서 RabbitMQ는 EC2 인스턴스에서 실행 중이라고 가정
    RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST') or 'your-ec2-instance-ip'  # EC2 IP 주소로 변경 필요
    RABBITMQ_PORT = int(os.environ.get('RABBITMQ_PORT') or 5672)
    RABBITMQ_USERNAME = os.environ.get('RABBITMQ_USERNAME') or 'your-username'
    RABBITMQ_PASSWORD = os.environ.get('RABBITMQ_PASSWORD') or 'your-password'
    
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
