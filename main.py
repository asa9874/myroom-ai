"""
MyRoom AI REST API 서버

Flask와 Flask-RESTX를 사용한 RESTful API 서버의 진입점입니다.
Swagger UI를 통해 API 문서를 제공합니다.
RabbitMQ Consumer를 별도 스레드에서 실행하여 3D 모델 생성 요청을 처리합니다.

실행 방법:
    개발 모드: python main.py
    프로덕션 모드: FLASK_ENV=production python main.py
"""

import os
import sys
import argparse
import subprocess
from dotenv import load_dotenv
from threading import Thread

# .env 파일에서 환경변수 로드
load_dotenv()

# ============================================
# 개발 모드: Docker RabbitMQ 사용 (localhost)
# run_production.py는 EC2 RabbitMQ 사용
# ============================================
os.environ['RABBITMQ_HOST'] = 'localhost'
os.environ['RABBITMQ_PORT'] = '5672'
os.environ['RABBITMQ_USERNAME'] = 'guest'
os.environ['RABBITMQ_PASSWORD'] = 'guest'
print("[RabbitMQ] Docker (localhost:5672) 연결 모드")

from app import create_app
from app.utils.rabbitmq_consumer import start_consumer_thread
from app.utils.recommendation_consumer import start_recommendation_consumer_thread
from app.utils.metadata_update_consumer import start_metadata_update_consumer_thread
from app.utils.model3d_delete_consumer import start_model3d_delete_consumer_thread


def parse_arguments():
    """
    커맨드라인 인자 파싱
    
    Returns:
        argparse.Namespace: 파싱된 인자들
    """
    parser = argparse.ArgumentParser(
        description='MyRoom AI REST API 서버',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
예시:
  python main.py -s3          # S3 업로드 활성화
  python main.py -nos3        # S3 업로드 비활성화 (로컬 URL 사용)
  python main.py -s3 -p 8080  # S3 업로드 활성화, 포트 8080 사용
    python main.py -ui          # 3D 파라미터 관리 GUI 실행 후 서버 시작
        '''
    )
    
    # S3 옵션
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
    
    # 포트 옵션
    parser.add_argument(
        '-p', '--port',
        type=int,
        default=int(os.environ.get('PORT', 5000)),
        help='서버 포트 (기본값: 5000)'
    )
    
    # 호스트 옵션
    parser.add_argument(
        '-H', '--host',
        default=os.environ.get('HOST', '0.0.0.0'),
        help='서버 호스트 (기본값: 0.0.0.0)'
    )
    
    # Debug 모드
    parser.add_argument(
        '-d', '--debug',
        action='store_true',
        help='Debug 모드 활성화'
    )

    parser.add_argument(
        '-ui', '--ui',
        action='store_true',
        help='서버와 함께 3D 파라미터 관리 GUI를 실행합니다'
    )
    
    return parser.parse_args()


# 애플리케이션 생성
app = create_app()


@app.route('/')
def index():
    """
    루트 경로
    API 문서 페이지로 리다이렉트합니다.
    """
    return {
        'message': 'MyRoom AI API에 오신 것을 환영합니다!',
        'documentation': '/docs',
        'version': app.config['API_VERSION'],
        'features': {
            'rabbitmq_consumer': 'RabbitMQ 메시지 수신 중',
            'model3d_generation': '3D 모델 생성 서비스 활성화'
        }
    }


def run_parameter_ui() -> None:
    """3D 파라미터 관리 GUI를 백그라운드 프로세스로 실행"""
    try:
        app.logger.info('3D 파라미터 관리 GUI를 백그라운드에서 실행합니다.')
        subprocess.Popen(
            [sys.executable, '-m', 'gui.run_gui'],
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
    except Exception as e:
        app.logger.warning(f'GUI 실행 실패: {e}')


if __name__ == '__main__':
    # 커맨드라인 인자 파싱
    args = parse_arguments()

    if args.ui:
        run_parameter_ui()
    
    # S3 사용 여부 설정
    use_s3 = args.use_s3 and not args.no_s3
    app.config['USE_S3'] = use_s3
    
    # 로깅
    s3_status = "✅ 활성화 (S3에 업로드)" if use_s3 else "❌ 비활성화 (로컬 URL 사용)"
    app.logger.info(f"S3 업로드: {s3_status}")
    
    # 환경 변수에서 포트 번호 가져오기 (인자 우선)
    port = args.port
    
    # 환경 변수에서 호스트 가져오기 (인자 우선)
    host = args.host
    
    # RabbitMQ Consumer (3D 모델 생성)를 별도 스레드에서 시작
    try:
        consumer_thread = Thread(
            target=start_consumer_thread,
            args=(app,),
            daemon=True,
            name='RabbitMQ-Consumer-Model3D'
        )
        consumer_thread.start()
        app.logger.info('3D 모델 생성 Consumer 스레드 시작됨')
    except Exception as e:
        app.logger.warning(f'3D 모델 생성 Consumer 시작 실패: {e}')
    
    # RabbitMQ Consumer (추천)를 별도 스레드에서 시작
    try:
        recommendation_consumer_thread = Thread(
            target=start_recommendation_consumer_thread,
            args=(app,),
            daemon=True,
            name='RabbitMQ-Consumer-Recommendation'
        )
        recommendation_consumer_thread.start()
        app.logger.info('추천 요청 Consumer 스레드 시작됨')
    except Exception as e:
        app.logger.warning(f'추천 요청 Consumer 시작 실패: {e}')
    
    # RabbitMQ Consumer (메타데이터 업데이트)를 별도 스레드에서 시작
    try:
        start_metadata_update_consumer_thread(app)
        app.logger.info('VectorDB 메타데이터 업데이트 Consumer 스레드 시작됨')
    except Exception as e:
        app.logger.warning(f'VectorDB 메타데이터 업데이트 Consumer 시작 실패: {e}')
    
    # RabbitMQ Consumer (VectorDB 삭제)를 별도 스레드에서 시작
    try:
        start_model3d_delete_consumer_thread(app)
        app.logger.info('VectorDB 삭제 Consumer 스레드 시작됨')
    except Exception as e:
        app.logger.warning(f'VectorDB 삭제 Consumer 시작 실패: {e}')
    
    # 서버 시작
    app.logger.info(f'서버가 http://{host}:{port} 에서 시작됩니다.')
    app.logger.info(f'Swagger 문서는 http://{host}:{port}/docs 에서 확인할 수 있습니다.')
    
    # ⚠️ 성능 중요: 개발 중이어도 프로덕션 모드로 실행 권장
    # debug=True 시 Werkzeug reloader가 모든 파일을 계속 모니터링하여 CPU 과다 점유
    debug_mode = args.debug or app.config['DEBUG']
    use_reloader = False  # 파일 자동 재로드 비활성화
    use_debugger = False  # Debugger 비활성화
    
    if debug_mode:
        app.logger.warning("⚠️  DEBUG 모드 활성화 - FastAPI 성능이 저하될 수 있습니다")
        app.logger.info("💡 권장: FLASK_ENV=production으로 실행하세요")
    
    app.run(
        host=host,
        port=port,
        debug=debug_mode,
        use_reloader=use_reloader,
        use_debugger=use_debugger,
        threaded=True  # 멀티스레드 활성화 (GIL 영향 감소)
    )
