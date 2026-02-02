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
from typing import Dict, Any, Tuple

from .model3d_generator import Model3DGenerator
from .s3_manager import S3Manager

logger = logging.getLogger(__name__)


class ImageQualityError(Exception):
    """이미지 품질 검증 실패 예외"""
    
    def __init__(self, score: float, issues: list, recommendations: list, message: str = None):
        self.score = score
        self.issues = issues
        self.recommendations = recommendations
        self.message = message or f"이미지 품질 미달 ({score:.1f}점)"
        super().__init__(self.message)
    
    def to_dict(self) -> dict:
        """예외 정보를 딕셔너리로 변환"""
        return {
            'error_type': 'IMAGE_QUALITY_FAILED',
            'score': self.score,
            'issues': self.issues,
            'recommendations': self.recommendations,
            'message': self.message
        }


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
        
        # S3 사용 여부 (config에서 읽기, 기본값: False)
        self.use_s3 = config.get('USE_S3', False)
        
        logger.info(f"S3 업로드 설정: {'활성화' if self.use_s3 else '비활성화'}")
        
        # Producer 인스턴스 생성 (Spring Boot로 메시지 전송용)
        self.producer = RabbitMQProducer(config)
        
        # 3D 모델 생성기 인스턴스 생성
        self.model_generator = Model3DGenerator()
        
        # S3 Manager 인스턴스 생성 (S3 사용 시에만)
        if self.use_s3:
            self.s3_manager = S3Manager(config)
        else:
            self.s3_manager = None
            logger.info("S3 Manager 비활성화됨 (로컬 URL 사용)")
        
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
            
            # 3. AI 모델로 3D 생성 (실제 API 호출)
            logger.info("3D 모델 생성 중... (수 분 소요 가능)")
            model_3d_path = self._generate_3d_model(image_path, member_id)
            logger.info(f"3D 모델 생성 완료: {model_3d_path}")
            
            # 3-1. � S3 사용 여부에 따라 처리
            if self.use_s3:
                # S3에 업로드
                logger.info("S3에 3D 모델 업로드 중...")
                s3_upload_success, model_3d_url = self._upload_model_to_s3(
                    model_3d_path, member_id, model3d_id
                )
                
                if not s3_upload_success:
                    raise Exception(f"S3 업로드 실패: {model_3d_url}")
                
                logger.info(f"[OK] S3 업로드 성공: {model_3d_url}")
            else:
                # 로컬 URL 생성
                logger.info("로컬 URL 생성 중...")
                model_3d_url = f"http://localhost:5000/models/{os.path.basename(model_3d_path)}"
                logger.info(f"[OK] 로컬 URL 생성: {model_3d_url}")
            
            # 4. 3D 모델 생성 성공 후 VectorDB에 메타데이터 저장
            # 생성 성공한 모델 정보를 메타데이터에 포함
            logger.info("VectorDB에 메타데이터 저장 중...")
            metadata_saved = self._save_metadata_to_vectordb(
                image_path=image_path,
                member_id=member_id,
                model3d_id=model3d_id,
                model3d_path=model_3d_path,  # 생성된 3D 모델 경로 포함
                furniture_type=furniture_type,
                is_shared=is_shared
            )
            logger.info(f"VectorDB 메타데이터 저장: {'성공' if metadata_saved else '실패'}")
            
            # 5. 처리 로그 저장 (선택사항)
            self._save_processing_log(member_id, image_url, model_3d_path, model3d_id, furniture_type, is_shared)
            
            # 6. 처리 시간 계산
            processing_time = int(time.time() - start_time)
            
            # 7. Spring Boot로 성공 메시지 전송
            # S3에서 반환받은 URL을 직접 사용
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
        
        except ImageQualityError as e:
            # 이미지 품질 검증 실패 (FAILED로 처리)
            logger.warning(f"[품질검증실패] {e.message}")
            logger.warning(f"  - 점수: {e.score:.1f}점")
            logger.warning(f"  - 문제점: {e.issues}")
            
            processing_time = int(time.time() - start_time)
            
            # 품질 실패 전용 URL 생성
            if self.use_s3:
                temp_model_3d_url = f"s3://{self.config.get('AWS_S3_BUCKET_NAME', 'unknown-bucket')}/quality_failed/model3d_id_{model3d_id}_member_{member_id}.glb"
            else:
                temp_model_3d_url = f"http://localhost:5000/models/quality_failed_model3d_id_{model3d_id}_member_{member_id}.glb"
            
            # Spring Boot로 품질 검증 실패 메시지 전송 (FAILED 상태 사용)
            error_message = f"[품질미달] 이미지 품질 미달 ({e.score:.1f}점): {', '.join(e.issues[:2]) if e.issues else '품질 기준 미충족'}"
            if e.recommendations:
                error_message += f" | 권장사항: {e.recommendations[0]}"
            
            self.producer.send_generation_response(
                member_id=member_id,
                model3d_id=model3d_id,
                original_image_url=image_url,
                model3d_url=temp_model_3d_url,
                thumbnail_url=image_url,
                status="FAILED",  # Spring Boot enum: SUCCESS, FAILED, PROCESSING
                message=error_message,
                processing_time_seconds=processing_time
            )
            
            return {
                'status': 'quality_failed',
                'imageUrl': image_url,
                'memberId': member_id,
                'model3dId': model3d_id,
                'furnitureType': furniture_type,
                'isShared': is_shared,
                'model3dUrl': temp_model_3d_url,
                'error': e.message,
                'quality_info': e.to_dict(),
                'timestamp': timestamp,
                'processedAt': datetime.now().isoformat(),
                'processingTimeSeconds': processing_time
            }
            
        except Exception as e:
            logger.error(f"3D 모델 생성 실패: {e}", exc_info=True)
            
            # 처리 시간 계산
            processing_time = int(time.time() - start_time)
            
            # 실패 URL 생성 (S3 사용 여부에 따라 다름)
            if self.use_s3:
                temp_model_3d_url = f"s3://{self.config.get('AWS_S3_BUCKET_NAME', 'unknown-bucket')}/error/failed_model3d_id_{model3d_id}_member_{member_id}.glb"
            else:
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
    
    def _generate_3d_model(self, image_path: str, member_id: int) -> dict:
        """
        3D 모델 생성기를 사용하여 3D 모델 생성 (품질 검증 통합)
        
        품질 검증 후 품질 등급에 따라 최적화된 파라미터로 3D 모델을 생성합니다.
        
        Args:
            image_path: 이미지 경로
            member_id: 사용자 ID
            
        Returns:
            dict: {
                'success': bool,
                'model_path': str or None,
                'quality_result': dict,  # 품질 검증 결과
                'error': str or None
            }
            
        Raises:
            ImageQualityError: 품질 검증 실패 시
        """
        # 설정에서 품질 검증 옵션 가져오기
        quality_check_enabled = self.config.get('QUALITY_CHECK_ENABLED', True)
        strict_mode = self.config.get('QUALITY_CHECK_STRICT_MODE', False)
        
        logger.info(f"[3D생성] 품질검증={quality_check_enabled}, 엄격모드={strict_mode}")
        
        if quality_check_enabled:
            # 품질 검증이 통합된 3D 모델 생성
            result = self.model_generator.generate_3d_model_with_validation(
                image_path=image_path,
                output_dir=self.config['MODEL3D_FOLDER'],
                member_id=member_id,
                strict_mode=strict_mode
            )
            
            if not result['success']:
                # 품질 검증 실패 또는 3D 생성 실패
                quality_info = result.get('quality_validation', {})
                error_msg = result.get('error', 'unknown')
                
                if error_msg == 'quality_failed':
                    # 품질 미달로 인한 실패
                    score = quality_info.get('score', 0)
                    issues = quality_info.get('issues', [])
                    raise ImageQualityError(
                        score=score,
                        issues=issues,
                        recommendations=quality_info.get('recommendations', []),
                        message=f"이미지 품질 미달 ({score:.1f}점): {', '.join(issues[:2]) if issues else '품질 기준 미충족'}"
                    )
                else:
                    # 기타 오류
                    raise Exception(result.get('message', '3D 모델 생성 실패'))
            
            logger.info(f"[3D생성] 성공 - 품질: {result['quality_validation'].get('quality_tier', 'unknown')}, "
                        f"점수: {result['quality_validation'].get('score', 0):.1f}점")
            return result['model_path']
        else:
            # 품질 검증 없이 기존 방식으로 생성
            return self.model_generator.generate_3d_model(
                image_path=image_path,
                output_dir=self.config['MODEL3D_FOLDER'],
                member_id=member_id,
                ss_sampling_steps=20,
                slat_sampling_steps=20,
                mesh_simplify_ratio=0.85,
                texture_size=512
            )
    
    def _upload_model_to_s3(self, model_3d_path: str, member_id: int, model3d_id: int) -> Tuple[bool, str]:
        """
        생성된 3D 모델을 S3에 업로드
        
        Args:
            model_3d_path: 로컬 3D 모델 파일 경로
            member_id: 회원 ID
            model3d_id: 3D 모델 ID (DB)
            
        Returns:
            (업로드 성공 여부, S3 URL 또는 에러 메시지) 튜플
        """
        try:
            if not self.use_s3:
                raise Exception("S3 업로드가 비활성화되었습니다.")
            
            if not self.s3_manager:
                raise Exception("S3 Manager가 초기화되지 않았습니다. AWS 자격증명을 확인하세요.")
            
            if not self.s3_manager.is_available():
                raise Exception("S3 서비스를 사용할 수 없습니다.")
            
            success, s3_url = self.s3_manager.upload_model_3d(
                file_path=model_3d_path,
                member_id=member_id,
                model3d_id=model3d_id
            )
            
            return success, s3_url
            
        except Exception as e:
            logger.error(f"S3 업로드 중 오류: {e}", exc_info=True)
            return False, str(e)
    
    
    def _save_metadata_to_vectordb(self, image_path: str, member_id: int, model3d_id: int,
                                   model3d_path: str = None, furniture_type: str = None, is_shared: bool = False) -> bool:
        """
        벡터DB에 메타데이터 저장 (이미지와 함께 학습용 메타정보 저장)
        
        Args:
            image_path: 이미지 파일 경로
            member_id: 회원 ID
            model3d_id: 3D 모델 ID (DB)
            model3d_path: 생성된 3D 모델 경로 (선택사항, 성공 시에만)
            furniture_type: 가구 타입
            is_shared: 공유 여부
            
        Returns:
            저장 성공 여부
        """
        try:
            # 올바른 임포트 경로: app.recommand에서 가져오기
            from app.recommand.clip_vectorizer import CLIPVectorizer
            import os
            
            # FIX: 새 인스턴스 생성 후 기존 데이터를 먼저 로드!
            vectorizer = CLIPVectorizer()
            
            # 기존 VectorDB 데이터가 있으면 로드 (덮어씌우지 않도록!)
            upload_folder = os.path.abspath(
                os.path.join(os.path.dirname(__file__), '..', '..', 'uploads')
            )
            db_index_path = os.path.join(upload_folder, 'furniture_index.faiss')
            db_metadata_path = os.path.join(upload_folder, 'furniture_metadata.pkl')
            
            # 기존 데이터 로드 (있으면)
            if os.path.exists(db_index_path) and os.path.exists(db_metadata_path):
                logger.info(f"기존 VectorDB 로드 중: {db_index_path}")
                vectorizer.load_database(db_index_path, db_metadata_path)
                logger.info(f"[OK] 기존 VectorDB 로드 완료: {vectorizer.index.ntotal} items")
            
            # 메타데이터 딕셔너리 생성 (3D 모델 경로 포함)
            metadata_dict = {
                "model3d_id": model3d_id,
                "furniture_type": furniture_type if furniture_type else "unknown",
                "image_path": image_path,
                "model3d_path": model3d_path,  # 생성된 3D 모델 경로
                "is_shared": is_shared,
                "member_id": member_id,
                "created_at": datetime.now().isoformat()  # 생성 시간
            }
            
            # 벡터DB에 추가 (이미지 임베딩 + 메타데이터)
            success = vectorizer.add_image_to_database(
                image_path=image_path,
                furniture_type=furniture_type if furniture_type else "unknown",
                metadata_dict=metadata_dict
            )
            
            if success:
                logger.info(f"[OK] 벡터DB 메타데이터 저장 성공:")
                logger.info(f"   - model3dId: {model3d_id}")
                logger.info(f"   - furnitureType: {furniture_type}")
                logger.info(f"   - imagePath: {image_path}")
                logger.info(f"   - model3dPath: {model3d_path}")
                logger.info(f"   - memberId: {member_id}")
                
                # CRITICAL: 벡터DB를 디스크에 저장해야 조회 가능!
                import os
                upload_folder = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), '..', '..', 'uploads')
                )
                os.makedirs(upload_folder, exist_ok=True)
                
                db_index_path = os.path.join(upload_folder, 'furniture_index.faiss')
                db_metadata_path = os.path.join(upload_folder, 'furniture_metadata.pkl')
                
                # 디스크에 저장
                if vectorizer.save_database(db_index_path, db_metadata_path):
                    logger.info(f"VectorDB 메타데이터 저장: 성공")
                else:
                    logger.warning(f"VectorDB 메타데이터 디스크 저장 실패")
            else:
                logger.warning(f"[FAIL] 벡터DB 메타데이터 저장 실패: model3dId={model3d_id}")
            
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
