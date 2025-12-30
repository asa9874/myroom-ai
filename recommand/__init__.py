"""
MyRoom-AI Recommendation Module

가구 추천 시스템을 위한 핵심 모듈
- 이미지 분석 및 벡터화
- 유사 검색 및 추천
- REST API 서버
"""

__version__ = "1.0.0"
__author__ = "MyRoom-AI"
__description__ = "Intelligent Furniture Recommendation System"

try:
    from .vectorizer import FurnitureVectorizer
    from .vectorize_images import ImageVectorizer
except ImportError as e:
    print(f"[Warning] 모듈 임포트 오류: {e}")

__all__ = [
    "FurnitureVectorizer",
    "ImageVectorizer"
]
