# MyRoom - AI Server
3D 방 꾸미기와 커뮤니티 경험을 제공하는 MyRoom 플랫폼의 AI 및 3D 데이터 처리 파이프라인 서버.

[Spring Boot 백엔드 레포지토리](https://github.com/사용자계정/myroom-backend)

## Features
- REST API: Flask-RESTX 기반 API 제공 및 Swagger UI 자동 문서화
- 3D 모델 생성: 2D 가구 이미지를 3D 객체(GLB 등)로 자동 변환 (Model3D)
- 룸/도면 분석: 도면이나 방 사진을 기반으로 3D 공간 구조 시각화 (Room3D)
- AI 가구 추천: CLIP 모델 및 FAISS(VectorDB)를 활용한 이미지 기반 유사 가구 추천 파이프라인
- 치수 및 메타데이터 관리: 3D 모델의 실제 Bounding Box 치수 추출 및 VectorDB 동기화 로직
- 비동기 처리: RabbitMQ를 활용한 무거운 AI 연산의 다중 Consumer 분산 처리
- GUI 도구: CustomTkinter 기반 파라미터 조율 및 테스트용 데스크톱 애플리케이션 지원

## Tech Stack
| 영역 | 기술 |
| --- | --- |
| Backend | Python 3, Flask, Flask-RESTX |
| AI / Vision | PyTorch, Transformers (CLIP), Ultralytics (YOLO) |
| 3D Processing | Trimesh, Panda3D |
| Vector Search | FAISS |
| Messaging | RabbitMQ (Pika) |
| Storage | AWS S3 (boto3) |
| Etc | CustomTkinter, OpenCV, Pillow, Rembg |

## Architecture & Flows
### 백그라운드 Consumer 아키텍처
Spring Boot 백엔드에서 발행(Publish)된 메시지를 수신하여, 별도의 스레드에서 비동기적으로 작업을 수행합니다.
- **Model3D Consumer**: 3D 모델 생성 파이프라인 실행 및 S3 업로드
- **Room3D Consumer**: 도면 기반 3D 방 구조 해석 및 생성
- **Recommendation Consumer**: FAISS를 통한 유사 모델 검색 후 백엔드로 콜백
- **Dimensions Consumer**: 3D 모델의 실제 치수 추출
- **Metadata Consumer**: VectorDB 아이템 추가, 업데이트 및 삭제 동기화 로직

## Installation & Usage
### 사전 요구사항
- Python 3.8+
- Docker Desktop (RabbitMQ) 또는 로컬 설치
- (선택) AWS S3 자격 증명

### 로컬 실행
1) 인프라 기동 (RabbitMQ)
```bash
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
```

2) 의존성 설치
```bash
pip install -r requirements.txt
```

3) 애플리케이션 실행
```bash
# 기본 API 및 Consumer 워커 실행
python main.py

# 파라미터 조율용 로컬 GUI와 함께 실행
python main.py -ui

# S3 파일 업로드 기능 활성화
python main.py -s3
```

4) 확인
- Swagger UI API 문서: http://localhost:5000/docs
- RabbitMQ 관리 UI: http://localhost:15672

### 프로파일 및 설정
- 환경 설정: 프로젝트 루트의 `.env` 파일을 로드하여 포트 및 브로커 정보를 설정합니다.
- AI 파라미터: [config/model3d_params.json](config/model3d_params.json) 파일로 3D 변환 세부 수치를 관리합니다.

#### .env 기본값 예시
```env
FLASK_ENV=development
PORT=5000
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USERNAME=guest
RABBITMQ_PASSWORD=guest
```

## Project Structure
```
myroom-ai/
  app/
    models/             # 데이터 모델 및 스키마
    recommand/          # CLIP 벡터화 및 FAISS 검색 로직
    routes/             # REST API 엔드포인트 (health, model3d_params 등)
    utils/              # Consumer 워커, 모델 생성, S3 관리 등 핵심 서비스
  config/               # JSON 파라미터 설정
  gui/                  # 로컬 테스트용 CustomTkinter 뷰어 및 패널
  module/               # 이미지 전처리 및 품질 검증 모듈
  main.py               # 서버 엔트리포인트
  requirements.txt
```
