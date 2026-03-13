"""
프로덕션 모드 Flask 서버 실행 스크립트

개발 중에도 Werkzeug의 파일 모니터링(reloader)를 비활성화하여
FastAPI 성능 저하를 방지합니다.

사용 방법:
    python run_production.py              - S3 비활성화 (기본값)
    python run_production.py -s3          - S3 활성화
    python run_production.py -nos3        - S3 비활성화 (명시적)
"""

import os
import sys
import argparse
import subprocess
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()

# ============================================
# 프로덕션 모드: EC2 RabbitMQ 사용
# main.py는 Docker RabbitMQ (localhost) 사용
# ============================================
# 환경변수에서 프로덕션 RabbitMQ 설정 읽기
production_host = os.environ.get('PRODUCTION_RABBITMQ_HOST', '43.201.36.211')
production_port = os.environ.get('PRODUCTION_RABBITMQ_PORT', '5672')
production_username = os.environ.get('PRODUCTION_RABBITMQ_USERNAME', 'guest')
production_password = os.environ.get('PRODUCTION_RABBITMQ_PASSWORD', 'guest')

os.environ['RABBITMQ_HOST'] = production_host
os.environ['RABBITMQ_PORT'] = production_port
os.environ['RABBITMQ_USERNAME'] = production_username
os.environ['RABBITMQ_PASSWORD'] = production_password
print(f"[RabbitMQ] EC2 ({production_host}:{production_port}) 연결 모드")

# 프로덕션 모드 설정
os.environ['FLASK_ENV'] = 'production'

# 이제 앱 임포트 (환경변수 설정 후)
from app import create_app
from threading import Thread

# 애플리케이션 생성
app = create_app('production')

from app.utils.rabbitmq_consumer import start_consumer_thread
from app.utils.recommendation_consumer import start_recommendation_consumer_thread
from app.utils.metadata_update_consumer import start_metadata_update_consumer_thread
from app.utils.model3d_delete_consumer import start_model3d_delete_consumer_thread


def parse_arguments():
    """커맨드라인 인자 파싱"""
    parser = argparse.ArgumentParser(
        description='MyRoom AI REST API 서버 (프로덕션 모드)'
    )
    
    s3_group = parser.add_mutually_exclusive_group()
    s3_group.add_argument(
        '-s3', '--use-s3',
        action='store_true',
        default=False,
        help='S3에 3D 모델을 업로드합니다 (기본값: 비활성화)'
    )
    s3_group.add_argument(
        '-nos3', '--no-s3',
        action='store_true',
        dest='no_s3',
        help='S3 업로드를 비활성화하고 로컬 URL을 사용합니다'
    )

    parser.add_argument(
        '-ui', '--ui',
        action='store_true',
        help='서버와 함께 3D 파라미터 관리 GUI를 실행합니다'
    )
    
    return parser.parse_args()


@app.route('/')
def index():
    """루트 경로"""
    return {
        'message': 'MyRoom AI API (프로덕션 모드)',
        'documentation': '/docs',
        'version': app.config['API_VERSION']
    }


if __name__ == '__main__':
    # 커맨드라인 인자 파싱
    args = parse_arguments()

    if args.ui:
        try:
            app.logger.info('3D 파라미터 관리 GUI를 백그라운드에서 실행합니다.')
            subprocess.Popen(
                [sys.executable, '-m', 'gui.run_gui'],
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
        except Exception as e:
            app.logger.warning(f'GUI 실행 실패: {e}')
    
    # S3 사용 여부 설정
    use_s3 = args.use_s3 and not args.no_s3
    app.config['USE_S3'] = use_s3
    
    # 로깅
    s3_status = "✅ 활성화 (S3에 업로드)" if use_s3 else "❌ 비활성화 (로컬 URL 사용)"
    app.logger.info(f"S3 업로드: {s3_status}")
    
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    enable_consumers = os.environ.get('ENABLE_CONSUMERS', 'true').lower() == 'true'
    
    # Consumer 시작
    if enable_consumers:
        try:
            consumer_thread = Thread(
                target=start_consumer_thread,
                args=(app,),
                daemon=True,
                name='RabbitMQ-Consumer-Model3D'
            )
            consumer_thread.start()
            app.logger.info('✓ 3D 모델 생성 Consumer 시작')
        except Exception as e:
            app.logger.warning(f'⚠ Consumer 시작 실패: {e}')
        
        try:
            recommendation_consumer_thread = Thread(
                target=start_recommendation_consumer_thread,
                args=(app,),
                daemon=True,
                name='RabbitMQ-Consumer-Recommendation'
            )
            recommendation_consumer_thread.start()
            app.logger.info('✓ 추천 Consumer 시작')
        except Exception as e:
            app.logger.warning(f'⚠ Consumer 시작 실패: {e}')

        try:
            start_metadata_update_consumer_thread(app)
            app.logger.info('✓ 메타데이터 업데이트 Consumer 시작')
        except Exception as e:
            app.logger.warning(f'⚠ 메타데이터 업데이트 Consumer 시작 실패: {e}')

        try:
            start_model3d_delete_consumer_thread(app)
            app.logger.info('✓ VectorDB 삭제 Consumer 시작')
        except Exception as e:
            app.logger.warning(f'⚠ VectorDB 삭제 Consumer 시작 실패: {e}')
    else:
        app.logger.info('○ Consumer 비활성화됨')
    
    app.logger.info("")
    app.logger.info("╔════════════════════════════════════════════════════════════╗")
    app.logger.info("║          MyRoom AI - Flask API Server (Production)         ║")
    app.logger.info("╚════════════════════════════════════════════════════════════╝")
    app.logger.info(f"🚀 서버 시작: http://{host}:{port}")
    app.logger.info(f"📖 API 문서: http://{host}:{port}/docs")
    app.logger.info("⚡ Werkzeug 파일 모니터링 비활성화 (FastAPI 성능 최적화)")
    app.logger.info("")
    
    # 프로덕션 모드: reloader/debugger 비활성화
    app.run(
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
        use_debugger=False,
        threaded=True
    )
