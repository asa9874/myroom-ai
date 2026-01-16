"""
RabbitMQ Consumer 모듈

Spring Boot 애플리케이션에서 전송된 3D 모델 생성 요청을 
RabbitMQ를 통해 수신하고 처리합니다.
"""

import pika
import json
import logging
import os
import requests
import time
from datetime import datetime
from threading import Thread
from typing import Dict, Any

from .model3d_generator import Model3DGenerator

logger = logging.getLogger(__name__)


class RabbitMQProducer:
    """
    Flask에서 Spring Boot로 3D 모델 생성 완료 메시지를 전송하는 클래스
    """
    
    def __init__(self, config):
        """
        RabbitMQ Producer 초기화
        
        Args:
            config: Flask Config 딕셔너리 (RabbitMQ 설정 포함)
        """
        self.config = config
        self.credentials = pika.PlainCredentials(
            config['RABBITMQ_USERNAME'],
            config['RABBITMQ_PASSWORD']
        )
        self.parameters = pika.ConnectionParameters(
            host=config['RABBITMQ_HOST'],
            port=config['RABBITMQ_PORT'],
            credentials=self.credentials,
            heartbeat=600,
            blocked_connection_timeout=300
        )
        self.exchange = config['RABBITMQ_EXCHANGE']
        self.routing_key = config['RABBITMQ_RESPONSE_ROUTING_KEY']
    
    def send_generation_response(self, member_id, model3d_id, original_image_url, model3d_url,
                                 status, message, thumbnail_url=None,
                                 processing_time_seconds=None):
        """
        3D 모델 생성 완료 메시지 전송
        
        Args:
            member_id: 회원 ID
            model3d_id: 3D 모델 ID (DB)
            original_image_url: 원본 이미지 URL
            model3d_url: 생성된 3D 모델 URL (실패 시 임시 URL)
            status: 생성 상태 ("SUCCESS" 또는 "FAILED")
            message: 상태 메시지
            thumbnail_url: 썸네일 URL (선택)
            processing_time_seconds: 처리 시간(초) (선택)
            
        Returns:
            전송 성공 여부 (bool)
        """
        try:
            # RabbitMQ 연결
            connection = pika.BlockingConnection(self.parameters)
            channel = connection.channel()
            
            # Exchange 선언 (이미 있으면 기존 것 사용)
            channel.exchange_declare(
                exchange=self.exchange,
                exchange_type='topic',
                durable=True
            )
            
            # 메시지 생성 (Spring Boot의 Model3DGenerationResponse 형식에 맞춤)
            response_message = {
                "memberId": member_id,
                "model3dId": model3d_id,  # 3D 모델 ID 추가
                "originalImageUrl": original_image_url,
                "model3dUrl": model3d_url,
                "thumbnailUrl": thumbnail_url,
                "status": status,
                "message": message,
                "timestamp": int(time.time() * 1000),  # 밀리초 단위
                "processingTimeSeconds": processing_time_seconds
            }
            
            # JSON으로 변환
            message_body = json.dumps(response_message, ensure_ascii=False)
            
            # 메시지 전송
            channel.basic_publish(
                exchange=self.exchange,
                routing_key=self.routing_key,
                body=message_body,
                properties=pika.BasicProperties(
                    content_type='application/json',
                    delivery_mode=2  # 메시지를 디스크에 저장 (persistent)
                )
            )
            
            logger.info(f"[SUCCESS] Spring Boot로 메시지 전송 성공")
            logger.info(f"   memberId={member_id}, model3dId={model3d_id}, status={status}")
            logger.info(f"   메시지: {message}")
            
            # 연결 종료
            connection.close()
            
            return True
            
        except Exception as e:
            logger.error(f"[FAILED] Spring Boot로 메시지 전송 실패: {str(e)}")
            return False


