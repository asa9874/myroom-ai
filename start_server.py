#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MyRoom-AI 빠른 시작 스크립트

이 스크립트를 실행하면 API 서버가 바로 시작됩니다.

사용 방법:
    python start_server.py
"""

import os
import sys
import subprocess
from pathlib import Path

def main():
    print("=" * 70)
    print(" " * 15 + "🏠 MyRoom-AI API 서버 시작 도구")
    print("=" * 70)
    
    # 현재 디렉토리 확인
    current_dir = Path.cwd()
    myroom_ai_dir = None
    
    # myroom-ai 디렉토리 찾기
    if (current_dir / 'recommand' / 'api_server.py').exists():
        myroom_ai_dir = current_dir
        print(f"\n✅ myroom-ai 디렉토리를 찾았습니다: {current_dir}")
    elif (current_dir.parent / 'recommand' / 'api_server.py').exists():
        myroom_ai_dir = current_dir.parent
        print(f"\n✅ myroom-ai 디렉토리를 찾았습니다: {myroom_ai_dir}")
    elif (current_dir.parent.parent / 'recommand' / 'api_server.py').exists():
        myroom_ai_dir = current_dir.parent.parent
        print(f"\n✅ myroom-ai 디렉토리를 찾았습니다: {myroom_ai_dir}")
    else:
        print("\n❌ myroom-ai 디렉토리를 찾을 수 없습니다.")
        print("   이 스크립트를 myroom-ai 디렉토리에서 실행하세요.")
        sys.exit(1)
    
    # recommand 디렉토리로 이동
    recommand_dir = myroom_ai_dir / 'recommand'
    print(f"✅ recommand 디렉토리: {recommand_dir}")
    
    print("\n" + "=" * 70)
    print("API 서버를 시작합니다...")
    print("=" * 70)
    print("\n📍 시작할 준비가 되었습니다:")
    print(f"   - 디렉토리: {recommand_dir}")
    print(f"   - 포트: 5000")
    print(f"   - URL: http://localhost:5000")
    print("\n💡 다음을 할 수 있습니다:")
    print("   - http://localhost:5000/api/status 에서 상태 확인")
    print("   - file:///.../test_api.html 에서 테스트 도구 사용")
    print("\n⚠️  종료: Ctrl+C 누르기")
    print("\n" + "=" * 70 + "\n")
    
    # api_server.py 또는 run_server.py 실행
    run_server_path = recommand_dir / 'run_server.py'
    api_server_path = recommand_dir / 'api_server.py'
    
    if run_server_path.exists():
        script_to_run = str(run_server_path)
        print(f"🚀 실행 중: {run_server_path}")
    elif api_server_path.exists():
        script_to_run = str(api_server_path)
        print(f"🚀 실행 중: {api_server_path}")
    else:
        print("❌ 실행할 스크립트를 찾을 수 없습니다.")
        sys.exit(1)
    
    try:
        # Python 스크립트 실행
        result = subprocess.run(
            [sys.executable, script_to_run],
            cwd=str(recommand_dir),
            check=False
        )
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n\n✅ 서버가 중지되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 오류가 발생했습니다: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
