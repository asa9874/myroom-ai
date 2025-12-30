"""
MyRoom-AI 메인 서버
가구 추천 API를 recommand 모듈에서 제공
"""

from flask import Flask, jsonify
import sys
import os
from pathlib import Path

# recommand 모듈 경로 추가
recommand_path = str(Path(__file__).parent / 'recommand')
sys.path.insert(0, recommand_path)

# api_server에서 Flask 앱 임포트
API_INTEGRATED = False
try:
    from api_server import app as api_app, init_vectorizer, vectorizer
    print("[Main] API 서버를 recommand 모듈에서 로드했습니다.")
    API_INTEGRATED = True
except ImportError as e:
    print(f"[Error] API 로드 실패: {e}")
    api_app = None

# Flask 앱 선택
if API_INTEGRATED and api_app:
    app = api_app
    # 벡터화 엔진 초기화
    try:
        init_vectorizer()
        print("[Main] 벡터화 엔진이 초기화되었습니다.")
    except Exception as e:
        print(f"[Warning] 벡터화 엔진 초기화 실패: {e}")
else:
    # Fallback: 독립 Flask 앱 생성
    app = Flask(__name__)


# ========================================
# 기본 엔드포인트
# ========================================

@app.route('/', methods=['GET'])
def index():
    """메인 페이지"""
    return jsonify({
        "name": "MyRoom-AI",
        "description": "지능형 가구 추천 시스템",
        "version": "1.0.0",
        "api_integrated": API_INTEGRATED,
        "services": {
            "recommendation_api": "/api/status",
            "swagger_ui": "/api/docs",
            "documentation": "/api/docs"
        }
    }), 200


@app.route('/docs', methods=['GET'])
def docs():
    """API 문서 링크"""
    return jsonify({
        "message": "API 문서를 확인하세요",
        "documentation_file": "recommand/API_DOCUMENTATION.md",
        "endpoints": [
            {"method": "GET", "path": "/api/status", "description": "API 상태 확인"},
            {"method": "GET", "path": "/api/health", "description": "헬스 체크"},
            {"method": "POST", "path": "/api/analyze/image", "description": "이미지 분석"},
            {"method": "POST", "path": "/api/search/image", "description": "이미지 검색"},
            {"method": "POST", "path": "/api/search/text", "description": "텍스트 검색"},
            {"method": "POST", "path": "/api/recommend", "description": "가구 추천"},
            {"method": "POST", "path": "/api/recommend/batch", "description": "배치 추천"},
            {"method": "POST", "path": "/api/db/build", "description": "DB 구축"},
            {"method": "GET", "path": "/api/db/info", "description": "DB 정보"}
        ]
    }), 200


# ========================================
# 앱 초기화 및 실행
# ========================================

if __name__ == '__main__':
    print("[Main] MyRoom-AI 서버 시작...")
    print(f"[Main] API 통합 상태: {'성공' if API_INTEGRATED else '실패'}")
    
    if not API_INTEGRATED:
        print("[Error] API를 로드할 수 없습니다.")
        print("[Info] 다음을 확인하세요:")
        print("  1. recommand/api_server.py 파일이 있는지 확인")
        print("  2. Python 경로가 올바른지 확인")
        print("  3. 직접 실행: cd recommand && python api_server.py")
    
    print("[Info] http://localhost:5000 에서 서버가 실행 중입니다.")
    print("[Info] http://localhost:5000/docs 에서 API 문서를 확인할 수 있습니다.")
    print("[Info] test_api.html 에서 웹 기반 API 테스트")
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False
    )