class Model3DConsumer:
    """
    RabbitMQ Consumer 클래스
    
    Spring Boot에서 전송된 3D 모델 생성 메시지를 수신하고
    이미지를 다운로드하여 3D 모델을 생성합니다.
    """
    
    def __init__(self, config):
        """
        Consumer 초기화
        
        Args:
            config: Flask Config 객체 (RabbitMQ 설정 포함)
        """
        self.config = config
        self.credentials = pika.PlainCredentials(
            config['RABBITMQ_USERNAME'],
            config['RABBITMQ_PASSWORD']
        )
        self.parameters = pika.ConnectionParameters(
            host=config['RABBITMQ_HOST'],
            port=config['RABBITMQ_PORT'],
            credentials=self.credentials,
            heartbeat=600,  # 연결 유지를 위한 heartbeat
            blocked_connection_timeout=300  # 블록된 연결 타임아웃
        )
        self.queue_name = config['RABBITMQ_QUEUE']
        self.connection = None
        self.channel = None
        
        # Producer 인스턴스 생성 (Spring Boot로 메시지 전송용)
        self.producer = RabbitMQProducer(config)
        
        # 3D 모델 생성기 인스턴스 생성
        self.model_generator = Model3DGenerator()
        
    def callback(self, ch, method, properties, body):
        """
        메시지 수신 시 호출되는 콜백 함수
        
        Args:
            ch: 채널 객체
            method: 메시지 전달 방법
            properties: 메시지 속성
            body: 메시지 본문 (bytes)
        """
        try:
            # JSON 파싱
            message = json.loads(body.decode('utf-8'))
            
            logger.info(f"=== 메시지 수신 ===")
            logger.info(f"Message: {message}")
            
            image_url = message.get('imageUrl')
            member_id = message.get('memberId')
            model3d_id = message.get('model3dId')
            furniture_type = message.get('furnitureType')
            is_shared = message.get('isShared')
            timestamp = message.get('timestamp')
            
            if not image_url or not member_id or not model3d_id:
                raise ValueError("imageUrl, memberId, model3dId는 필수 필드입니다.")
            
            # 이미지 URL로 3D 모델 생성 처리 (새로운 필드 포함)
            result = self.process_3d_model(
                image_url=image_url,
                member_id=member_id,
                model3d_id=model3d_id,
                furniture_type=furniture_type,
                is_shared=is_shared,
                timestamp=timestamp
            )
            
            # 처리 성공 시 ACK
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
            logger.info(f"=== 메시지 처리 완료 ===")
            logger.info(f"Member ID: {member_id}, Model3D ID: {model3d_id}")
            logger.info(f"Result: {result}")
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {e}")
            logger.error(f"원본 메시지: {body}")
            # JSON 파싱 오류는 재시도해도 해결 불가능하므로 NACK (재시도 안 함)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
        except Exception as e:
            logger.error(f"메시지 처리 중 오류 발생: {e}", exc_info=True)
            # 일반 오류는 재시도 가능하도록 requeue=True
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def process_3d_model(self, image_url: str, member_id: int, model3d_id: int,
                        furniture_type: str = None, is_shared: bool = False,
                        timestamp: int = None) -> Dict[str, Any]:
        """
        3D 모델 생성 로직
        
        Args:
            image_url: 업로드된 이미지 URL
            member_id: 사용자 ID
            model3d_id: 3D 모델 ID (DB)
            furniture_type: 가구 타입
            is_shared: 공유 여부
            timestamp: 메시지 타임스탐프 (Unix timestamp)
            
        Returns:
            처리 결과 딕셔너리
        """
        logger.info(f"3D 모델 생성 시작: imageUrl={image_url}, memberId={member_id}, model3dId={model3d_id}")
        start_time = time.time()
        
        try:
            # 1. 이미지 다운로드
            image_data = self._download_image(image_url)
            logger.info(f"이미지 다운로드 완료: {len(image_data)} bytes")
            
            # 2. 이미지 저장
            image_path = self._save_image(image_data, member_id)
            logger.info(f"이미지 저장 완료: {image_path}")
            
            # 3. 벡터DB 메타데이터 저장 (3D 모델 생성 전)
            # 메타데이터: 3d_model_id, furniture_type, image_path, is_shared
            metadata_saved = self._save_metadata_to_vectordb(
                image_path=image_path,
                member_id=member_id,
                model3d_id=model3d_id,
                furniture_type=furniture_type,
                is_shared=is_shared
            )
            logger.info(f"메타데이터 저장: {'성공' if metadata_saved else '실패'}")
            
            # 4. AI 모델로 3D 생성 (실제 API 호출)
            logger.info("3D 모델 생성 중... (수 분 소요 가능)")
            model_3d_path = self._generate_3d_model(image_path, member_id)
            logger.info(f"3D 모델 생성 완료: {model_3d_path}")
            
            # 5. 처리 로그 저장 (선택사항)
            self._save_processing_log(member_id, image_url, model_3d_path, model3d_id, furniture_type, is_shared)
            
            # 6. 처리 시간 계산
            processing_time = int(time.time() - start_time)
            
            # 7. Spring Boot로 성공 메시지 전송
            # TODO: 실제 환경에서는 model_3d_url을 실제 접근 가능한 URL로 변경
            model_3d_url = f"http://localhost:5000/models/{os.path.basename(model_3d_path)}"
            
            self.producer.send_generation_response(
                member_id=member_id,
                model3d_id=model3d_id,  # model3d_id 추가
                original_image_url=image_url,
                model3d_url=model_3d_url,
                thumbnail_url=image_url,  # 원본 이미지를 썸네일로 사용
                status="SUCCESS",
                message="3D 모델 생성이 성공적으로 완료되었습니다.",
                processing_time_seconds=processing_time
            )
            
            return {
                'status': 'success',
                'imageUrl': image_url,
                'memberId': member_id,
                'model3dId': model3d_id,
                'furnitureType': furniture_type,
                'isShared': is_shared,
                'imagePath': image_path,
                'model3dPath': model_3d_path,
                'model3dUrl': model_3d_url,
                'metadataStored': metadata_saved,
                'timestamp': timestamp,
                'processedAt': datetime.now().isoformat(),
                'processingTimeSeconds': processing_time
            }
            
        except Exception as e:
            logger.error(f"3D 모델 생성 실패: {e}", exc_info=True)
            
            # 처리 시간 계산
            processing_time = int(time.time() - start_time)
            
            # 실패 시에도 임시 URL 생성 (디버깅/추적용)
            temp_model_3d_url = f"http://localhost:5000/models/failed_url_model3d_id_{model3d_id}_member_{member_id}.glb"
            
            # Spring Boot로 실패 메시지 전송
            self.producer.send_generation_response(
                member_id=member_id,
                model3d_id=model3d_id,  # model3d_id 추가
                original_image_url=image_url,
                model3d_url=temp_model_3d_url,  # 임시 URL 반환
                thumbnail_url=image_url,  # 원본 이미지를 썸네일로 사용
                status="FAILED",
                message=f"3D 모델 생성 실패: {str(e)}",
                processing_time_seconds=processing_time
            )
            
            return {
                'status': 'failed',
                'imageUrl': image_url,
                'memberId': member_id,
                'model3dId': model3d_id,
                'furnitureType': furniture_type,
                'isShared': is_shared,
                'model3dUrl': temp_model_3d_url,  # 임시 URL 포함
                'error': str(e),
                'timestamp': timestamp,
                'processedAt': datetime.now().isoformat(),
                'processingTimeSeconds': processing_time
            }
    
    def _download_image(self, image_url: str) -> bytes:
        """
        이미지 URL에서 이미지 다운로드
        
        Args:
            image_url: 이미지 URL
            
        Returns:
            이미지 바이너리 데이터
        """
        try:
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            logger.error(f"이미지 다운로드 실패: {image_url}, 오류: {e}")
            raise
    
    def _save_image(self, image_data: bytes, member_id: int) -> str:
        """
        다운로드한 이미지를 로컬에 저장
        
        Args:
            image_data: 이미지 바이너리 데이터
            member_id: 사용자 ID
            
        Returns:
            저장된 이미지 경로
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"member_{member_id}_{timestamp}.jpg"
        filepath = os.path.join(self.config['UPLOAD_FOLDER'], filename)
        
        # 디렉토리가 없으면 생성
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        return filepath
    
    def _generate_3d_model(self, image_path: str, member_id: int) -> str:
        """
        3D 모델 생성기를 사용하여 3D 모델 생성
        
        최적화 파라미터:
        - ss_sampling_steps: 20 (기본 30 → 20으로 감소, ~33% 빠름)
        - slat_sampling_steps: 20 (기본 30 → 20으로 감소, ~33% 빠름)
        - mesh_simplify_ratio: 0.85 (기본 0.95 → 0.85로 감소, 더 단순한 메시 구조)
        - texture_size: 512 (기본 1024 → 512로 감소, 텍스처 처리 시간 ~75% 단축)
        
        Args:
            image_path: 이미지 경로
            member_id: 사용자 ID
            
        Returns:
            생성된 3D 모델 파일 경로 (.glb)
        """
        return self.model_generator.generate_3d_model(
            image_path=image_path,
            output_dir=self.config['MODEL3D_FOLDER'],
            member_id=member_id,
            # 성능 최적화 파라미터
            ss_sampling_steps=20,          # 기본값 30 → 20 (33% 빠름)
            slat_sampling_steps=20,        # 기본값 30 → 20 (33% 빠름)
            mesh_simplify_ratio=0.85,      # 기본값 0.95 → 0.85 (더 단순한 메시)
            texture_size=512               # 기본값 1024 → 512 (75% 빠름, 여전히 충분한 품질)
        )
    
    def _save_metadata_to_vectordb(self, image_path: str, member_id: int, model3d_id: int,
                                   furniture_type: str = None, is_shared: bool = False) -> bool:
        """
        벡터DB에 메타데이터 저장 (이미지와 함께 학습용 메타정보 저장)
        
        Args:
            image_path: 이미지 파일 경로
            member_id: 회원 ID
            model3d_id: 3D 모델 ID (DB)
            furniture_type: 가구 타입
            is_shared: 공유 여부
            
        Returns:
            저장 성공 여부
        """
        try:
            from .clip_vectorizer import CLIPVectorizer
            
            # CLIPVectorizer 인스턴스 생성 (싱글톤 패턴으로 변경 권장)
            vectorizer = CLIPVectorizer()
            
            # 메타데이터 딕셔너리 생성 (3d_model_id, furniture_type, image_path, is_shared)
            metadata_dict = {
                "model3d_id": model3d_id,
                "furniture_type": furniture_type if furniture_type else "unknown",
                "image_path": image_path,
                "is_shared": is_shared,
                "member_id": member_id
            }
            
            # 벡터DB에 추가 (이미지 임베딩 + 메타데이터)
            success = vectorizer.add_image_to_database(
                image_path=image_path,
                furniture_type=furniture_type if furniture_type else "unknown",
                metadata_dict=metadata_dict
            )
            
            if success:
                logger.info(f"벡터DB 메타데이터 저장 성공: model3dId={model3d_id}, furnitureType={furniture_type}")
                # 벡터DB 저장 (필요시 활성화)
                # vectorizer.save_database(self.config.get('VECTORDB_PATH', 'vectordb.pkl'))
            else:
                logger.warning(f"벡터DB 메타데이터 저장 실패: model3dId={model3d_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"벡터DB 메타데이터 저장 중 오류: {e}", exc_info=True)
            return False
    
    def _save_processing_log(self, member_id: int, image_url: str, model_path: str,
                            model3d_id: int = None, furniture_type: str = None,
                            is_shared: bool = False):
        """
        처리 로그 저장 (선택사항)
        
        Args:
            member_id: 사용자 ID
            image_url: 원본 이미지 URL
            model_path: 생성된 3D 모델 경로
            model3d_id: 3D 모델 ID (DB)
            furniture_type: 가구 타입
            is_shared: 공유 여부
        """
        log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'uploads', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, 'processing_log.json')
        
        log_entry = {
            'memberId': member_id,
            'model3dId': model3d_id,
            'imageUrl': image_url,
            'model3dPath': model_path,
            'furnitureType': furniture_type,
            'isShared': is_shared,
            'processedAt': datetime.now().isoformat()
        }
        
        # 로그 파일에 추가
        try:
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            else:
                logs = []
            
            logs.append(log_entry)
            
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.warning(f"로그 저장 실패: {e}")
    
    def start_consuming(self):
        """
        RabbitMQ 메시지 수신 시작
        블로킹 방식으로 계속 메시지를 대기합니다.
        """
        try:
            self.connection = pika.BlockingConnection(self.parameters)
            self.channel = self.connection.channel()
            
            # Queue 존재 확인 (없으면 생성)
            self.channel.queue_declare(queue=self.queue_name, durable=True)
            
            # Prefetch count 설정 (한 번에 하나의 메시지만 처리)
            self.channel.basic_qos(prefetch_count=1)
            
            # Consumer 등록
            self.channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=self.callback,
                auto_ack=False  # 수동 ACK 사용
            )
            
            logger.info(f"==========================================")
            logger.info(f"RabbitMQ Consumer 시작")
            logger.info(f"Queue: {self.queue_name}")
            logger.info(f"Host: {self.config['RABBITMQ_HOST']}:{self.config['RABBITMQ_PORT']}")
            logger.info(f"메시지 대기 중... (종료하려면 CTRL+C)")
            logger.info(f"==========================================")
            
            self.channel.start_consuming()
            
        except KeyboardInterrupt:
            logger.info("Consumer 종료 중...")
            self.stop_consuming()
            
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"RabbitMQ 연결 실패: {e}")
            logger.error("RabbitMQ 서버가 실행 중인지 확인하세요.")
            raise
            
        except Exception as e:
            logger.error(f"Consumer 실행 중 오류 발생: {e}", exc_info=True)
            raise
    
    def stop_consuming(self):
        """
        RabbitMQ 메시지 수신 중지
        """
        if self.channel and self.channel.is_open:
            logger.info("채널 종료 중...")
            self.channel.stop_consuming()
            self.channel.close()
        
        if self.connection and self.connection.is_open:
            logger.info("연결 종료 중...")
            self.connection.close()
        
        logger.info("Consumer 종료 완료")


def start_consumer_thread(app):
    """
    별도 스레드에서 RabbitMQ Consumer 실행
    
    Args:
        app: Flask 애플리케이션 인스턴스
    """
    with app.app_context():
        consumer = Model3DConsumer(app.config)
        consumer.start_consuming()
