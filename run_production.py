"""
프로덕션 모드 Flask 서버 실행 스크립트

개발 중에도 Werkzeug의 파일 모니터링(reloader)를 비활성화하여
FastAPI 성능 저하를 방지합니다.

사용 방법:
    python run_production.py
"""

import os
import sys
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()

# 프로덕션 모드 설정
os.environ['FLASK_ENV'] = 'production'

# 이제 앱 임포트 (환경변수 설정 후)
from app import create_app
from threading import Thread

# 애플리케이션 생성
app = create_app('production')

from app.utils.rabbitmq_consumer import start_consumer_thread
from app.utils.recommendation_consumer import start_recommendation_consumer_thread


@app.route('/')
def index():
    """루트 경로"""
    return {
        'message': 'MyRoom AI API (프로덕션 모드)',
        'documentation': '/docs',
        'version': app.config['API_VERSION']
    }


if __name__ == '__main__':
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
