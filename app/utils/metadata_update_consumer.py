"""
VectorDB 메타데이터 업데이트 Consumer

Spring Boot 서버에서 전송된 3D 모델 메타데이터 업데이트 메시지를 
RabbitMQ를 통해 수신하고 VectorDB를 업데이트합니다.

메시지 형식:
{
    "model3d_id": Long,
    "member_id": Long,
    "name": String,
    "description": String (nullable),
    "is_shared": Boolean,
    "timestamp": Long (milliseconds)
}
"""

import pika
import json
import logging
import time
from typing import Callable
from threading import Thread
from flask import Flask

logger = logging.getLogger(__name__)


class MetadataUpdateConsumer:
    """
    VectorDB 메타데이터 업데이트를 위한 RabbitMQ Consumer
    
    Spring Boot에서 3D 모델 정보가 수정될 때 전송되는 메시지를 수신하여
    VectorDB의 메타데이터를 업데이트합니다.
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
            heartbeat=600,
            blocked_connection_timeout=300
        )
        self.queue_name = config['METADATA_UPDATE_QUEUE']
        self.exchange = config['RABBITMQ_EXCHANGE']
        self.routing_key = config['METADATA_UPDATE_ROUTING_KEY']
        self.connection = None
        self.channel = None
    
    def connect(self):
        """RabbitMQ 연결 및 큐 설정"""
        try:
            self.connection = pika.BlockingConnection(self.parameters)
            self.channel = self.connection.channel()
            
            # Exchange 선언 (이미 있으면 기존 것 사용)
            self.channel.exchange_declare(
                exchange=self.exchange,
                exchange_type='topic',
                durable=True
            )
            
            # Queue 선언
            self.channel.queue_declare(
                queue=self.queue_name,
                durable=True
            )
            
            # Queue를 Exchange에 바인딩
            self.channel.queue_bind(
                exchange=self.exchange,
                queue=self.queue_name,
                routing_key=self.routing_key
            )
            
            # QoS 설정 (한 번에 1개의 메시지만 처리)
            self.channel.basic_qos(prefetch_count=1)
            
            logger.info(f"[SUCCESS] RabbitMQ 연결 성공 (메타데이터 업데이트 큐: {self.queue_name})")
            
        except Exception as e:
            logger.error(f"[FAILED] RabbitMQ 연결 실패: {str(e)}", exc_info=True)
            raise
    
    def start_consuming(self, callback: Callable):
        """
        메시지 수신 시작
        
        Args:
            callback: 메시지 수신 시 호출할 콜백 함수
        """
        try:
            logger.info(f"[*] 메타데이터 업데이트 요청 수신 대기 중: {self.queue_name}")
            self.channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=callback,
                auto_ack=False  # 수동 ACK
            )
            
            self.channel.start_consuming()
        except Exception as e:
            logger.error(f"[FAILED] 메시지 수신 실패: {str(e)}", exc_info=True)
    
    def close(self):
        """연결 종료"""
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
                logger.info("[SUCCESS] RabbitMQ 연결 종료 (메타데이터 업데이트)")
        except Exception as e:
            logger.error(f"연결 종료 중 오류: {str(e)}")


def process_metadata_update_message(ch, method, properties, body):
    """
    메타데이터 업데이트 메시지 처리 콜백 함수
    
    멱등성을 보장하여 같은 메시지가 여러 번 처리되어도 동일한 결과를 반환합니다.
    
    Args:
        ch: RabbitMQ 채널
        method: 메시지 메타데이터
        properties: 메시지 속성
        body: 메시지 본문 (JSON 바이트)
    
    메시지 형식:
    {
        "model3d_id": Long,
        "member_id": Long,
        "name": String,
        "description": String (nullable),
        "is_shared": Boolean,
        "timestamp": Long (milliseconds)
    }
    """
    start_time = time.time()
    
    try:
        # 1. 메시지 파싱
        message = json.loads(body)
        model3d_id = message.get('model3d_id')
        member_id = message.get('member_id')
        name = message.get('name')
        description = message.get('description')  # nullable
        is_shared = message.get('is_shared')
        timestamp = message.get('timestamp')
        
        logger.info(f"[RECEIVE] 메타데이터 업데이트 요청 수신")
        logger.info(f"    model3d_id={model3d_id}")
        logger.info(f"    member_id={member_id}")
        logger.info(f"    name={name}")
        logger.info(f"    description={description}")
        logger.info(f"    is_shared={is_shared}")
        logger.info(f"    timestamp={timestamp}")
        
        # 2. 필수 필드 검증
        if model3d_id is None:
            raise ValueError("model3d_id는 필수입니다")
        
        # 3. VectorDB 메타데이터 업데이트
        from app.routes.recommendation import get_vectorizer
        
        vectorizer = get_vectorizer()
        
        # 4. 기존 메타데이터 확인
        existing_meta = vectorizer.find_by_model3d_id(model3d_id)
        
        if existing_meta is None:
            logger.warning(f"[NOT_FOUND] VectorDB에 model3d_id={model3d_id} 데이터가 없습니다.")
            logger.info("    isVectorDbTrained=true인 모델만 업데이트 메시지가 전송되므로 이 경우는 드뭅니다.")
            # 메시지 ACK (데이터가 없어도 처리 완료로 표시)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
        
        # 5. 메타데이터 업데이트 수행
        success = vectorizer.update_metadata(
            model3d_id=model3d_id,
            name=name,
            description=description,
            is_shared=is_shared
        )
        
        if success:
            # 6. 변경사항을 디스크에 저장 (영구 저장)
            # 주의: recommendation.py와 동일한 경로 사용 (UPLOAD_FOLDER)
            from flask import current_app
            import os
            
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
            index_path = os.path.join(upload_folder, 'furniture_index.faiss')
            metadata_path = os.path.join(upload_folder, 'furniture_metadata.pkl')
            
            save_success = vectorizer.save_database(index_path, metadata_path)
            
            if save_success:
                logger.info(f"[SUCCESS] VectorDB 저장 완료: {metadata_path}")
            else:
                logger.warning(f"[WARN] VectorDB 저장 실패 (메모리에는 업데이트됨)")
            
            # 7. 메시지 ACK
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
            processing_time = time.time() - start_time
            logger.info(f"[COMPLETE] 메타데이터 업데이트 완료 (소요 시간: {processing_time:.2f}초)")
        else:
            logger.error(f"[FAILED] 메타데이터 업데이트 실패: model3d_id={model3d_id}")
            # 실패 시에도 ACK (재시도해도 동일한 결과일 가능성이 높음)
            ch.basic_ack(delivery_tag=method.delivery_tag)
    
    except json.JSONDecodeError as e:
        logger.error(f"[ERROR] JSON 파싱 오류: {str(e)}", exc_info=True)
        # 잘못된 형식의 메시지는 재큐하지 않음
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    
    except ValueError as e:
        logger.error(f"[ERROR] 검증 오류: {str(e)}", exc_info=True)
        # 검증 실패 메시지는 재큐하지 않음
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    
    except Exception as e:
        logger.error(f"[ERROR] 메타데이터 업데이트 중 예기치 않은 오류: {str(e)}", exc_info=True)
        # 예기치 않은 오류는 재시도를 위해 재큐
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def start_metadata_update_consumer_thread(app: Flask):
    """
    Flask 애플리케이션 컨텍스트에서 메타데이터 업데이트 Consumer를 실행
    
    Args:
        app: Flask 애플리케이션 인스턴스
    """
    def consumer_loop():
        """Consumer 루프"""
        with app.app_context():
            retry_count = 0
            max_retries = 5
            
            while retry_count < max_retries:
                try:
                    consumer = MetadataUpdateConsumer(app.config)
                    consumer.connect()
                    consumer.start_consuming(process_metadata_update_message)
                    
                except Exception as e:
                    logger.error(f"메타데이터 업데이트 Consumer 실행 중 오류: {str(e)}", exc_info=True)
                    retry_count += 1
                    
                    if retry_count < max_retries:
                        logger.info(f"재연결 시도 ({retry_count}/{max_retries})...")
                        time.sleep(5)  # 5초 대기 후 재연결
                    else:
                        logger.error("최대 재연결 시도 횟수 초과 (메타데이터 업데이트 Consumer)")
                        break
    
    # 별도 스레드에서 실행
    consumer_thread = Thread(
        target=consumer_loop,
        daemon=True,
        name='MetadataUpdateConsumer'
    )
    consumer_thread.start()
    logger.info("메타데이터 업데이트 Consumer 스레드 시작됨")
    
    return consumer_thread
