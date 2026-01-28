@echo off
echo ======================================
echo   RabbitMQ + Flask AI Server 실행
echo ======================================
echo.

REM 기본값: S3 사용 안 함 (-nos3)
set S3_OPTION=-nos3

REM 커맨드라인 인자 확인
if "%1"=="-s3" (
    set S3_OPTION=-s3
    echo [설정] S3 업로드 활성화
) else if "%1"=="-nos3" (
    set S3_OPTION=-nos3
    echo [설정] S3 업로드 비활성화 (로컬 URL 사용)
) else if not "%1"=="" (
    echo [경고] 알 수 없는 옵션: %1
    echo.
    echo 사용법:
    echo   start_server.bat          - S3 비활성화 (기본값)
    echo   start_server.bat -s3      - S3 활성화
    echo   start_server.bat -nos3    - S3 비활성화 (명시적)
    echo.
    pause
    exit /b 1
)

echo.

REM 1. RabbitMQ Docker 컨테이너 실행 확인
echo [1/3] RabbitMQ 서버 확인 중...
docker ps | findstr rabbitmq >nul 2>&1
if %errorlevel% == 0 (
    echo ✓ RabbitMQ 서버가 이미 실행 중입니다.
) else (
    echo ! RabbitMQ 서버가 실행되지 않았습니다.
    echo   Docker 컨테이너를 시작합니다...
    docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
    if %errorlevel% == 0 (
        echo ✓ RabbitMQ 서버가 시작되었습니다.
        echo   초기화를 위해 10초 대기 중...
        timeout /t 10 /nobreak >nul
    ) else (
        echo ✗ RabbitMQ 서버 시작 실패!
        echo   수동으로 Docker를 확인하세요.
        pause
        exit /b 1
    )
)

echo.
echo [2/3] Python 패키지 확인 중...
pip show pika >nul 2>&1
if %errorlevel% == 0 (
    echo ✓ pika 패키지가 설치되어 있습니다.
) else (
    echo ! pika 패키지가 설치되지 않았습니다.
    echo   패키지를 설치합니다...
    pip install pika==1.3.2
)

echo.
echo [3/3] Flask AI 서버 시작 중...
echo.
echo ======================================
echo   서버 정보:
echo   - Flask: http://localhost:5000
echo   - Swagger: http://localhost:5000/docs
echo   - RabbitMQ 관리: http://localhost:15672
echo     (Username: guest / Password: guest)
echo ======================================
echo.

REM Flask 서버 실행 (S3 옵션 포함)
python main.py %S3_OPTION%

pause


REM Flask 서버 실행
python main.py

pause
