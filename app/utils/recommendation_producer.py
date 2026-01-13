"""
추천 시스템용 RabbitMQ Producer

Flask AI 서버에서 추천 결과를 Java 백엔드 서버로 전송합니다.
"""

import pika
import json
import logging
import time
from typing import Dict, Any

logger = logging.getLogger(__name__)


class RecommendationProducer:
    """
    추천 결과를 RabbitMQ를 통해 Java 서버로 전송하는 클래스
    """
    
    def __init__(self, config):
        """
        Producer 초기화
        
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
        self.exchange = config['RECOMMAND_EXCHANGE']
        self.routing_key = config['RECOMMAND_RESPONSE_ROUTING_KEY']
    
    def send_recommendation_response(self, response_message: Dict[str, Any]) -> bool:
        """
        추천 결과 메시지 전송
        
        Args:
            response_message: 전송할 응답 메시지 딕셔너리
                {
                    "memberId": int,
                    "status": "success" | "failed",
                    "roomAnalysis": {...},
                    "recommendation": {...},
                    "timestamp": int,
                    "error": str (선택, 실패 시)
                }
            
        Returns:
            전송 성공 여부 (bool)
        """
        try:
            # RabbitMQ 연결
            connection = pika.BlockingConnection(self.parameters)
            channel = connection.channel()
            
            # Exchange 선언
            channel.exchange_declare(
                exchange=self.exchange,
                exchange_type='topic',
                durable=True
            )
            
            # 타임스탬프 추가 (없으면)
            if 'timestamp' not in response_message:
                response_message['timestamp'] = int(time.time() * 1000)
            
            # JSON으로 변환
            message_body = json.dumps(response_message, ensure_ascii=False)
            
            # 메시지 전송
            channel.basic_publish(
                exchange=self.exchange,
                routing_key=self.routing_key,
                body=message_body,
                properties=pika.BasicProperties(
                    content_type='application/json',
                    delivery_mode=2  # 메시지 지속성
                )
            )
            
            member_id = response_message.get('memberId')
            status = response_message.get('status')
            logger.info(f"[SUCCESS] 추천 결과 전송 성공: memberId={member_id}, status={status}")
            
            # 연결 종료
            connection.close()
            
            return True
            
        except Exception as e:
            logger.error(f"[FAILED] 추천 결과 전송 실패: {str(e)}", exc_info=True)
            return False
