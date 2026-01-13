"""
Flask AI 서버와 Java 백엔드 서버의 RabbitMQ 추천 시스템 통합 예제

이 파일은 참고용 테스트 코드입니다.
실제 Java 서버에서는 Spring Boot의 RabbitListener를 사용하세요.
"""

import json
import pika
import time
from datetime import datetime
from typing import Dict, Any


class MockJavaRecommendationProducer:
    """
    Java 서버의 추천 요청을 시뮬레이션하는 Producer
    """
    
    def __init__(self, host='localhost', port=5672, username='guest', password='guest'):
        self.host = host
        self.port = port
        self.credentials = pika.PlainCredentials(username, password)
        self.parameters = pika.ConnectionParameters(
            host=self.host,
            port=self.port,
            credentials=self.credentials,
            heartbeat=600
        )
        self.exchange = 'recommand.exchange'
        self.request_queue = 'recommand.request.queue'
        self.routing_key = 'recommand.request'
    
    def connect(self):
        """RabbitMQ 연결"""
        self.connection = pika.BlockingConnection(self.parameters)
        self.channel = self.connection.channel()
        
        # Exchange 선언
        self.channel.exchange_declare(
            exchange=self.exchange,
            exchange_type='topic',
            durable=True
        )
        
        # Queue 선언
        self.channel.queue_declare(
            queue=self.request_queue,
            durable=True
        )
        
        # Binding
        self.channel.queue_bind(
            exchange=self.exchange,
            queue=self.request_queue,
            routing_key=self.routing_key
        )
    
    def send_recommendation_request(
        self,
        member_id: int,
        image_url: str,
        category: str = "chair",
        top_k: int = 5
    ) -> bool:
        """
        추천 요청 메시지 발송
        
        Args:
            member_id: 회원 ID
            image_url: 분석할 이미지 URL
            category: 추천 카테고리
            top_k: 반환할 결과 개수
        
        Returns:
            발송 성공 여부
        """
        try:
            message = {
                "memberId": member_id,
                "imageUrl": image_url,
                "category": category,
                "topK": top_k,
                "timestamp": int(time.time() * 1000)
            }
            
            message_body = json.dumps(message, ensure_ascii=False)
            
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=self.routing_key,
                body=message_body,
                properties=pika.BasicProperties(
                    content_type='application/json',
                    delivery_mode=2
                )
            )
            
            print(f"✅ 요청 메시지 발송 성공")
            print(f"   memberId={member_id}, category={category}, topK={top_k}")
            print(f"   imageUrl={image_url}")
            
            return True
        
        except Exception as e:
            print(f"❌ 요청 메시지 발송 실패: {e}")
            return False
    
    def close(self):
        """연결 종료"""
        if self.connection:
            self.connection.close()


