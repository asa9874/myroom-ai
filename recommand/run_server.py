#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MyRoom-AI API 서버 (recommand 모듈 직접 실행)
이 파일은 recommand 디렉토리에 있어야 합니다.

사용 방법:
    cd myroom-ai/recommand
    python run_server.py
"""

import sys
import os

# 현재 디렉토리를 모듈 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_server import app, init_vectorizer

if __name__ == '__main__':
    print("=" * 60)
    print("MyRoom-AI API 서버")
    print("=" * 60)
    
    # 벡터화 엔진 초기화
    print("\n[Startup] 벡터화 엔진을 초기화하는 중...")
    if not init_vectorizer():
        print("[Warning] 벡터화 엔진 초기화 중 문제가 발생했습니다.")
        print("[Info] 계속 진행합니다...")
    
    print("\n" + "=" * 60)
    print("🚀 서버 시작됨")
    print("=" * 60)
    print("\n📍 API 엔드포인트:")
    print("  - GET  http://localhost:5000/api/status")
    print("  - GET  http://localhost:5000/api/health")
    print("  - POST http://localhost:5000/api/analyze/image")
    print("  - POST http://localhost:5000/api/search/image")
    print("  - POST http://localhost:5000/api/search/text")
    print("  - POST http://localhost:5000/api/recommend")
    print("  - POST http://localhost:5000/api/recommend/batch")
    print("  - POST http://localhost:5000/api/db/build")
    print("  - GET  http://localhost:5000/api/db/info")
    print("\n📚 Swagger API 문서:")
    print("  - http://localhost:5000/docs")
    print("\n🌐 웹 테스트 도구:")
    print("  - file:///path/to/test_api.html")
    print("\n⚠️  종료하려면 Ctrl+C를 누르세요")
    print("=" * 60 + "\n")
    
    # Flask 서버 실행
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False
    )
