"""
추천 시스템용 RabbitMQ Consumer

Java 서버에서 전송된 추천 요청을 수신하고 처리합니다.
"""

import pika
import json
import logging
import time
from typing import Callable
from threading import Thread
from flask import Flask, current_app

logger = logging.getLogger(__name__)


class RecommendationConsumer:
    """
    RabbitMQ로부터 추천 요청을 수신하는 클래스
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
        self.request_queue = config['RECOMMAND_REQUEST_QUEUE']
        self.exchange = config['RECOMMAND_EXCHANGE']
        self.connection = None
        self.channel = None
    
    def connect(self):
        """RabbitMQ 연결 및 큐 설정"""
        try:
            self.connection = pika.BlockingConnection(self.parameters)
            self.channel = self.connection.channel()
            
            # Exchange 선언
            self.channel.exchange_declare(
                exchange=self.exchange,
                exchange_type='topic',
                durable=True
            )
            
            # Request Queue 선언
            self.channel.queue_declare(
                queue=self.request_queue,
                durable=True
            )
            
            # Queue를 Exchange에 바인딩
            self.channel.queue_bind(
                exchange=self.exchange,
                queue=self.request_queue,
                routing_key='recommand.request'
            )
            
            # QoS 설정 (한 번에 1개의 메시지만 처리)
            self.channel.basic_qos(prefetch_count=1)
            
            logger.info(f"[SUCCESS] RabbitMQ 연결 성공 (큐: {self.request_queue})")
            
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
            logger.info(f"[*] 추천 요청 수신 대기 중: {self.request_queue}")
            self.channel.basic_consume(
                queue=self.request_queue,
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
                logger.info("[SUCCESS] RabbitMQ 연결 종료")
        except Exception as e:
            logger.error(f"연결 종료 중 오류: {str(e)}")


def start_recommendation_consumer_thread(app: Flask):
    """
    Flask 애플리케이션 컨텍스트에서 추천 Consumer를 실행
    
    Args:
        app: Flask 애플리케이션 인스턴스
    """
    def consumer_loop():
        """Consumer 루프"""
        with app.app_context():
            try:
                from .recommendation_callback import process_recommendation_message
                
                consumer = RecommendationConsumer(app.config)
                consumer.connect()
                consumer.start_consuming(process_recommendation_message)
                
            except Exception as e:
                logger.error(f"추천 Consumer 실행 중 오류: {str(e)}", exc_info=True)
                # 재연결 로직
                retry_count = 0
                max_retries = 5
                while retry_count < max_retries:
                    try:
                        logger.info(f"재연결 시도 ({retry_count + 1}/{max_retries})...")
                        time.sleep(5)  # 5초 대기
                        consumer = RecommendationConsumer(app.config)
                        consumer.connect()
                        consumer.start_consuming(process_recommendation_message)
                    except Exception as retry_error:
                        logger.error(f"재연결 실패: {retry_error}")
                        retry_count += 1
                
                if retry_count >= max_retries:
                    logger.error("최대 재연결 시도 횟수 초과")
    
    # 별도 스레드에서 실행
    consumer_thread = Thread(
        target=consumer_loop,
        daemon=True,
        name='RecommendationConsumer'
    )
    consumer_thread.start()
    logger.info("추천 Consumer 스레드 시작됨")