class MockJavaRecommendationConsumer:
    """
    Flask AI 서버의 응답을 수신하는 Consumer
    """
    
    def __init__(self, host='localhost', port=5672, username='guest', password='guest'):
        self.host = host
        self.port = port
        self.credentials = pika.PlainCredentials(username, password)
        self.parameters = pika.ConnectionParameters(
            host=self.host,
            port=self.port,
            credentials=self.credentials,
            heartbeat=600
        )
        self.exchange = 'recommand.exchange'
        self.response_queue = 'recommand.response.queue'
        self.routing_key = 'recommand.response'
        self.responses = []  # 수신한 메시지 저장
    
    def connect(self):
        """RabbitMQ 연결"""
        self.connection = pika.BlockingConnection(self.parameters)
        self.channel = self.connection.channel()
        
        # Exchange 선언
        self.channel.exchange_declare(
            exchange=self.exchange,
            exchange_type='topic',
            durable=True
        )
        
        # Response Queue 선언 (임시)
        self.channel.queue_declare(
            queue=self.response_queue,
            durable=True
        )
        
        # Binding
        self.channel.queue_bind(
            exchange=self.exchange,
            queue=self.response_queue,
            routing_key=self.routing_key
        )
    
    def receive_recommendation_response(self, callback=None):
        """
        응답 메시지 수신
        
        Args:
            callback: 메시지 수신 시 호출할 콜백 함수
        """
        def default_callback(ch, method, properties, body):
            try:
                message = json.loads(body)
                self.responses.append(message)
                
                member_id = message.get('memberId')
                status = message.get('status')
                
                print(f"\n{'='*60}")
                print(f"✅ 응답 메시지 수신")
                print(f"   memberId={member_id}, status={status}")
                
                if status == "success":
                    room_analysis = message.get('roomAnalysis', {})
                    recommendation = message.get('recommendation', {})
                    
                    print(f"\n📍 방 분석 결과:")
                    print(f"   스타일: {room_analysis.get('style')}")
                    print(f"   색상: {room_analysis.get('color')}")
                    print(f"   재질: {room_analysis.get('material')}")
                    print(f"   감지된 가구: {room_analysis.get('detectedFurniture')}")
                    
                    print(f"\n🛋️  추천 결과:")
                    print(f"   카테고리: {recommendation.get('targetCategory')}")
                    print(f"   이유: {recommendation.get('reasoning')[:100]}...")
                    print(f"   검색 쿼리: {recommendation.get('searchQuery')}")
                    print(f"   추천 가구 ({recommendation.get('resultCount')}개):")
                    
                    for result in recommendation.get('results', [])[:3]:
                        print(f"     - {result['rank']}위: {result['filename']}")
                        print(f"       유사도: {result['score']:.4f}")
                else:
                    error = message.get('error')
                    print(f"   에러: {error}")
                
                print(f"{'='*60}\n")
                
                # 커스텀 콜백 호출
                if callback:
                    callback(message)
                
                # ACK
                ch.basic_ack(delivery_tag=method.delivery_tag)
            
            except Exception as e:
                print(f"❌ 메시지 처리 중 오류: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        callback_fn = callback or default_callback
        
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(
            queue=self.response_queue,
            on_message_callback=callback_fn,
            auto_ack=False
        )
        
        print(f"[*] 응답 메시지 수신 대기 중...")
        self.channel.start_consuming()
    
    def close(self):
        """연결 종료"""
        if self.connection:
            self.connection.close()


def test_recommendation_flow():
    """
    추천 시스템 전체 흐름 테스트
    
    테스트 시나리오:
    1. Flask 서버에 추천 요청 발송
    2. Flask 서버가 처리하여 응답 발송
    3. Java 서버가 응답 수신
    """
    
    print("\n" + "="*60)
    print("🧪 RabbitMQ 추천 시스템 테스트")
    print("="*60)
    
    # Producer 초기화 (Java 서버 시뮬레이션)
    print("\n[1단계] 요청 메시지 발송")
    print("-" * 60)
    
    producer = MockJavaRecommendationProducer()
    try:
        producer.connect()
        
        # 테스트 요청 발송
        producer.send_recommendation_request(
            member_id=1,
            image_url="https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=600",
            category="chair",
            top_k=5
        )
        
        producer.close()
        
        # 처리 시간 대기
        print("\n⏳ Flask 서버 처리 대기 중 (약 15-20초)...")
        time.sleep(5)
        
    except Exception as e:
        print(f"❌ 요청 발송 실패: {e}")
        return
    
    # Consumer 초기화 (Java 서버 시뮬레이션)
    print("\n[2단계] 응답 메시지 수신")
    print("-" * 60)
    
    consumer = MockJavaRecommendationConsumer()
    try:
        consumer.connect()
        
        # 타임아웃 설정 (30초)
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("응답 수신 타임아웃")
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(30)
        
        try:
            consumer.receive_recommendation_response()
        except TimeoutError:
            print("⏰ 응답 수신 타임아웃 (30초)")
        finally:
            signal.alarm(0)
        
        consumer.close()
    
    except Exception as e:
        print(f"❌ 응답 수신 실패: {e}")


def test_multiple_requests():
    """여러 개의 요청을 연속으로 발송하는 테스트"""
    
    print("\n" + "="*60)
    print("🧪 다중 요청 테스트")
    print("="*60)
    
    test_cases = [
        {
            "member_id": 1,
            "image_url": "https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=600",
            "category": "chair",
            "top_k": 5
        },
        {
            "member_id": 2,
            "image_url": "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=600",
            "category": "table",
            "top_k": 3
        },
        {
            "member_id": 3,
            "image_url": "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=600",
            "category": "bed",
            "top_k": 5
        }
    ]
    
    producer = MockJavaRecommendationProducer()
    
    try:
        producer.connect()
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n[요청 {i}]")
            producer.send_recommendation_request(
                member_id=test_case["member_id"],
                image_url=test_case["image_url"],
                category=test_case["category"],
                top_k=test_case["top_k"]
            )
            time.sleep(1)  # 요청 간격
        
        producer.close()
        
        print("\n✅ 모든 요청 발송 완료")
        print("⏳ Flask 서버가 처리 중입니다...")
        
    except Exception as e:
        print(f"❌ 요청 발송 실패: {e}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "multiple":
        test_multiple_requests()
    else:
        test_recommendation_flow()
