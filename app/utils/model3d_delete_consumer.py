"""
VectorDB 삭제 Consumer

Spring Boot 서버에서 전송된 3D 모델 삭제 메시지를 
RabbitMQ를 통해 수신하고 VectorDB에서 삭제합니다.

메시지 형식:
{
    "model3d_ids": [1, 2, 3],  # 리스트 형태 (단건/다건 모두 지원)
    "member_id": Long,
    "timestamp": Long (milliseconds)
}
"""

import pika
import json
import logging
import time
from typing import Callable, List
from threading import Thread
from flask import Flask

logger = logging.getLogger(__name__)


class Model3DDeleteConsumer:
    """
    VectorDB 삭제를 위한 RabbitMQ Consumer
    
    Spring Boot에서 3D 모델이 삭제될 때 전송되는 메시지를 수신하여
    VectorDB에서 해당 데이터를 삭제합니다.
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
        self.queue_name = config['MODEL3D_DELETE_QUEUE']
        self.exchange = config['RABBITMQ_EXCHANGE']
        self.routing_key = config['MODEL3D_DELETE_ROUTING_KEY']
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
            
            logger.info(f"[SUCCESS] RabbitMQ 연결 성공 (삭제 큐: {self.queue_name})")
            
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
            logger.info(f"[*] 삭제 요청 수신 대기 중: {self.queue_name}")
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
                logger.info("[SUCCESS] RabbitMQ 연결 종료 (삭제)")
        except Exception as e:
            logger.error(f"연결 종료 중 오류: {str(e)}")


def delete_from_vectordb(vectorizer, model3d_ids: List[int]) -> dict:
    """
    VectorDB에서 여러 3D 모델 데이터를 삭제합니다.
    
    FAISS IndexFlatIP는 개별 벡터 삭제를 지원하지 않으므로,
    메타데이터에서 삭제 표시를 하고 인덱스를 재구성합니다.
    
    Args:
        vectorizer: CLIPVectorizer 인스턴스
        model3d_ids: 삭제할 3D 모델 ID 목록
        
    Returns:
        삭제 결과 딕셔너리 {deleted: [], not_found: []}
    """
    deleted = []
    not_found = []
    
    for model3d_id in model3d_ids:
        # 메타데이터에서 해당 ID 찾기
        found = False
        for i, meta in enumerate(vectorizer.metadata):
            if meta.get("model3d_id") == model3d_id:
                # 삭제 표시 (soft delete)
                vectorizer.metadata[i]["_deleted"] = True
                deleted.append(model3d_id)
                found = True
                logger.info(f"[DELETED] model3d_id={model3d_id} 삭제 표시됨")
                break
        
        if not found:
            not_found.append(model3d_id)
            logger.warning(f"[NOT_FOUND] model3d_id={model3d_id} VectorDB에서 찾을 수 없음")
    
    return {"deleted": deleted, "not_found": not_found}


def process_delete_message(ch, method, properties, body):
    """
    삭제 메시지 처리 콜백 함수
    
    멱등성을 보장하여 같은 메시지가 여러 번 처리되어도 동일한 결과를 반환합니다.
    
    Args:
        ch: RabbitMQ 채널
        method: 메시지 메타데이터
        properties: 메시지 속성
        body: 메시지 본문 (JSON 바이트)
    
    메시지 형식:
    {
        "model3d_ids": [1, 2, 3],
        "member_id": Long,
        "timestamp": Long (milliseconds)
    }
    """
    start_time = time.time()
    
    try:
        # 1. 메시지 파싱
        message = json.loads(body)
        model3d_ids = message.get('model3d_ids', [])
        member_id = message.get('member_id')
        timestamp = message.get('timestamp')
        
        logger.info(f"[RECEIVE] 삭제 요청 수신")
        logger.info(f"    model3d_ids={model3d_ids}")
        logger.info(f"    member_id={member_id}")
        logger.info(f"    timestamp={timestamp}")
        logger.info(f"    삭제 대상 개수: {len(model3d_ids)}개")
        
        # 2. 필수 필드 검증
        if not model3d_ids:
            logger.warning("[WARN] model3d_ids가 비어있습니다. 처리 건너뜀.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
        
        # 3. VectorDB에서 삭제 수행
        from app.routes.recommendation import get_vectorizer
        
        vectorizer = get_vectorizer()
        
        # 4. 삭제 실행
        result = delete_from_vectordb(vectorizer, model3d_ids)
        
        logger.info(f"[RESULT] 삭제 완료: {len(result['deleted'])}개 삭제, {len(result['not_found'])}개 미발견")
        
        if result['deleted']:
            # 5. 변경사항을 디스크에 저장 (영구 저장)
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
        
        # 6. 메시지 ACK
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
        processing_time = time.time() - start_time
        logger.info(f"[COMPLETE] 삭제 처리 완료 (소요 시간: {processing_time:.2f}초)")
    
    except json.JSONDecodeError as e:
        logger.error(f"[ERROR] JSON 파싱 오류: {str(e)}", exc_info=True)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    
    except ValueError as e:
        logger.error(f"[ERROR] 검증 오류: {str(e)}", exc_info=True)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    
    except Exception as e:
        logger.error(f"[ERROR] 삭제 처리 중 예기치 않은 오류: {str(e)}", exc_info=True)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def start_model3d_delete_consumer_thread(app: Flask):
    """
    Flask 애플리케이션 컨텍스트에서 삭제 Consumer를 실행
    
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
                    consumer = Model3DDeleteConsumer(app.config)
                    consumer.connect()
                    consumer.start_consuming(process_delete_message)
                    
                except Exception as e:
                    logger.error(f"삭제 Consumer 실행 중 오류: {str(e)}", exc_info=True)
                    retry_count += 1
                    
                    if retry_count < max_retries:
                        logger.info(f"재연결 시도 ({retry_count}/{max_retries})...")
                        time.sleep(5)  # 5초 대기 후 재연결
                    else:
                        logger.error("최대 재연결 시도 횟수 초과 (삭제 Consumer)")
                        break
    
    # 별도 스레드에서 실행
    consumer_thread = Thread(
        target=consumer_loop,
        daemon=True,
        name='Model3DDeleteConsumer'
    )
    consumer_thread.start()
    logger.info("VectorDB 삭제 Consumer 스레드 시작됨")
    
    return consumer_thread
