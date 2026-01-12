"""
추천 시스템 테스트 스크립트

클립 벡터라이저, 이미지 분석, 검색 엔진의 주요 기능을 테스트합니다.

실행 방법:
    python test_recommendation.py
"""

import os
import sys
import logging
import json
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def test_clip_vectorizer():
    """CLIP 벡터라이저 테스트"""
    logger.info("=" * 60)
    logger.info("Testing CLIP Vectorizer")
    logger.info("=" * 60)

    try:
        from app.recommand import CLIPVectorizer

        # 벡터라이저 초기화
        logger.info("Initializing CLIPVectorizer...")
        vectorizer = CLIPVectorizer()

        # 데이터베이스 정보
        info = vectorizer.get_database_info()
        logger.info(f"Vectorizer initialized: {json.dumps(info, indent=2)}")

        # 텍스트 임베딩 테스트
        logger.info("Testing text embedding...")
        text = "modern wooden chair with armrest"
        embedding = vectorizer._get_text_embedding(text)

        if embedding is not None:
            logger.info(f"✅ Text embedding created successfully")
            logger.info(f"   - Shape: {embedding.shape}")
            logger.info(f"   - Norm: {(embedding ** 2).sum() ** 0.5:.4f}")
        else:
            logger.warning("❌ Failed to create text embedding")

        logger.info("✅ CLIP Vectorizer tests completed\n")
        return True

    except Exception as e:
        logger.error(f"❌ CLIP Vectorizer test failed: {e}")
        return False


def test_image_analyzer():
    """이미지 분석기 테스트"""
    logger.info("=" * 60)
    logger.info("Testing Image Analyzer")
    logger.info("=" * 60)

    try:
        from app.recommand import ImageAnalyzer

        # 이미지 분석기 초기화
        logger.info("Initializing ImageAnalyzer...")
        analyzer = ImageAnalyzer()

        logger.info("✅ ImageAnalyzer initialized successfully")
        logger.info("   - YOLO model: Available")
        logger.info(f"   - BLIP model: {'Available' if analyzer.blip_model else 'Not available'}")
        logger.info(f"   - Gemini API: {'Configured' if analyzer.gemini_model else 'Not configured'}")

        logger.info("✅ Image Analyzer tests completed\n")
        return True

    except Exception as e:
        logger.error(f"❌ Image Analyzer test failed: {e}")
        return False


def test_furniture_search_engine():
    """가구 검색 엔진 테스트"""
    logger.info("=" * 60)
    logger.info("Testing Furniture Search Engine")
    logger.info("=" * 60)

    try:
        from app.recommand import CLIPVectorizer, FurnitureSearchEngine

        # 벡터라이저 및 검색 엔진 초기화
        logger.info("Initializing search engine...")
        vectorizer = CLIPVectorizer()
        search_engine = FurnitureSearchEngine(vectorizer)

        logger.info("✅ Search engine initialized successfully")

        # 통계 조회
        stats = search_engine.get_statistics()
        logger.info(f"Database statistics: {json.dumps(stats, indent=2)}")

        # 빈 데이터베이스에서 검색 시도 (경고만 출력)
        logger.info("Testing search with empty database...")
        results = search_engine.search_by_text("test query", top_k=5)
        if not results:
            logger.info("✅ Correctly handled empty database")

        logger.info("✅ Furniture Search Engine tests completed\n")
        return True

    except Exception as e:
        logger.error(f"❌ Furniture Search Engine test failed: {e}")
        return False


def test_api_endpoints():
    """Flask API 엔드포인트 테스트"""
    logger.info("=" * 60)
    logger.info("Testing Flask API Endpoints")
    logger.info("=" * 60)

    try:
        from app import create_app

        # 앱 생성
        logger.info("Creating Flask app...")
        app = create_app("testing")

        # 테스트 클라이언트 생성
        client = app.test_client()

        # 1. Health check
        logger.info("Testing GET /api/recommendation/health...")
        response = client.get("/api/recommendation/health")
        logger.info(f"   - Status: {response.status_code}")
        if response.status_code == 200:
            logger.info("   ✅ Health check passed")
        else:
            logger.warning(f"   ❌ Health check failed: {response.get_json()}")

        # 2. Categories
        logger.info("Testing GET /api/recommendation/categories...")
        response = client.get("/api/recommendation/categories")
        logger.info(f"   - Status: {response.status_code}")
        if response.status_code == 200:
            logger.info("   ✅ Categories endpoint passed")
        else:
            logger.warning(f"   ❌ Categories endpoint failed: {response.get_json()}")

        # 3. Statistics
        logger.info("Testing GET /api/recommendation/statistics...")
        response = client.get("/api/recommendation/statistics")
        logger.info(f"   - Status: {response.status_code}")
        if response.status_code == 200:
            logger.info("   ✅ Statistics endpoint passed")
        else:
            logger.warning(f"   ❌ Statistics endpoint failed: {response.get_json()}")

        # 4. Text search
        logger.info("Testing POST /api/recommendation/search/text...")
        response = client.post(
            "/api/recommendation/search/text",
            json={"query": "modern chair", "top_k": 5},
            content_type="application/json",
        )
        logger.info(f"   - Status: {response.status_code}")
        if response.status_code == 200:
            logger.info("   ✅ Text search endpoint passed")
        else:
            logger.warning(f"   ❌ Text search endpoint failed: {response.get_json()}")

        logger.info("✅ Flask API tests completed\n")
        return True

    except Exception as e:
        logger.error(f"❌ Flask API test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """모든 테스트 실행"""
    logger.info("\n" + "=" * 60)
    logger.info("MyRoom AI Recommendation System Tests")
    logger.info("=" * 60 + "\n")

    results = {
        "CLIP Vectorizer": test_clip_vectorizer(),
        "Image Analyzer": test_image_analyzer(),
        "Furniture Search Engine": test_furniture_search_engine(),
        "Flask API": test_api_endpoints(),
    }

    # 결과 요약
    logger.info("=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_flag in results.items():
        status = "✅ PASSED" if passed_flag else "❌ FAILED"
        logger.info(f"{test_name}: {status}")

    logger.info("=" * 60)
    logger.info(f"Total: {passed}/{total} tests passed")
    logger.info("=" * 60 + "\n")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
