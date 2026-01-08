# RabbitMQ 플로우 간단 요약

## 📋 개요
MyRoom AI 프로젝트는 Spring Boot 백엔드에서 전송된 3D 모델 생성 요청을 RabbitMQ를 통해 Flask AI 서버에서 비동기로 처리합니다.

---

## 🔄 전체 플로우

```
[Spring Boot 서버] 
    ↓ 메시지 발행
[RabbitMQ Queue: model3d.upload.queue]
    ↓ 메시지 수신
[Flask AI 서버 - Consumer Thread]
    ↓ 처리
[3D 모델 생성 → 저장]
```

---

## 🛠️ 구성 요소

### 1️⃣ RabbitMQ 설정 (config.py)
```python
RABBITMQ_HOST = 'localhost'          # RabbitMQ 서버 주소
RABBITMQ_PORT = 5672                 # RabbitMQ 포트
RABBITMQ_USERNAME = 'guest'          # 인증 사용자명
RABBITMQ_PASSWORD = 'guest'          # 인증 비밀번호
RABBITMQ_QUEUE = 'model3d.upload.queue'  # 큐 이름
```

### 2️⃣ Consumer 실행 (main.py)
- Flask 서버 시작 시 **별도 스레드**로 RabbitMQ Consumer 실행
- 데몬 스레드로 동작하여 메인 서버와 독립적으로 작동
- RabbitMQ 연결 실패 시에도 Flask 서버는 정상 실행

```python
consumer_thread = Thread(
    target=start_consumer_thread,
    args=(app,),
    daemon=True,
    name='RabbitMQ-Consumer'
)
```

### 3️⃣ 메시지 수신 및 처리 (rabbitmq_consumer.py)

#### 📨 메시지 포맷
```json
{
  "imageUrl": "http://example.com/image.jpg",
  "memberId": 12345,
  "timestamp": 1704729600000
}
```

#### ⚙️ 처리 단계
1. **메시지 수신** - RabbitMQ 큐에서 메시지 받기
2. **JSON 파싱** - 메시지 본문을 JSON으로 변환
3. **이미지 다운로드** - `imageUrl`에서 이미지 다운로드
4. **이미지 저장** - `uploads/` 폴더에 저장
5. **3D 모델 생성** - AI 모델로 3D 변환 (현재는 Mock)
6. **3D 파일 저장** - `uploads/models/` 폴더에 .obj 파일 저장
7. **ACK 전송** - 처리 완료 후 RabbitMQ에 확인 응답

---

## ✅ 에러 처리

### JSON 파싱 오류
- **NACK (requeue=False)** - 재시도해도 해결 불가능하므로 버림
- 잘못된 메시지 형식으로 재처리해도 의미 없음

### 일반 처리 오류
- **NACK (requeue=True)** - 재시도 가능하도록 큐에 다시 넣음
- 네트워크 오류, 일시적 장애 등은 재처리로 해결 가능

### 처리 성공
- **ACK** - 정상 처리 완료, 큐에서 메시지 제거

---

## 📁 파일 저장 구조

```
myroom-ai/
├── uploads/
│   ├── image_12345_20260108_215720.jpg    # 다운로드된 이미지
│   └── models/
│       └── model3d_12345_20260108_215721.obj  # 생성된 3D 모델
```

---

## 🔧 현재 상태

### ✅ 구현 완료
- RabbitMQ 연결 및 메시지 수신
- 이미지 다운로드 및 저장
- 에러 핸들링 (ACK/NACK)
- 로깅 시스템

### 🚧 TODO (Mock 처리 중)
- **실제 AI 3D 모델 생성 연동**
  - TripoSR
  - InstantMesh
  - 기타 Image-to-3D 모델

---

## 🔍 주요 메서드

| 메서드 | 역할 |
|--------|------|
| `Model3DConsumer.__init__()` | RabbitMQ 연결 설정 초기화 |
| `callback()` | 메시지 수신 시 호출되는 콜백 |
| `process_3d_model()` | 3D 모델 생성 전체 프로세스 |
| `_download_image()` | 이미지 URL에서 다운로드 |
| `_save_image()` | 이미지 파일 저장 |
| `_generate_3d_mock()` | 3D 모델 생성 (Mock) |
| `start_consuming()` | Consumer 시작 |
| `stop_consuming()` | Consumer 종료 |

---

## 🚀 실행 방법

```bash
# RabbitMQ 서버 실행 (Docker 예시)
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:management

# Flask 서버 실행 (RabbitMQ Consumer 자동 시작)
python main.py
```

---

## 📊 로그 확인

Consumer가 정상 작동하면 다음과 같은 로그가 출력됩니다:

```
[INFO] RabbitMQ Consumer 스레드 시작됨
==========================================
RabbitMQ Consumer 시작
Queue: model3d.upload.queue
Host: localhost:5672
메시지 대기 중... (종료하려면 CTRL+C)
==========================================
```

메시지 수신 시:
```
=== 메시지 수신 ===
Message: {'imageUrl': '...', 'memberId': 12345, 'timestamp': ...}
이미지 다운로드 완료: 12345 bytes
이미지 저장 완료: uploads/image_12345_20260108.jpg
3D 모델 생성 완료: uploads/models/model3d_12345_20260108.obj
=== 메시지 처리 완료 ===
```

---

## 🔒 보안 고려사항

- **환경 변수 사용**: 프로덕션에서는 `RABBITMQ_USERNAME`, `RABBITMQ_PASSWORD`를 환경 변수로 설정
- **SSL/TLS**: 프로덕션 환경에서는 암호화된 연결 사용 권장
- **이미지 검증**: 다운로드한 이미지의 유효성 검사 필요

---

## 📝 메모

- Consumer는 **수동 ACK 모드** 사용 (`auto_ack=False`)
- **Heartbeat 600초**: 장시간 처리를 위한 연결 유지
- **Daemon Thread**: Flask 서버 종료 시 자동 종료
- 현재 3D 생성은 Mock으로 처리, 실제 AI 모델 연동 필요
