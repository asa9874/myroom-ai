"""
가구 검색 및 추천 엔진

CLIP 벡터라이저를 사용하여 이미지 및 텍스트 기반 가구 검색,
필터링 및 추천 기능을 제공합니다.

주요 기능:
- 텍스트 기반 가구 검색
- 이미지 기반 유사 가구 검색
- 카테고리별 필터링
- 검색 결과 랭킹 및 정렬
"""

import os
import logging
from typing import List, Dict, Optional, Tuple
from PIL import Image
import numpy as np

from .clip_vectorizer import CLIPVectorizer

logger = logging.getLogger(__name__)


class FurnitureSearchEngine:
    """CLIP 벡터 DB를 사용한 가구 검색 엔진"""

    def __init__(self, vectorizer: CLIPVectorizer):
        """
        검색 엔진 초기화

        Args:
            vectorizer: CLIPVectorizer 인스턴스
        """
        self.vectorizer = vectorizer
        logger.info("FurnitureSearchEngine initialized")

    def search_by_text(
        self, query: str, top_k: int = 5, furniture_type: Optional[str] = None
    ) -> List[Dict]:
        """
        텍스트 쿼리로 가구 검색

        Args:
            query: 검색 텍스트 (예: "modern wooden chair")
            top_k: 반환할 상위 결과 개수
            furniture_type: 특정 가구 타입으로 필터링 (선택사항)

        Returns:
            검색 결과 딕셔너리 리스트
        """
        if self.vectorizer.index.ntotal == 0:
            logger.warning("Database is empty")
            return []

        try:
            # 텍스트 임베딩 생성
            query_vector = self.vectorizer._get_text_embedding(query)

            if query_vector is None:
                logger.error(f"Failed to create embedding for query: {query}")
                return []

            # 벡터 DB 검색
            distances, indices = self.vectorizer.index.search(query_vector, min(top_k * 3, self.vectorizer.index.ntotal))

            results = []
            for i, idx in enumerate(indices[0]):
                if idx < 0 or idx >= len(self.vectorizer.metadata):
                    continue

                meta = self.vectorizer.metadata[idx]

                # 필터링 (furniture_type 지정 시)
                if furniture_type and meta.get("furniture_type") != furniture_type:
                    continue
                
                # FIX: is_shared=True인 항목만 반환
                if not meta.get("is_shared", False):
                    continue

                results.append(
                    {
                        "rank": len(results) + 1,
                        "score": float(distances[0][i]),
                        "model3d_id": meta.get("model3d_id"),  # model3d_id 추가
                        "furniture_type": meta.get("furniture_type"),
                        "image_path": meta.get("image_path"),
                        "filename": meta.get("filename"),
                        "metadata": {
                            k: v
                            for k, v in meta.items()
                            if k not in ["image_path", "furniture_type", "filename"]
                        },
                    }
                )

                if len(results) >= top_k:
                    break

            logger.info(f"Text search completed: {len(results)} results for '{query}'")
            return results

        except Exception as e:
            logger.error(f"Error in text search: {e}")
            return []

    def search_by_image(
        self, image_path: str, top_k: int = 5, furniture_type: Optional[str] = None
    ) -> List[Dict]:
        """
        이미지 쿼리로 유사한 가구 검색

        Args:
            image_path: 쿼리 이미지 파일 경로
            top_k: 반환할 상위 결과 개수
            furniture_type: 특정 가구 타입으로 필터링 (선택사항)

        Returns:
            검색 결과 딕셔너리 리스트
        """
        if self.vectorizer.index.ntotal == 0:
            logger.warning("Database is empty")
            return []

        try:
            if not os.path.exists(image_path):
                logger.error(f"Image not found: {image_path}")
                return []

            # 이미지 임베딩 생성
            image = Image.open(image_path).convert("RGB")
            query_vector = self.vectorizer._get_image_embedding(image)

            if query_vector is None:
                logger.error(f"Failed to create embedding for image: {image_path}")
                return []

            # 벡터 DB 검색
            distances, indices = self.vectorizer.index.search(query_vector, min(top_k * 3, self.vectorizer.index.ntotal))

            results = []
            for i, idx in enumerate(indices[0]):
                if idx < 0 or idx >= len(self.vectorizer.metadata):
                    continue

                meta = self.vectorizer.metadata[idx]

                # 삭제된 항목 제외
                if meta.get("_deleted", False):
                    continue

                # 필터링 (furniture_type 지정 시)
                if furniture_type and meta.get("furniture_type") != furniture_type:
                    continue
                
                # FIX: is_shared=True인 항목만 반환
                if not meta.get("is_shared", False):
                    continue

                results.append(
                    {
                        "rank": len(results) + 1,
                        "score": float(distances[0][i]),
                        "model3d_id": meta.get("model3d_id"),  # model3d_id 추가
                        "furniture_type": meta.get("furniture_type"),
                        "image_path": meta.get("image_path"),
                        "filename": meta.get("filename"),
                        "metadata": {
                            k: v
                            for k, v in meta.items()
                            if k not in ["image_path", "furniture_type", "filename"]
                        },
                    }
                )

                if len(results) >= top_k:
                    break

            logger.info(f"Image search completed: {len(results)} results for '{os.path.basename(image_path)}'")
            return results

        except Exception as e:
            logger.error(f"Error in image search: {e}")
            return []

    def get_categories(self) -> Dict[str, int]:
        """
        데이터베이스에 있는 모든 가구 카테고리 조회

        Returns:
            카테고리명: 개수 딕셔너리
        """
        categories = {}
        for meta in self.vectorizer.metadata:
            furniture_type = meta.get("furniture_type", "unknown")
            categories[furniture_type] = categories.get(furniture_type, 0) + 1

        return categories

    def get_category_details(self, furniture_type: str) -> Dict:
        """
        특정 카테고리의 상세 정보 조회

        Args:
            furniture_type: 가구 타입

        Returns:
            카테고리 상세 정보 딕셔너리
        """
        items = [meta for meta in self.vectorizer.metadata if meta.get("furniture_type") == furniture_type]

        return {
            "furniture_type": furniture_type,
            "count": len(items),
            "items": items,
        }

    def filter_by_category(self, furniture_type: str) -> List[Dict]:
        """
        특정 카테고리의 모든 가구 조회

        Args:
            furniture_type: 가구 타입

        Returns:
            해당 카테고리의 모든 가구 리스트
        """
        results = []
        for i, meta in enumerate(self.vectorizer.metadata):
            if meta.get("furniture_type") == furniture_type:
                results.append(
                    {
                        "index": i,
                        "furniture_type": furniture_type,
                        "image_path": meta.get("image_path"),
                        "filename": meta.get("filename"),
                        "metadata": {
                            k: v
                            for k, v in meta.items()
                            if k not in ["image_path", "furniture_type", "filename"]
                        },
                    }
                )

        logger.info(f"Found {len(results)} items in category '{furniture_type}'")
        return results

    def hybrid_search(
        self, text_query: str, image_path: Optional[str] = None, top_k: int = 5, furniture_type: Optional[str] = None
    ) -> List[Dict]:
        """
        텍스트 및 이미지 기반 하이브리드 검색

        Args:
            text_query: 텍스트 검색 쿼리
            image_path: 이미지 검색 경로 (선택사항)
            top_k: 반환할 결과 개수
            furniture_type: 가구 타입 필터

        Returns:
            통합 검색 결과 (점수로 정렬)
        """
        results_dict = {}

        # 텍스트 검색 결과
        text_results = self.search_by_text(text_query, top_k * 2, furniture_type)
        for result in text_results:
            img_path = result["image_path"]
            if img_path not in results_dict:
                results_dict[img_path] = {
                    **result,
                    "text_score": result["score"],
                    "image_score": 0.0,
                    "combined_score": result["score"],
                }
            else:
                results_dict[img_path]["text_score"] = result["score"]
                results_dict[img_path]["combined_score"] = (
                    results_dict[img_path]["text_score"] + results_dict[img_path].get("image_score", 0)
                ) / 2

        # 이미지 검색 결과 (이미지 제공 시)
        if image_path:
            image_results = self.search_by_image(image_path, top_k * 2, furniture_type)
            for result in image_results:
                img_path = result["image_path"]
                if img_path not in results_dict:
                    results_dict[img_path] = {
                        **result,
                        "text_score": 0.0,
                        "image_score": result["score"],
                        "combined_score": result["score"],
                    }
                else:
                    results_dict[img_path]["image_score"] = result["score"]
                    results_dict[img_path]["combined_score"] = (
                        results_dict[img_path].get("text_score", 0) + results_dict[img_path]["image_score"]
                    ) / 2

        # 점수로 정렬 및 상위 K개 반환
        sorted_results = sorted(
            results_dict.values(), key=lambda x: x["combined_score"], reverse=True
        )[:top_k]

        for i, result in enumerate(sorted_results, 1):
            result["rank"] = i

        logger.info(f"Hybrid search completed: {len(sorted_results)} results")
        return sorted_results

    def get_statistics(self) -> Dict:
        """
        데이터베이스의 통계 정보

        Returns:
            통계 정보 딕셔너리
        """
        categories = self.get_categories()

        return {
            "total_items": self.vectorizer.index.ntotal,
            "total_categories": len(categories),
            "categories": categories,
            "vector_dimension": self.vectorizer.dimension,
            "device": self.vectorizer.device,
        }
