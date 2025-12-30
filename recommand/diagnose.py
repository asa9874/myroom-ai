#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MyRoom-AI API 진단 스크립트
API 라우팅 문제를 진단합니다.
"""

import sys
import os
from pathlib import Path

print("=" * 70)
print("🔍 MyRoom-AI API 진단 도구")
print("=" * 70)

# 1. 파일 존재 확인
print("\n[1] 파일 존재 확인")
print("-" * 70)

current_dir = Path(__file__).parent
print(f"현재 디렉토리: {current_dir}")

files_to_check = [
    'api_server.py',
    'vectorizer.py',
    'vectorize_images.py',
    '__init__.py'
]

all_files_exist = True
for file in files_to_check:
    file_path = current_dir / file
    exists = file_path.exists()
    status = "✅" if exists else "❌"
    print(f"{status} {file}")
    all_files_exist = all_files_exist and exists

# 2. 임포트 테스트
print("\n[2] 임포트 테스트")
print("-" * 70)

# api_server 임포트
try:
    from api_server import app
    print("✅ api_server.py 에서 Flask app 임포트 성공")
except Exception as e:
    print(f"❌ api_server.py 임포트 실패: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# init_vectorizer 함수 찾기
try:
    from api_server import init_vectorizer
    print("✅ init_vectorizer 함수 임포트 성공")
except Exception as e:
    print(f"❌ init_vectorizer 함수 임포트 실패: {e}")

# 3. Flask 앱 상태 확인
print("\n[3] Flask 앱 상태")
print("-" * 70)

print(f"앱 이름: {app.name}")
print(f"앱 debug: {app.debug}")
print(f"앱 routes 개수: {len(app.url_map._rules)}")

# 4. 라우트 확인
print("\n[4] 등록된 라우트")
print("-" * 70)

for rule in app.url_map.iter_rules():
    # Flask 자동 라우트 제외
    if rule.endpoint in ('static', 'werkzeug.'):
        continue
    print(f"  {rule.rule:40} [{', '.join(rule.methods - {'OPTIONS', 'HEAD'})}]")

api_routes = [rule.rule for rule in app.url_map.iter_rules() if rule.rule.startswith('/api')]
print(f"\n총 API 라우트: {len(api_routes)}개")

if len(api_routes) == 0:
    print("❌ API 라우트가 등록되지 않았습니다!")
elif len(api_routes) < 9:
    print(f"⚠️  예상한 9개보다 {len(api_routes)}개만 등록되었습니다.")
else:
    print(f"✅ {len(api_routes)}개의 API 라우트가 등록되었습니다.")

# 5. 테스트 요청
print("\n[5] 테스트 요청")
print("-" * 70)

test_client = app.test_client()

# GET /api/status 테스트
try:
    response = test_client.get('/api/status')
    print(f"GET /api/status: {response.status_code}")
    if response.status_code == 200:
        print(f"  응답: {response.get_json()}")
    else:
        print(f"  응답 데이터: {response.data}")
except Exception as e:
    print(f"❌ 요청 실패: {e}")

# GET /api/health 테스트
try:
    response = test_client.get('/api/health')
    print(f"GET /api/health: {response.status_code}")
    if response.status_code == 200:
        print(f"  응답: {response.get_json()}")
except Exception as e:
    print(f"❌ 요청 실패: {e}")

print("\n" + "=" * 70)
print("진단 완료")
print("=" * 70)

print("\n💡 다음 단계:")
if len(api_routes) >= 9:
    print("  서버가 정상적으로 작동합니다. run_server.py를 실행해보세요:")
    print("    python run_server.py")
else:
    print("  라우트가 제대로 등록되지 않았습니다. api_server.py를 확인하세요.")

