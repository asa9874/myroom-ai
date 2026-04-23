# Room3D AI 연동 참고 문서

## 1. 전체 처리 흐름
1. 클라이언트가 도면 이미지를 업로드한다.
2. 백엔드가 이미지를 S3의 room3d/images/ 경로에 저장한다.
3. 백엔드가 Room3D 레코드를 먼저 저장한다.
   - drawing_xml_url = null
   - success = null
4. 백엔드가 RabbitMQ로 AI 요청 메시지를 발행한다.
5. AI 서버가 도면 분석/생성을 완료한 뒤 RabbitMQ 응답 메시지를 발행한다.
6. 백엔드 Consumer가 응답을 수신해서 DB를 업데이트한다.
   - SUCCESS: success = true, drawing_xml_url 저장
   - FAILED: success = false, drawing_xml_url = null

## 2. RabbitMQ 계약

### 2-1. 요청 채널
- exchange: room3d.exchange
- queue: room3d.request.queue
- routing key: room3d.request

### 2-2. 응답 채널
- exchange: room3d.exchange
- queue: room3d.response.queue
- routing key: room3d.response

## 3. AI 요청 메시지 스키마

필수 필드 중심으로 전송한다.

```json
{
  "room3dId": 12,
  "memberId": 5,
  "drawingImageUrl": "https://asa-room.s3.amazonaws.com/room3d/images/0d3b...png",
  "roomName": "안방",
  "description": "붙박이장이 있는 안방",
  "timestamp": 1776903000000
}
```

필드 설명:
- room3dId: 백엔드 DB 식별자. 응답 시 반드시 동일한 값으로 돌려줘야 함.
- memberId: 요청 사용자 식별자.
- drawingImageUrl: AI 서버가 읽어야 할 도면 이미지 URL.
- roomName: 방 이름.
- description: 방 설명(없으면 null 가능).
- timestamp: 요청 생성 시각(ms).

## 4. AI 응답 메시지 스키마

AI 서버는 아래 구조로 응답 메시지를 발행한다.

```json
{
  "room3dId": 12,
  "memberId": 5,
  "status": "SUCCESS",
  "xmlFileUrl": "https://asa-room.s3.amazonaws.com/room3d/xml/8f1d...xml",
  "message": "completed",
  "timestamp": 1776903012000
}
```

status 규칙:
- SUCCESS
  - xmlFileUrl 필수
  - 백엔드는 success=true, drawing_xml_url=xmlFileUrl 로 저장
- FAILED
  - xmlFileUrl은 null 가능
  - 백엔드는 success=false, drawing_xml_url=null 로 저장

## 5. 백엔드 API 요약

### 5-1. 생성
- POST /api/room3d
- multipart/form-data
  - image: 필수
  - room_name: 필수
  - description: 선택

### 5-2. 수정
- PUT /api/room3d/{room3dId}
- multipart/form-data
  - room_name: 선택
  - description: 선택
  - xml_file: 선택

수정 시 xml_file이 존재하면 기존 XML 파일을 S3에서 삭제하고 새 XML URL로 교체한다.

### 5-3. 단일 조회
- GET /api/room3d/{room3dId}
- 본인 데이터만 조회 가능

### 5-4. 내 목록 조회(페이지네이션)
- GET /api/room3d/my?page=0&size=10&sort=createdAt,desc
- success 상태와 무관하게 전체 반환

### 5-5. 삭제
- DELETE /api/room3d/{room3dId}
- DB row 삭제 + S3 도면 이미지/XML 파일 삭제

## 6. AI 서버 구현 시 주의사항
- 응답의 room3dId, memberId는 요청값 그대로 유지해야 한다.
- SUCCESS인데 xmlFileUrl이 비어 있으면 백엔드에서 예외로 처리된다.
- 상태값은 SUCCESS 또는 FAILED를 사용한다.
- 메시지는 JSON 변환 가능한 구조로 발행한다.
- 재시도 시 같은 room3dId로 중복 응답이 들어갈 수 있으므로, AI 서버는 동일 요청 중복 발행을 피하는 것이 좋다.
