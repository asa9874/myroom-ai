@echo off
echo ======================================
echo   RabbitMQ 테스트 스크립트 실행
echo ======================================
echo.

echo [1/2] RabbitMQ 서버 확인 중...
docker ps | findstr rabbitmq >nul 2>&1
if %errorlevel% == 0 (
    echo ✓ RabbitMQ 서버가 실행 중입니다.
) else (
    echo ✗ RabbitMQ 서버가 실행되지 않았습니다!
    echo.
    echo 먼저 RabbitMQ 서버를 시작하세요:
    echo   docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
    echo.
    echo 또는 start_server.bat를 실행하세요.
    pause
    exit /b 1
)

echo.
echo [2/2] Flask 서버 확인 중...
curl -s http://localhost:5000/api/v1/health/ping >nul 2>&1
if %errorlevel% == 0 (
    echo ✓ Flask 서버가 실행 중입니다.
) else (
    echo ⚠ Flask 서버가 실행되지 않았습니다.
    echo   테스트를 계속 진행하지만, 메시지가 처리되지 않을 수 있습니다.
    echo.
    echo   Flask 서버 시작: python main.py
)

echo.
echo ======================================
echo   테스트 스크립트 실행
echo ======================================
echo.

python test_rabbitmq.py

echo.
echo ======================================
echo   테스트 후 확인사항
echo ======================================
echo.
echo 1. Flask 서버 로그 확인
echo 2. RabbitMQ 관리 콘솔: http://localhost:15672/
echo 3. API 호출:
echo    curl http://localhost:5000/api/v1/model3d/models
echo    curl http://localhost:5000/api/v1/model3d/stats
echo.

pause
