# RabbitMQ 연동 테스트 가이드

Flask AI 서버와 RabbitMQ를 연동하여 Spring Boot로부터 전송된 메시지를 수신하고 처리하는 시스템이 구현되었습니다.

## 📁 생성된 파일

1. **app/utils/rabbitmq_consumer.py** - RabbitMQ Consumer 구현
2. **app/routes/model3d.py** - 3D 모델 API 엔드포인트
3. **config.py** - RabbitMQ 설정 추가
4. **main.py** - Consumer 통합
5. **requirements.txt** - pika 라이브러리 추가

## 🚀 시작하기

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. RabbitMQ 서버 실행

#### Docker 사용 (권장)
```bash
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
```

#### Windows에서 직접 설치
RabbitMQ를 다운로드하고 설치 후 실행:
```bash
rabbitmq-server
```

### 3. RabbitMQ 관리 콘솔 접속

브라우저에서 다음 주소로 접속:
```
http://localhost:15672/
Username: guest
Password: guest
```

### 4. Flask AI 서버 실행

```bash
python main.py
```

실행되면 다음과 같은 로그가 표시됩니다:
```
==========================================
RabbitMQ Consumer 시작
Queue: model3d.upload.queue
Host: localhost:5672
메시지 대기 중... (종료하려면 CTRL+C)
==========================================
```

## 📡 API 엔드포인트

Flask 서버가 실행되면 다음 엔드포인트를 사용할 수 있습니다:

### Swagger UI
- **URL**: http://localhost:5000/docs
- **설명**: 모든 API를 테스트할 수 있는 인터랙티브 문서

### 3D 모델 API

#### 1. 모든 3D 모델 조회
```http
GET http://localhost:5000/api/v1/model3d/models
```

**응답 예시:**
```json
[
  {
    "memberId": 1,
    "imageUrl": "http://localhost:8080/uploads/images/abc123.jpg",
    "model3dPath": "c:\\path\\to\\model3d_1_20260108_123456.obj",
    "processedAt": "2026-01-08T12:34:56"
  }
]
```

#### 2. 특정 사용자의 3D 모델 조회
```http
GET http://localhost:5000/api/v1/model3d/models/1
```

#### 3. 최근 생성된 3D 모델 조회
```http
GET http://localhost:5000/api/v1/model3d/models/latest
```

#### 4. 3D 모델 생성 통계
```http
GET http://localhost:5000/api/v1/model3d/stats
```

**응답 예시:**
```json
{
  "totalCount": 10,
  "memberStats": {
    "1": 5,
    "2": 3,
    "3": 2
  },
  "recentModels": [...]
}
```

## 🧪 테스트 방법

### 방법 1: Python 테스트 스크립트 사용

`test_rabbitmq.py` 파일을 실행하여 직접 메시지를 전송합니다:

```bash
python test_rabbitmq.py
```

### 방법 2: RabbitMQ 관리 콘솔에서 수동 전송

1. http://localhost:15672/ 접속
2. **Queues** 탭 클릭
3. `model3d.upload.queue` 클릭
4. **Publish message** 섹션에서 메시지 입력:

**Payload:**
```json
{
  "imageUrl": "http://example.com/test-image.jpg",
  "memberId": 1,
  "timestamp": 1704672000000
}
```

5. **Publish message** 버튼 클릭

### 방법 3: Spring Boot에서 메시지 전송

Spring Boot 애플리케이션이 실행 중이라면, 이미지 업로드 API를 호출하여 자동으로 메시지가 전송됩니다:

```bash
curl -X POST http://localhost:8080/api/model3d/upload \
  -F "file=@test_image.jpg" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 📊 메시지 처리 확인

### 1. Flask 로그 확인
Flask 콘솔에 다음과 같은 로그가 표시됩니다:

```
=== 메시지 수신 ===
Message: {'imageUrl': 'http://example.com/test-image.jpg', 'memberId': 1, 'timestamp': 1704672000000}
이미지 다운로드 완료: 12345 bytes
이미지 저장 완료: c:\path\to\uploads\member_1_20260108_123456.jpg
Mock 3D 모델 생성: c:\path\to\uploads\models\model3d_1_20260108_123456.obj
=== 메시지 처리 완료 ===
Member ID: 1
Result: {'status': 'success', ...}
```

### 2. RabbitMQ 관리 콘솔 확인
- **Queues** 탭에서 `model3d.upload.queue`의 **Ready** 카운트가 0이면 정상 처리됨
- **Message rates** 그래프에서 메시지 처리 추이 확인

### 3. API로 확인
```bash
# 전체 모델 조회
curl http://localhost:5000/api/v1/model3d/models

