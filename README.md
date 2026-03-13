# MyRoom AI REST API

Flask와 Flask-RESTX를 사용한 RESTful API 서버입니다.  
**RabbitMQ 연동을 통해 Spring Boot 애플리케이션으로부터 3D 모델 생성 요청을 수신하고 처리합니다.**

## 🌟 주요 기능

- ✅ RESTful API (Flask-RESTX + Swagger UI)
- ✅ RabbitMQ 메시지 큐 연동
- ✅ 3D 모델 생성 비동기 처리
- ✅ 이미지 업로드 및 처리
- ✅ API 문서 자동 생성 (Swagger)

## 프로젝트 구조

```
myroom-ai/
├── main.py                      # 애플리케이션 진입점 (+ RabbitMQ Consumer 시작)
├── config.py                    # 설정 파일 (+ RabbitMQ 설정)
├── requirements.txt             # 의존성 패키지
├── test_rabbitmq.py            # RabbitMQ 테스트 스크립트
├── start_server.bat            # 서버 실행 스크립트 (Windows)
├── TESTING_GUIDE.md            # 테스트 가이드
├── app/                        # 애플리케이션 패키지
│   ├── __init__.py            # 앱 팩토리
│   ├── routes/                # API 라우트
│   │   ├── health.py          # 헬스 체크 API
│   │   ├── example.py         # 예제 API (CRUD)
│   │   └── model3d.py         # 3D 모델 관련 API ⭐ NEW
│   ├── models/                # 데이터 모델
│   │   └── __init__.py
│   └── utils/                 # 유틸리티 함수
│       ├── __init__.py
│       └── rabbitmq_consumer.py  # RabbitMQ Consumer ⭐ NEW
└── uploads/                   # 업로드 파일 저장 (자동 생성)
    ├── logs/                  # 처리 로그
    └── models/                # 생성된 3D 모델
```

## 🚀 빠른 시작

### 방법 1: 자동 실행 스크립트 (Windows)

```bash
start_server.bat
```

이 스크립트는 다음을 자동으로 수행합니다:
1. RabbitMQ Docker 컨테이너 확인/시작
2. Python 패키지 설치 확인
3. Flask 서버 시작

### 방법 2: 수동 설치 및 실행

#### 1. RabbitMQ 서버 실행

**Docker 사용 (권장):**
```bash
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
```

#### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

#### 3. Flask 서버 실행

```bash
python main.py
```

### 3D 파라미터 GUI 실행

3D 모델 생성 파라미터는 `config/model3d_params.json`에서 관리됩니다.

```bash
python main.py -ui
```

또는 프로덕션 실행 스크립트에서:

```bash
python run_production.py -ui
```

`-ui`를 사용하면 서버 시작 전에 파라미터 관리 GUI가 열리고,
저장 후 창을 닫으면 서버가 이어서 시작됩니다.

## 📡 API 엔드포인트

### Swagger UI
- **URL**: http://localhost:5000/docs
- **설명**: 모든 API를 테스트할 수 있는 인터랙티브 문서

### 헬스 체크
- `GET /api/v1/health/` - 서버 상태 확인
- `GET /api/v1/health/ping` - 핑 테스트

### 3D 모델 API ⭐ NEW
- `GET /api/v1/model3d/models` - 모든 3D 모델 조회
- `GET /api/v1/model3d/models/{member_id}` - 특정 사용자의 3D 모델 조회
- `GET /api/v1/model3d/models/latest` - 최근 생성된 3D 모델 조회
- `GET /api/v1/model3d/stats` - 3D 모델 생성 통계

### 예제 API (CRUD)
- `GET /api/v1/examples/` - 모든 아이템 조회
- `POST /api/v1/examples/` - 새 아이템 생성
- `GET /api/v1/examples/{id}` - 특정 아이템 조회
- `PUT /api/v1/examples/{id}` - 아이템 수정
- `DELETE /api/v1/examples/{id}` - 아이템 삭제
- `GET /api/v1/examples/search?q=검색어` - 아이템 검색

## 🧪 테스트

### RabbitMQ 테스트 스크립트 실행

```bash
python test_rabbitmq.py
```

테스트 옵션:
1. 단일 메시지 전송
2. 다중 메시지 전송 (3개)
3. 다중 메시지 전송 (5개)
4. Queue 상태 확인

**자세한 테스트 가이드는 [TESTING_GUIDE.md](TESTING_GUIDE.md)를 참고하세요.**

## 🔧 환경 변수

### Flask 설정
- `FLASK_ENV`: 실행 환경 (development, production, testing)
- `SECRET_KEY`: Flask 비밀 키 (프로덕션 필수)
- `PORT`: 서버 포트 (기본값: 5000)
- `HOST`: 서버 호스트 (기본값: 0.0.0.0)
- `LOG_LEVEL`: 로그 레벨 (기본값: INFO)

### RabbitMQ 설정 ⭐ NEW
- `RABBITMQ_HOST`: RabbitMQ 호스트 (기본값: localhost)
- `RABBITMQ_PORT`: RabbitMQ 포트 (기본값: 5672)
- `RABBITMQ_USERNAME`: RabbitMQ 사용자명 (기본값: guest)
- `RABBITMQ_PASSWORD`: RabbitMQ 비밀번호 (기본값: guest)

## 🔗 주요 링크

- **Flask 서버**: http://localhost:5000
- **Swagger UI**: http://localhost:5000/docs
- **RabbitMQ 관리 콘솔**: http://localhost:15672 (guest/guest)

## 🏗️ RabbitMQ 아키텍처

```
┌─────────────────┐      ┌──────────────────┐      ┌────────────────────┐
│  Spring Boot    │      │    RabbitMQ      │      │   Flask AI Server  │
│   (Producer)    │─────>│  model3d.queue   │─────>│    (Consumer)      │
└─────────────────┘      └──────────────────┘      └────────────────────┘
        │                                                      │
        │ 1. 이미지 업로드                                      │
        │ 2. 메시지 발송                                       │
        │    - imageUrl                                       │ 3. 메시지 수신
        │    - memberId                                       │ 4. 이미지 다운로드
        │    - timestamp                                      │ 5. 3D 모델 생성
        │                                                     │ 6. 결과 저장
        │                                                     │ 7. ACK 전송
```

## 📝 개발 가이드

### 새 API 추가하기

1. `app/routes/` 폴더에 새 파일 생성 (예: `my_api.py`)
2. Namespace와 Resource 정의
3. `app/__init__.py`의 `register_routes()` 함수에 네임스페이스 등록

예제:
```python
# app/routes/my_api.py
from flask_restx import Namespace, Resource

ns = Namespace('myapi', description='나의 API')

@ns.route('/')
class MyResource(Resource):
    def get(self):
        return {'message': 'Hello'}
```

```python
# app/__init__.py의 register_routes() 함수에 추가
from app.routes.my_api import ns as my_api_ns
api.add_namespace(my_api_ns, path='/myapi')
```

### 설정 수정하기

`config.py` 파일에서 환경별 설정을 수정할 수 있습니다.

## 주요 기능

- ✅ Flask-RESTX를 통한 RESTful API
- ✅ Swagger UI 자동 문서화
- ✅ 환경별 설정 관리 (개발/프로덕션/테스트)
- ✅ 로깅 시스템
- ✅ 에러 핸들링
- ✅ CRUD 예제 API
- ✅ 모듈식 구조 (유지보수 용이)

## 라이선스

MIT
