"""
추천 요청 메시지 처리 콜백

RabbitMQ로부터 받은 추천 요청을 처리하는 비즈니스 로직
"""

import json
import logging
import time
from datetime import datetime
from typing import Dict, Any

from .recommendation_producer import RecommendationProducer

logger = logging.getLogger(__name__)


def process_recommendation_message(ch, method, properties, body):
    """
    추천 요청 메시지 처리 콜백 함수
    
    Args:
        ch: RabbitMQ 채널
        method: 메시지 메타데이터
        properties: 메시지 속성
        body: 메시지 본문 (JSON 바이트)
    
    메시지 형식 (Java → Flask):
    {
        "memberId": int,
        "imageUrl": str,
        "category": str (선택, 기본값: "chair"),
        "topK": int (선택, 기본값: 5),
        "timestamp": long (밀리초)
    }
    """
    start_time = time.time()
    response_message = None
    
    try:
        # 1. 메시지 파싱
        message = json.loads(body)
        member_id = message.get('memberId')
        image_url = message.get('imageUrl')
        category = message.get('category', 'chair')
        top_k = message.get('topK', 5)
        request_timestamp = message.get('timestamp')
        
        logger.info(f"[RECEIVE] 추천 요청 수신")
        logger.info(f"    memberId={member_id}")
        logger.info(f"    imageUrl={image_url}")
        logger.info(f"    category={category}")
        logger.info(f"    topK={top_k}")
        
        # 2. 필수 필드 검증
        if not member_id or not image_url:
            raise ValueError("memberId와 imageUrl은 필수입니다")
        
        # 3. 이미지 분석 및 추천 수행
        from flask import current_app
        from app.routes.recommendation import get_image_analyzer, get_search_engine, get_vectorizer
        
        # Flask 애플리케이션 컨텍스트가 있으면 사용
        app_context = current_app._get_current_object()
        
        # 4. 벡터DB 확인
        vectorizer = get_vectorizer()
        if vectorizer.index.ntotal == 0:
            logger.warning("[WARN] 벡터DB가 비어있습니다. 초기화 필요")
            response_message = {
                "memberId": member_id,
                "status": "warning",
                "error": "벡터DB가 비어있습니다. /api/recommendation/init-database를 호출하세요",
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
        else:
            # 5. 이미지 분석
            logger.info("[이미지분석] 이미지 분석 중...")
            image_analyzer = get_image_analyzer()
            analysis_result = image_analyzer.analyze_image_comprehensive(
                image_url, 
                category
            )
            
            logger.info(f"[DONE] 이미지 분석 완료")
            logger.info(f"    감지된 가구: {analysis_result['room_analysis'].get('detected_furniture', [])}")
            
            # 6. 가구 추천
            logger.info(f"[SEARCH] 가구 추천 검색 중 (category={category}, topK={top_k})...")
            search_engine = get_search_engine()
            search_query = analysis_result['recommendation']['search_query']
            recommendations = search_engine.search_by_text(
                search_query,
                top_k,
                category
            )
            
            logger.info(f"[DONE] 가구 추천 완료: {len(recommendations)}개 결과")
            
            # 7. 응답 메시지 구성
            response_message = {
                "memberId": member_id,
                "status": "success",
                "roomAnalysis": {
                    "style": analysis_result['room_analysis'].get('style'),
                    "color": analysis_result['room_analysis'].get('color'),
                    "material": analysis_result['room_analysis'].get('material'),
                    "detectedFurniture": analysis_result['room_analysis'].get('detected_furniture', []),
                    "detectedCount": analysis_result['room_analysis'].get('detected_count', 0),
                    "detailedDetections": analysis_result['room_analysis'].get('detailed_detections', [])
                },
                "recommendation": {
                    "targetCategory": category,
                    "reasoning": analysis_result['recommendation'].get('reasoning'),
                    "searchQuery": search_query,
                    "results": recommendations,
                    "resultCount": len(recommendations)
                },
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
        
        # 8. 응답 발송
        if response_message:
            producer = RecommendationProducer(app_context.config)
            success = producer.send_recommendation_response(response_message)
            
            if success:
                # 9. 메시지 ACK
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
                processing_time = time.time() - start_time
                logger.info(f"[COMPLETE] 메시지 처리 완료 (소요 시간: {processing_time:.2f}초)")
            else:
                # 응답 발송 실패 시 재시도
                logger.warning(f"응답 발송 실패, 메시지 재큐...")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    except json.JSONDecodeError as e:
        logger.error(f"[ERROR] JSON 파싱 오류: {str(e)}", exc_info=True)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    
    except ValueError as e:
        logger.error(f"[ERROR] 검증 오류: {str(e)}", exc_info=True)
        
        # 실패 응답 발송
        try:
            message = json.loads(body)
            response_message = {
                "memberId": message.get('memberId'),
                "status": "failed",
                "error": str(e),
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
            
            from flask import current_app
            from app.routes.recommendation import get_image_analyzer
            app_context = current_app._get_current_object()
            
            producer = RecommendationProducer(app_context.config)
            producer.send_recommendation_response(response_message)
        except Exception as send_error:
            logger.error(f"실패 응답 발송 중 오류: {send_error}")
        
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    
    except Exception as e:
        logger.error(f"[ERROR] 메시지 처리 중 오류: {str(e)}", exc_info=True)
        
        # 실패 응답 발송
        try:
            message = json.loads(body)
            response_message = {
                "memberId": message.get('memberId'),
                "status": "failed",
                "error": str(e),
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
            
            from flask import current_app
            app_context = current_app._get_current_object()
            
            producer = RecommendationProducer(app_context.config)
            producer.send_recommendation_response(response_message)
        except Exception as send_error:
            logger.error(f"실패 응답 발송 중 오류: {send_error}")
        
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
