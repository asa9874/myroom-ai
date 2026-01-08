"""
RabbitMQ 테스트 스크립트

Flask AI 서버로 테스트 메시지를 전송하여 RabbitMQ 연동을 테스트합니다.
Spring Boot 없이 직접 메시지를 RabbitMQ로 전송할 수 있습니다.
"""

import pika
import json
import time
from datetime import datetime


def send_test_message(image_url, member_id):
    """
    테스트 메시지를 RabbitMQ로 전송
    
    Args:
        image_url: 테스트할 이미지 URL
        member_id: 테스트 사용자 ID
    """
    # RabbitMQ 연결 설정
    credentials = pika.PlainCredentials('guest', 'guest')
    parameters = pika.ConnectionParameters(
        host='localhost',
        port=5672,
        credentials=credentials
    )
    
    try:
        # 연결 생성
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        # Exchange와 Queue 선언 (없으면 생성)
        exchange_name = 'model3d.exchange'
        queue_name = 'model3d.upload.queue'
        routing_key = 'model3d.upload'
        
        channel.exchange_declare(
            exchange=exchange_name,
            exchange_type='topic',
            durable=True
        )
        
        channel.queue_declare(queue=queue_name, durable=True)
        
        channel.queue_bind(
            queue=queue_name,
            exchange=exchange_name,
            routing_key=routing_key
        )
        
        # 메시지 생성
        message = {
            'imageUrl': image_url,
            'memberId': member_id,
            'timestamp': int(time.time() * 1000)  # Unix timestamp (milliseconds)
        }
        
        # 메시지 전송
        channel.basic_publish(
            exchange=exchange_name,
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # 메시지 영속성
                content_type='application/json'
            )
        )
        
        print("=" * 60)
        print("✅ 메시지 전송 성공!")
        print("=" * 60)
        print(f"Exchange: {exchange_name}")
        print(f"Routing Key: {routing_key}")
        print(f"Queue: {queue_name}")
        print(f"\n메시지 내용:")
        print(json.dumps(message, indent=2, ensure_ascii=False))
        print("=" * 60)
        
        # 연결 종료
        connection.close()
        
        return True
        
    except pika.exceptions.AMQPConnectionError as e:
        print("❌ RabbitMQ 연결 실패!")
        print(f"오류: {e}")
        print("\n해결 방법:")
        print("1. RabbitMQ 서버가 실행 중인지 확인하세요.")
        print("2. Docker: docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management")
        return False
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return False


def send_multiple_test_messages(count=3):
    """
    여러 개의 테스트 메시지 전송
    
    Args:
        count: 전송할 메시지 개수
    """
    print(f"\n🚀 {count}개의 테스트 메시지를 전송합니다...\n")
    
    test_images = [
        "https://picsum.photos/800/600?random=1",
        "https://picsum.photos/800/600?random=2",
        "https://picsum.photos/800/600?random=3",
        "https://picsum.photos/800/600?random=4",
        "https://picsum.photos/800/600?random=5",
    ]
    
    success_count = 0
    
    for i in range(count):
        member_id = (i % 3) + 1  # 사용자 ID 1, 2, 3 순환
        image_url = test_images[i % len(test_images)]
        
        print(f"\n[{i+1}/{count}] 메시지 전송 중...")
        
        if send_test_message(image_url, member_id):
            success_count += 1
            time.sleep(1)  # 메시지 간 간격
        else:
            break
    
    print(f"\n📊 전송 완료: {success_count}/{count} 성공")


def check_queue_status():
    """
    Queue 상태 확인 (관리 API 사용)
    """
    try:
        import requests
        
        # RabbitMQ 관리 API
        url = "http://localhost:15672/api/queues/%2F/model3d.upload.queue"
        auth = ('guest', 'guest')
        
        response = requests.get(url, auth=auth, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print("\n📊 Queue 상태:")
            print(f"  - 이름: {data['name']}")
            print(f"  - 대기 중인 메시지: {data.get('messages_ready', 0)}")
            print(f"  - 처리 중인 메시지: {data.get('messages_unacknowledged', 0)}")
            print(f"  - 전체 메시지: {data.get('messages', 0)}")
            print(f"  - Consumer 수: {data.get('consumers', 0)}")
        else:
            print(f"⚠️  Queue 상태 확인 실패 (HTTP {response.status_code})")
            
    except ImportError:
        print("⚠️  requests 라이브러리가 필요합니다: pip install requests")
    except Exception as e:
        print(f"⚠️  Queue 상태 확인 중 오류: {e}")


if __name__ == '__main__':
    print("=" * 60)
    print("  RabbitMQ 테스트 스크립트")
    print("=" * 60)
    print("\n테스트 옵션을 선택하세요:")
    print("1. 단일 메시지 전송")
    print("2. 다중 메시지 전송 (3개)")
    print("3. 다중 메시지 전송 (5개)")
    print("4. Queue 상태 확인")
    print("0. 종료")
    
    choice = input("\n선택 (0-4): ").strip()
    
    if choice == '1':
        # 단일 메시지 테스트
        image_url = "https://picsum.photos/800/600"
        member_id = 1
        send_test_message(image_url, member_id)
        
    elif choice == '2':
        # 3개 메시지 전송
        send_multiple_test_messages(3)
        
    elif choice == '3':
        # 5개 메시지 전송
        send_multiple_test_messages(5)
        
    elif choice == '4':
        # Queue 상태 확인
        check_queue_status()
        
    elif choice == '0':
        print("종료합니다.")
        
    else:
        print("❌ 잘못된 선택입니다.")
    
    print("\n" + "=" * 60)
    print("테스트 완료!")
    print("=" * 60)
    print("\n📌 다음 단계:")
    print("1. Flask 서버 로그에서 메시지 처리 확인")
    print("2. API 호출: curl http://localhost:5000/api/v1/model3d/models")
    print("3. RabbitMQ 관리 콘솔: http://localhost:15672/")
    print("=" * 60)
