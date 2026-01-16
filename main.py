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
from dotenv import load_dotenv
from threading import Thread
from app import create_app
from app.utils.rabbitmq_consumer import start_consumer_thread
from app.utils.recommendation_consumer import start_recommendation_consumer_thread

# .env 파일에서 환경변수 로드
load_dotenv()

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


if __name__ == '__main__':
    # 환경 변수에서 포트 번호 가져오기 (기본값: 5000)
    port = int(os.environ.get('PORT', 5000))
    
    # 환경 변수에서 호스트 가져오기 (기본값: 0.0.0.0)
    host = os.environ.get('HOST', '0.0.0.0')
    
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
    
    # 서버 시작
    app.logger.info(f'서버가 http://{host}:{port} 에서 시작됩니다.')
    app.logger.info(f'Swagger 문서는 http://{host}:{port}/docs 에서 확인할 수 있습니다.')
    
    # ⚠️ 성능 중요: 개발 중이어도 프로덕션 모드로 실행 권장
    # debug=True 시 Werkzeug reloader가 모든 파일을 계속 모니터링하여 CPU 과다 점유
    debug_mode = app.config['DEBUG']
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