# 최근 모델 조회
curl http://localhost:5000/api/v1/model3d/models/latest

# 통계 조회
curl http://localhost:5000/api/v1/model3d/stats
```

## 📂 생성되는 파일

메시지가 처리되면 다음 파일들이 생성됩니다:

1. **uploads/** - 다운로드된 이미지 파일
   - 예: `member_1_20260108_123456.jpg`

2. **uploads/models/** - 생성된 3D 모델 파일 (현재는 Mock)
   - 예: `model3d_1_20260108_123456.obj`

3. **uploads/logs/processing_log.json** - 처리 로그
   ```json
   [
     {
       "memberId": 1,
       "imageUrl": "http://example.com/test-image.jpg",
       "model3dPath": "c:\\path\\to\\model3d_1_20260108_123456.obj",
       "processedAt": "2026-01-08T12:34:56.789"
     }
   ]
   ```

## ⚙️ 환경 변수 설정 (선택사항)

`.env` 파일을 생성하여 RabbitMQ 설정을 커스터마이징할 수 있습니다:

```env
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USERNAME=guest
RABBITMQ_PASSWORD=guest

FLASK_ENV=development
PORT=5000
HOST=0.0.0.0
```

## 🐛 트러블슈팅

### 문제 1: Connection refused 에러
```
pika.exceptions.AMQPConnectionError: Connection to localhost:5672 failed
```

**해결책:**
- RabbitMQ 서버가 실행 중인지 확인
- Docker: `docker ps` 명령으로 컨테이너 확인
- 포트 5672가 열려있는지 확인

### 문제 2: 메시지가 Queue에 쌓이지만 처리되지 않음

**해결책:**
- Flask Consumer가 실행 중인지 확인
- 로그에서 "RabbitMQ Consumer 시작" 메시지 확인
- RabbitMQ 관리 콘솔에서 Consumer 연결 확인

### 문제 3: 이미지 다운로드 실패

**해결책:**
- imageUrl이 실제 접근 가능한 URL인지 확인
- 네트워크 연결 확인
- 방화벽/프록시 설정 확인

### 문제 4: pika 모듈 없음

**해결책:**
```bash
pip install pika==1.3.2
```

## 🔄 메시지 흐름

```
┌─────────────────┐      ┌──────────────┐      ┌────────────────┐
│  Spring Boot    │      │   RabbitMQ   │      │   Flask AI     │
│    Producer     │─────>│    Queue     │─────>│    Consumer    │
└─────────────────┘      └──────────────┘      └────────────────┘
        │                                              │
        │ 1. 이미지 업로드                              │
        │ 2. 메시지 발송                               │
        │                                              │ 3. 메시지 수신
        │                                              │ 4. 이미지 다운로드
        │                                              │ 5. 3D 모델 생성
        │                                              │ 6. 결과 저장
        │                                              │ 7. ACK 전송
```

## 📝 다음 단계

현재는 Mock 3D 모델 생성이지만, 실제 AI 모델을 연동하려면:

1. **app/utils/rabbitmq_consumer.py**의 `_generate_3d_mock` 메서드 수정
2. 실제 3D 생성 AI 모델 (TripoSR, InstantMesh 등) 통합
3. GPU 사용 설정
4. 처리 결과를 Spring Boot로 콜백 (선택사항)

## 🔗 관련 문서

- [RabbitMQ 공식 문서](https://www.rabbitmq.com/documentation.html)
- [Pika 문서](https://pika.readthedocs.io/)
- [Flask-RESTX 문서](https://flask-restx.readthedocs.io/)

---

**문의사항이나 문제가 발생하면 로그를 확인하거나 이슈를 등록해주세요!** 🚀
