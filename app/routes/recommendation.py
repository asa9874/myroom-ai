"""
추천 시스템 관련 REST API 라우트

가구 검색, 이미지 분석, AI 기반 추천 등의 API 엔드포인트를 제공합니다.

엔드포인트:
- GET /api/recommendation/health - 서비스 상태 확인
- GET /api/recommendation/categories - 가구 카테고리 목록
- GET /api/recommendation/statistics - 데이터베이스 통계
- POST /api/recommendation/search/text - 텍스트 기반 검색
- POST /api/recommendation/search/image - 이미지 기반 검색
- POST /api/recommendation/search/hybrid - 하이브리드 검색
- POST /api/recommendation/analyze - 이미지 분석 및 AI 추천
"""

import os
import logging
from flask import request, jsonify, current_app
from flask_restx import Namespace, Resource, fields
from werkzeug.utils import secure_filename

from app.recommand import CLIPVectorizer, FurnitureSearchEngine, ImageAnalyzer

logger = logging.getLogger(__name__)

# API 네임스페이스
api = Namespace(
    "recommendation",
    description="가구 추천 및 검색 API",
    path="/recommendation",
)

# 전역 변수 (애플리케이션 컨텍스트에서 초기화)
_vectorizer = None
_search_engine = None
_image_analyzer = None
_db_loaded = False


def init_recommendation_system():
    """추천 시스템 초기화"""
    global _vectorizer, _search_engine, _image_analyzer, _db_loaded

    try:
        logger.info("Initializing recommendation system...")

        # CLIP 벡터라이저 초기화
        _vectorizer = CLIPVectorizer()

        # 애플리케이션 컨텍스트에서 UPLOAD_FOLDER 가져오기
        if current_app:
            upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
        else:
            # 컨텍스트 없을 때는 상대 경로 사용 후 절대 경로로 변환
            upload_folder = os.path.abspath("uploads")
        
        # 데이터베이스 로드 시도
        db_path = os.path.join(upload_folder, "furniture_index.faiss")
        db_meta_path = os.path.join(upload_folder, "furniture_metadata.pkl")

        # 절대 경로 변환
        db_path = os.path.abspath(db_path)
        db_meta_path = os.path.abspath(db_meta_path)

        # 디버깅: 경로 정보 로깅
        logger.info(f"Looking for database files:")
        logger.info(f"  Index path: {db_path}")
        logger.info(f"  Metadata path: {db_meta_path}")
        logger.info(f"  Index exists: {os.path.exists(db_path)}")
        logger.info(f"  Metadata exists: {os.path.exists(db_meta_path)}")

        if os.path.exists(db_path) and os.path.exists(db_meta_path):
            logger.info("Database files found. Attempting to load...")
            if _vectorizer.load_database(db_path, db_meta_path):
                logger.info(f"[SUCCESS] Database loaded successfully ({_vectorizer.index.ntotal} items)")
                _db_loaded = True
            else:
                logger.warning("[FAILED] Failed to load database, starting with empty index")
        else:
            logger.warning("[WARNING] Database files not found, starting with empty index")

        # 검색 엔진 초기화
        _search_engine = FurnitureSearchEngine(_vectorizer)

        # 이미지 분석기 초기화 (공식 모델 설정)
        _image_analyzer = ImageAnalyzer(
            primary_model='gemini-2.5-flash',
            fallback_models=['gemini-2.5-pro', 'gemini-3-flash']
        )

        logger.info("Recommendation system initialized successfully")

    except Exception as e:
        logger.error(f"Error initializing recommendation system: {e}", exc_info=True)
        raise


def get_vectorizer() -> CLIPVectorizer:
    """전역 벡터라이저 객체 반환"""
    global _vectorizer
    if _vectorizer is None:
        init_recommendation_system()
    return _vectorizer


def get_search_engine() -> FurnitureSearchEngine:
    """전역 검색 엔진 객체 반환"""
    global _search_engine
    if _search_engine is None:
        init_recommendation_system()
    return _search_engine


def get_image_analyzer() -> ImageAnalyzer:
    """전역 이미지 분석기 객체 반환"""
    global _image_analyzer
    if _image_analyzer is None:
        init_recommendation_system()
    return _image_analyzer


def allowed_file(filename: str) -> bool:
    """파일 확장자 확인"""
    allowed_extensions = current_app.config.get("ALLOWED_EXTENSIONS", {"jpg", "jpeg", "png", "gif"})
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


# ==================== 응답 모델 정의 ====================

search_result = api.model(
    "SearchResult",
    {
        "rank": fields.Integer(description="결과 순위"),
        "score": fields.Float(description="유사도 점수"),
        "furniture_type": fields.String(description="가구 타입"),
        "image_path": fields.String(description="이미지 경로"),
        "filename": fields.String(description="파일명"),
    },
)

room_analysis = api.model(
    "RoomAnalysis",
    {
        "style": fields.String(description="방의 스타일"),
        "color": fields.String(description="색상 구성"),
        "material": fields.String(description="재질"),
        "detected_furniture": fields.List(fields.String, description="감지된 가구"),
        "detected_count": fields.Integer(description="감지된 개수"),
    },
)

recommendation_result = api.model(
    "RecommendationResult",
    {
        "target_category": fields.String(description="목표 가구 카테고리"),
        "reasoning": fields.String(description="추천 이유"),
        "search_query": fields.String(description="검색 쿼리"),
        "results": fields.List(fields.Nested(search_result), description="검색 결과"),
    },
)

# ==================== 라우트 정의 ====================


@api.route("/metadata")
class MetadataList(Resource):
    """VectorDB에 저장된 모든 메타데이터 조회"""

    def get(self):
        """
        VectorDB에 저장된 모든 메타데이터 리스트 조회

        쿼리 파라미터:
        - skip: 시작 인덱스 (기본값: 0)
        - limit: 조회할 개수 (기본값: 100)
        - furniture_type: 특정 가구 타입 필터링 (선택사항)

        Returns:
            JSON: 메타데이터 리스트 및 통계
        """
        try:
            # 쿼리 파라미터
            skip = int(request.args.get("skip", 0))
            limit = int(request.args.get("limit", 100))
            furniture_type = request.args.get("furniture_type", None)

            # 범위 검증
            skip = max(0, skip)
            limit = max(1, min(limit, 1000))  # 최대 1000개까지만

            vectorizer = get_vectorizer()
            
            # 🔥 FIX: 매번 조회 시 디스크에서 최신 데이터를 다시 로드
            if current_app:
                upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
            else:
                upload_folder = os.path.abspath("uploads")
            
            db_path = os.path.join(upload_folder, "furniture_index.faiss")
            db_meta_path = os.path.join(upload_folder, "furniture_metadata.pkl")
            
            # 파일이 존재하면 다시 로드 (항상 최신 상태 유지)
            if os.path.exists(db_path) and os.path.exists(db_meta_path):
                vectorizer.load_database(db_path, db_meta_path)

            if vectorizer.index.ntotal == 0:
                return {
                    "status": "success",
                    "total_count": 0,
                    "filtered_count": 0,
                    "metadata_list": [],
                    "pagination": {
                        "skip": skip,
                        "limit": limit,
                        "total_pages": 0,
                        "current_page": 0,
                    },
                }, 200

            # 필터링 (furniture_type 지정 시)
            filtered_metadata = vectorizer.metadata

            if furniture_type:
                filtered_metadata = [
                    m for m in vectorizer.metadata
                    if m.get("furniture_type") == furniture_type
                ]

            total_count = len(vectorizer.metadata)
            filtered_count = len(filtered_metadata)
            
            # 페이지네이션
            start_idx = skip
            end_idx = skip + limit
            paginated_data = filtered_metadata[start_idx:end_idx]

            # 응답 구성
            metadata_list = []
            for idx, meta in enumerate(paginated_data):
                metadata_list.append({
                    "index": start_idx + idx,
                    "furniture_type": meta.get("furniture_type"),
                    "image_path": meta.get("image_path"),
                    "filename": meta.get("filename"),
                    "metadata": {
                        k: v for k, v in meta.items()
                        if k not in ["image_path", "furniture_type", "filename"]
                    }
                })

            total_pages = (filtered_count + limit - 1) // limit
            current_page = (skip // limit) + 1 if filtered_count > 0 else 0

            logger.info(f"Metadata list retrieved: total={total_count}, filtered={filtered_count}, returned={len(metadata_list)}")

            return {
                "status": "success",
                "total_count": total_count,
                "filtered_count": filtered_count,
                "metadata_list": metadata_list,
                "pagination": {
                    "skip": skip,
                    "limit": limit,
                    "total_pages": total_pages,
                    "current_page": current_page,
                },
                "filters": {
                    "furniture_type": furniture_type,
                },
            }, 200

        except ValueError as e:
            logger.error(f"Invalid parameter: {e}")
            return {
                "status": "error",
                "message": f"잘못된 파라미터: {str(e)}",
            }, 400
        except Exception as e:
            logger.error(f"Error retrieving metadata: {e}")
            return {"status": "error", "message": str(e)}, 500

    def delete(self):
        """
        VectorDB 메타데이터 초기화 (전체 삭제)

        Returns:
            JSON: 초기화 결과
        """
        try:
            vectorizer = get_vectorizer()

            if vectorizer.index.ntotal == 0:
                return {
                    "status": "warning",
                    "message": "VectorDB가 이미 비어있습니다",
                }, 200

            # 메타데이터 초기화
            old_count = vectorizer.index.ntotal
            vectorizer.metadata = []
            vectorizer.index.reset()

            logger.warning(f"VectorDB cleared: {old_count} items removed")

            return {
                "status": "success",
                "message": "VectorDB 초기화 완료",
                "cleared_count": old_count,
            }, 200

        except Exception as e:
            logger.error(f"Error clearing metadata: {e}")
            return {"status": "error", "message": str(e)}, 500


@api.route("/metadata/<int:index>")
class MetadataDetail(Resource):
    """특정 메타데이터 상세 조회"""

    def get(self, index: int):
        """
        특정 인덱스의 메타데이터 상세 조회

        Args:
            index: 메타데이터 인덱스

        Returns:
            JSON: 메타데이터 상세 정보
        """
        try:
            vectorizer = get_vectorizer()
            
            # 🔥 FIX: 매번 조회 시 디스크에서 최신 데이터를 다시 로드
            if current_app:
                upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
            else:
                upload_folder = os.path.abspath("uploads")
            
            db_path = os.path.join(upload_folder, "furniture_index.faiss")
            db_meta_path = os.path.join(upload_folder, "furniture_metadata.pkl")
            
            # 파일이 존재하면 다시 로드 (항상 최신 상태 유지)
            if os.path.exists(db_path) and os.path.exists(db_meta_path):
                vectorizer.load_database(db_path, db_meta_path)

            if index < 0 or index >= len(vectorizer.metadata):
                return {
                    "status": "error",
                    "message": f"유효하지 않은 인덱스: {index} (범위: 0-{len(vectorizer.metadata)-1})",
                }, 404

            meta = vectorizer.metadata[index]

            return {
                "status": "success",
                "index": index,
                "furniture_type": meta.get("furniture_type"),
                "image_path": meta.get("image_path"),
                "filename": meta.get("filename"),
                "metadata": {
                    k: v for k, v in meta.items()
                    if k not in ["image_path", "furniture_type", "filename"]
                },
            }, 200

        except Exception as e:
            logger.error(f"Error retrieving metadata detail: {e}")
            return {"status": "error", "message": str(e)}, 500

    def delete(self, index: int):
        """
        특정 인덱스의 메타데이터 삭제

        Args:
            index: 메타데이터 인덱스

        Returns:
            JSON: 삭제 결과
        """
        try:
            vectorizer = get_vectorizer()

            if index < 0 or index >= len(vectorizer.metadata):
                return {
                    "status": "error",
                    "message": f"유효하지 않은 인덱스: {index}",
                }, 404

            # 메타데이터 삭제 (주의: FAISS 인덱스는 삭제할 수 없으므로 메타만 삭제)
            deleted_meta = vectorizer.metadata.pop(index)

            logger.warning(f"Metadata at index {index} deleted: {deleted_meta.get('filename')}")

            return {
                "status": "success",
                "message": f"인덱스 {index}의 메타데이터 삭제 완료",
                "deleted_item": {
                    "filename": deleted_meta.get("filename"),
                    "furniture_type": deleted_meta.get("furniture_type"),
                },
            }, 200

        except Exception as e:
            logger.error(f"Error deleting metadata: {e}")
            return {"status": "error", "message": str(e)}, 500


@api.route("/vectordb/reset")
class VectorDBReset(Resource):
    """VectorDB 초기화 (완전 재설정)"""

    def post(self):
        """
        VectorDB를 완전히 초기화합니다.
        
        기존 FAISS 인덱스 파일과 메타데이터 파일을 삭제하고
        새로운 빈 VectorDB를 생성합니다.

        Returns:
            JSON: 초기화 결과
        """
        try:
            upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
            os.makedirs(upload_folder, exist_ok=True)

            db_path = os.path.join(upload_folder, "furniture_index.faiss")
            db_meta_path = os.path.join(upload_folder, "furniture_metadata.pkl")

            db_path = os.path.abspath(db_path)
            db_meta_path = os.path.abspath(db_meta_path)

            # 기존 파일 삭제
            deleted_files = []

            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                    deleted_files.append(db_path)
                    logger.warning(f"Deleted FAISS index file: {db_path}")
                except Exception as e:
                    logger.error(f"Failed to delete FAISS index: {e}")
                    return {
                        "status": "error",
                        "message": f"FAISS 인덱스 파일 삭제 실패: {str(e)}",
                    }, 500

            if os.path.exists(db_meta_path):
                try:
                    os.remove(db_meta_path)
                    deleted_files.append(db_meta_path)
                    logger.warning(f"Deleted metadata file: {db_meta_path}")
                except Exception as e:
                    logger.error(f"Failed to delete metadata: {e}")
                    return {
                        "status": "error",
                        "message": f"메타데이터 파일 삭제 실패: {str(e)}",
                    }, 500

            # 새로운 빈 VectorDB 생성
            try:
                vectorizer = CLIPVectorizer()
                
                # 빈 상태로 저장
                vectorizer.save_database(db_path, db_meta_path)
                
                logger.info(f"New empty VectorDB created at {db_path}")
                
                return {
                    "status": "success",
                    "message": "VectorDB 완전 초기화 완료",
                    "deleted_files": deleted_files,
                    "new_vectordb": {
                        "index_path": db_path,
                        "metadata_path": db_meta_path,
                        "total_items": 0,
                    },
                }, 200

            except Exception as e:
                logger.error(f"Failed to create new VectorDB: {e}")
                return {
                    "status": "error",
                    "message": f"새로운 VectorDB 생성 실패: {str(e)}",
                }, 500

        except Exception as e:
            logger.error(f"Error resetting VectorDB: {e}")
            return {"status": "error", "message": str(e)}, 500


@api.route("/vectordb/status")
class VectorDBStatus(Resource):
    """VectorDB 상태 조회"""

    def get(self):
        """
        VectorDB의 현재 상태 조회
        (파일 존재 여부, 크기, 아이템 수 등)

        Returns:
            JSON: VectorDB 상태 정보
        """
        try:
            upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
            db_path = os.path.join(upload_folder, "furniture_index.faiss")
            db_meta_path = os.path.join(upload_folder, "furniture_metadata.pkl")

            db_path = os.path.abspath(db_path)
            db_meta_path = os.path.abspath(db_meta_path)

            vectorizer = get_vectorizer()
            
            # 🔥 FIX: 매번 조회 시 디스크에서 최신 데이터를 다시 로드
            if os.path.exists(db_path) and os.path.exists(db_meta_path):
                vectorizer.load_database(db_path, db_meta_path)

            index_exists = os.path.exists(db_path)
            metadata_exists = os.path.exists(db_meta_path)

            index_size = 0
            metadata_size = 0

            if index_exists:
                index_size = os.path.getsize(db_path)

            if metadata_exists:
                metadata_size = os.path.getsize(db_meta_path)

            # 가구 타입별 통계
            furniture_stats = {}
            for meta in vectorizer.metadata:
                ftype = meta.get("furniture_type", "unknown")
                furniture_stats[ftype] = furniture_stats.get(ftype, 0) + 1

            logger.info(f"VectorDB status: items={vectorizer.index.ntotal}, size={index_size + metadata_size} bytes")

            return {
                "status": "success",
                "vectordb": {
                    "total_items": vectorizer.index.ntotal,
                    "index_file": {
                        "path": db_path,
                        "exists": index_exists,
                        "size_bytes": index_size,
                        "size_mb": round(index_size / (1024 * 1024), 2),
                    },
                    "metadata_file": {
                        "path": db_meta_path,
                        "exists": metadata_exists,
                        "size_bytes": metadata_size,
                        "size_mb": round(metadata_size / (1024 * 1024), 2),
                    },
                    "total_size_mb": round((index_size + metadata_size) / (1024 * 1024), 2),
                    "furniture_types": furniture_stats,
                    "is_empty": vectorizer.index.ntotal == 0,
                },
            }, 200

        except Exception as e:
            logger.error(f"Error checking VectorDB status: {e}")
            return {"status": "error", "message": str(e)}, 500


        """
        VectorDB 메타데이터 통계

        Returns:
            JSON: 통계 정보
        """
        try:
            vectorizer = get_vectorizer()

            total_count = len(vectorizer.metadata)

            if total_count == 0:
                return {
                    "status": "success",
                    "total_count": 0,
                    "furniture_types": {},
                    "unique_files": 0,
                }, 200

            # 가구 타입별 통계
            furniture_stats = {}
            unique_files = set()

            for meta in vectorizer.metadata:
                ftype = meta.get("furniture_type", "unknown")
                furniture_stats[ftype] = furniture_stats.get(ftype, 0) + 1

                filename = meta.get("filename")
                if filename:
                    unique_files.add(filename)

            logger.info(f"Metadata statistics: total={total_count}, types={len(furniture_stats)}")

            return {
                "status": "success",
                "total_count": total_count,
                "furniture_types": furniture_stats,
                "unique_files": len(unique_files),
                "type_distribution": [
                    {
                        "type": ftype,
                        "count": count,
                        "percentage": round((count / total_count) * 100, 2),
                    }
                    for ftype, count in sorted(furniture_stats.items(), key=lambda x: x[1], reverse=True)
                ],
            }, 200

        except Exception as e:
            logger.error(f"Error retrieving statistics: {e}")
            return {"status": "error", "message": str(e)}, 500



class HealthCheck(Resource):
    """서비스 상태 확인 (관리자용 - 실시간 조회)"""

    def get(self):
        """
        추천 시스템 상태 확인 (매번 fresh하게 vectorDB에서 읽음)
        
        이 엔드포인트는 관리자용이므로 캐싱하지 않습니다.

        Returns:
            JSON: 서비스 상태 및 데이터베이스 정보
        """
        try:
            # 매번 fresh하게 vectorizer 생성 (캐싱 없음)
            vectorizer = CLIPVectorizer()
            
            # 애플리케이션 컨텍스트에서 UPLOAD_FOLDER 가져오기
            if current_app:
                upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
            else:
                upload_folder = os.path.abspath("uploads")
            
            # 데이터베이스 로드
            db_path = os.path.join(upload_folder, "furniture_index.faiss")
            db_meta_path = os.path.join(upload_folder, "furniture_metadata.pkl")
            
            db_path = os.path.abspath(db_path)
            db_meta_path = os.path.abspath(db_meta_path)
            
            logger.info(f"[HEALTH] Fresh vectorDB load - Index: {db_path}")
            
            # 데이터베이스 파일 존재 확인 및 로드
            db_loaded = False
            if os.path.exists(db_path) and os.path.exists(db_meta_path):
                if vectorizer.load_database(db_path, db_meta_path):
                    db_loaded = True
                    logger.info(f"[HEALTH] Database loaded: {vectorizer.index.ntotal} items")
            
            db_info = vectorizer.get_database_info()

            return {
                "status": "ok",
                "message": "Recommendation service is running",
                "database": db_info,
                "db_loaded": db_loaded,
                "timestamp": __import__("datetime").datetime.now().isoformat(),
            }, 200

        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}, 500


@api.route("/categories")
class Categories(Resource):
    """가구 카테고리 관리 (관리자용 - 실시간 조회)"""

    def get(self):
        """
        데이터베이스의 모든 가구 카테고리 조회 (매번 fresh하게 vectorDB에서 읽음)
        
        이 엔드포인트는 관리자용이므로 캐싱하지 않고 항상 현재 상태를 반환합니다.

        Returns:
            JSON: 카테고리 목록 및 개수
        """
        try:
            # 매번 fresh하게 vectorizer와 search_engine 생성 (캐싱 없음)
            vectorizer = CLIPVectorizer()
            
            # 애플리케이션 컨텍스트에서 UPLOAD_FOLDER 가져오기
            if current_app:
                upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
            else:
                upload_folder = os.path.abspath("uploads")
            
            # 데이터베이스 로드
            db_path = os.path.join(upload_folder, "furniture_index.faiss")
            db_meta_path = os.path.join(upload_folder, "furniture_metadata.pkl")
            
            db_path = os.path.abspath(db_path)
            db_meta_path = os.path.abspath(db_meta_path)
            
            logger.info(f"[CATEGORIES] Fresh vectorDB load - Index: {db_path}")
            
            # 데이터베이스 파일 존재 확인 및 로드
            if os.path.exists(db_path) and os.path.exists(db_meta_path):
                if not vectorizer.load_database(db_path, db_meta_path):
                    logger.warning("[CATEGORIES] Failed to load database")
                    return {
                        "status": "success",
                        "categories": {},
                        "total_categories": 0,
                        "message": "데이터베이스 파일 로드 실패"
                    }, 200
            else:
                logger.info(f"[CATEGORIES] Database files not found")
                return {
                    "status": "success",
                    "categories": {},
                    "total_categories": 0,
                    "message": "저장된 데이터가 없습니다"
                }, 200
            
            # 검색 엔진으로 카테고리 조회
            search_engine = FurnitureSearchEngine(vectorizer)
            categories = search_engine.get_categories()

            return {
                "status": "success",
                "categories": categories,
                "total_categories": len(categories),
            }, 200

        except Exception as e:
            logger.error(f"Error fetching categories: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}, 500


@api.route("/statistics")
class Statistics(Resource):
    """데이터베이스 통계 (관리자용 - 실시간 조회)"""

    def get(self):
        """
        데이터베이스의 통계 정보 조회 (매번 fresh하게 vectorDB에서 읽음)
        
        이 엔드포인트는 관리자용이므로 캐싱하지 않고 항상 현재 상태를 반환합니다.

        Returns:
            JSON: 통계 정보
        """
        try:
            # 매번 fresh하게 vectorizer와 search_engine 생성 (캐싱 없음)
            vectorizer = CLIPVectorizer()
            
            # 애플리케이션 컨텍스트에서 UPLOAD_FOLDER 가져오기
            if current_app:
                upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
            else:
                upload_folder = os.path.abspath("uploads")
            
            # 데이터베이스 로드
            db_path = os.path.join(upload_folder, "furniture_index.faiss")
            db_meta_path = os.path.join(upload_folder, "furniture_metadata.pkl")
            
            db_path = os.path.abspath(db_path)
            db_meta_path = os.path.abspath(db_meta_path)
            
            logger.info(f"[STATISTICS] Fresh vectorDB load - Index: {db_path}, Metadata: {db_meta_path}")
            
            # 데이터베이스 파일 존재 확인
            if os.path.exists(db_path) and os.path.exists(db_meta_path):
                if vectorizer.load_database(db_path, db_meta_path):
                    logger.info(f"[STATISTICS] Database loaded: {vectorizer.index.ntotal} items")
                else:
                    logger.warning("[STATISTICS] Failed to load database")
                    return {"status": "success", "statistics": {
                        "total_items": 0,
                        "total_categories": 0,
                        "categories": {},
                        "vector_dimension": vectorizer.dimension,
                        "device": vectorizer.device,
                        "message": "데이터베이스 파일 로드 실패"
                    }}, 200
            else:
                logger.info(f"[STATISTICS] Database files not found")
                return {"status": "success", "statistics": {
                    "total_items": 0,
                    "total_categories": 0,
                    "categories": {},
                    "vector_dimension": vectorizer.dimension,
                    "device": vectorizer.device,
                    "message": "저장된 데이터가 없습니다"
                }}, 200
            
            # 검색 엔진으로 통계 조회
            search_engine = FurnitureSearchEngine(vectorizer)
            stats = search_engine.get_statistics()

            return {"status": "success", "statistics": stats}, 200

        except Exception as e:
            logger.error(f"Error fetching statistics: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}, 500


@api.route("/search/text")
class TextSearch(Resource):
    """텍스트 기반 가구 검색"""

    def post(self):
        """
        텍스트 쿼리로 가구 검색

        요청 본문:
        {
            "query": "modern wooden chair",
            "top_k": 5,
            "furniture_type": "chair" (선택사항)
        }

        Returns:
            JSON: 검색 결과
        """
        try:
            data = request.get_json()

            if not data or "query" not in data:
                return {"status": "error", "message": "검색 쿼리가 없습니다"}, 400

            query = data["query"].strip()
            if not query:
                return {"status": "error", "message": "검색 쿼리가 비어있습니다"}, 400

            top_k = data.get("top_k", 5)
            furniture_type = data.get("furniture_type")

            # 벡터라이저 데이터베이스 확인
            vectorizer = get_vectorizer()
            if vectorizer.index.ntotal == 0:
                return {
                    "status": "warning",
                    "message": "데이터베이스가 비어있습니다",
                    "results": [],
                }, 200

            # 검색 실행
            search_engine = get_search_engine()
            results = search_engine.search_by_text(query, top_k, furniture_type)

            return {
                "status": "success",
                "query": query,
                "results": results,
                "count": len(results),
            }, 200

        except Exception as e:
            logger.error(f"Error in text search: {e}")
            return {"status": "error", "message": str(e)}, 500


@api.route("/search/image")
class ImageSearch(Resource):
    """이미지 기반 가구 검색"""

    def post(self):
        """
        이미지 쿼리로 유사한 가구 검색

        요청 형식: multipart/form-data
        - file: 이미지 파일
        - top_k: 반환할 결과 개수 (선택사항, 기본값 5)
        - furniture_type: 가구 타입 필터 (선택사항)

        Returns:
            JSON: 검색 결과
        """
        try:
            if "file" not in request.files:
                return {"status": "error", "message": "이미지 파일이 없습니다"}, 400

            file = request.files["file"]

            if file.filename == "":
                return {"status": "error", "message": "파일이 선택되지 않았습니다"}, 400

            if not allowed_file(file.filename):
                return {
                    "status": "error",
                    "message": "지원하지 않는 파일 형식입니다",
                }, 400

            # 임시 파일로 저장
            filename = secure_filename(file.filename)
            upload_dir = current_app.config.get("UPLOAD_FOLDER", "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            filepath = os.path.join(upload_dir, f"temp_{filename}")

            file.save(filepath)

            try:
                top_k = request.args.get("top_k", 5, type=int)
                furniture_type = request.args.get("furniture_type", None)

                # 벡터라이저 데이터베이스 확인
                vectorizer = get_vectorizer()
                if vectorizer.index.ntotal == 0:
                    return {
                        "status": "warning",
                        "message": "데이터베이스가 비어있습니다",
                        "results": [],
                    }, 200

                # 검색 실행
                search_engine = get_search_engine()
                results = search_engine.search_by_image(filepath, top_k, furniture_type)

                return {
                    "status": "success",
                    "results": results,
                    "count": len(results),
                }, 200

            finally:
                # 임시 파일 삭제
                if os.path.exists(filepath):
                    os.remove(filepath)

        except Exception as e:
            logger.error(f"Error in image search: {e}")
            return {"status": "error", "message": str(e)}, 500


@api.route("/analyze")
class AnalyzeRoom(Resource):
    """이미지 분석 및 AI 기반 추천
    
    NOTE: 이 엔드포인트는 HTTP POST와 RabbitMQ 메시지 모두로 지원됩니다.
    - HTTP POST: 직접 이미지를 업로드하여 즉시 결과 반환
    - RabbitMQ: Java 서버에서 메시지 기반으로 요청하면 비동기 처리
    """

    def post(self):
        """
        방의 이미지를 분석하고 AI 기반 가구 추천

        요청 형식: multipart/form-data
        - file: 방의 이미지 파일
        - category: 추천할 가구 카테고리 (선택사항, 기본값 'chair')
        - top_k: 반환할 추천 결과 개수 (선택사항, 기본값 5)

        Returns:
            JSON: 방 분석 결과 및 추천
        
        예제:
            curl -X POST \
              -F "file=@room.jpg" \
              -F "category=chair" \
              -F "top_k=5" \
              http://localhost:5000/api/recommendation/analyze
        
        RabbitMQ 메시지 형식 (Java → Flask):
        {
            "memberId": 1,
            "imageUrl": "https://example.com/room.jpg",
            "category": "chair",
            "topK": 5,
            "timestamp": 1705088400000
        }
        """
        try:
            if "file" not in request.files:
                return {"status": "error", "message": "이미지 파일이 없습니다"}, 400

            file = request.files["file"]

            if file.filename == "":
                return {"status": "error", "message": "파일이 선택되지 않았습니다"}, 400

            if not allowed_file(file.filename):
                return {
                    "status": "error",
                    "message": "지원하지 않는 파일 형식입니다",
                }, 400

            # 임시 파일로 저장
            filename = secure_filename(file.filename)
            upload_dir = current_app.config.get("UPLOAD_FOLDER", "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            filepath = os.path.join(upload_dir, f"room_{filename}")

            file.save(filepath)

            try:
                target_category = request.args.get("category", "chair")
                top_k = request.args.get("top_k", 5, type=int)

                # 벡터라이저 데이터베이스 확인
                vectorizer = get_vectorizer()
                if vectorizer.index.ntotal == 0:
                    return {
                        "status": "warning",
                        "message": "데이터베이스가 비어있습니다",
                        "analysis": None,
                        "recommendations": [],
                    }, 200

                # 이미지 분석 실행
                image_analyzer = get_image_analyzer()
                analysis_result = image_analyzer.analyze_image_comprehensive(
                    filepath, target_category
                )

                # 추천 검색 실행
                room_context = analysis_result["room_analysis"]
                reasoning = analysis_result["recommendation"]["reasoning"]
                search_query = analysis_result["recommendation"]["search_query"]

                search_engine = get_search_engine()
                recommendations = search_engine.search_by_text(
                    search_query, top_k, target_category
                )
                
                # 🔥 FIX: Java DTO와 형식 일치하도록 memberId, timestamp 추가
                import time
                member_id = request.args.get("member_id", None, type=int)  # 쿼리 파라미터에서 memberId 가져오기

                return {
                    "status": "success",
                    "member_id": member_id,  # 🆕 Java: memberId
                    "room_analysis": room_context,
                    "recommendation": {
                        "target_category": target_category,
                        "reasoning": reasoning,
                        "search_query": search_query,
                        "results": recommendations,
                        "result_count": len(recommendations),
                    },
                    "timestamp": int(time.time() * 1000),  # 🆕 Java: timestamp (Unix ms)
                }, 200

            finally:
                # 임시 파일 삭제
                if os.path.exists(filepath):
                    os.remove(filepath)

        except Exception as e:
            logger.error(f"Error in room analysis: {e}")
            return {"status": "error", "message": str(e)}, 500


@api.route("/init-database")
class InitDatabase(Resource):
    """VectorDB 초기화 및 생성"""

    def post(self):
        """
        새로운 벡터 데이터베이스 초기화 및 구축

        요청 형식: application/x-www-form-urlencoded 또는 JSON
        {
            "data_dir": "./data",  # 가구 이미지 디렉토리 경로
            "model_name": "openai/clip-vit-base-patch32"  # CLIP 모델 (선택사항)
        }

        또는 쿼리 파라미터:
        - data_dir: 이미지 디렉토리 경로
        - model_name: CLIP 모델 이름 (선택사항)

        Returns:
            JSON: 초기화 결과 및 통계
        """
        try:
            # 요청 데이터 파싱
            if request.is_json:
                data = request.get_json()
                data_dir = data.get("data_dir", "./data")
                model_name = data.get("model_name", "openai/clip-vit-base-patch32")
            else:
                data_dir = request.args.get("data_dir", "./data")
                model_name = request.args.get(
                    "model_name", "openai/clip-vit-base-patch32"
                )

            if not os.path.exists(data_dir):
                return {
                    "status": "error",
                    "message": f"디렉토리를 찾을 수 없습니다: {data_dir}",
                }, 400

            logger.info(f"Initializing VectorDB with model: {model_name}, data_dir: {data_dir}")

            # 새로운 벡터라이저 생성
            global _vectorizer, _search_engine, _db_loaded
            _vectorizer = CLIPVectorizer(model_name=model_name)
            _search_engine = FurnitureSearchEngine(_vectorizer)

            # 데이터베이스 구축
            logger.info(f"Building database from {data_dir}...")
            success = _vectorizer.build_database(data_dir)

            if not success:
                return {
                    "status": "warning",
                    "message": "구축할 이미지가 없습니다",
                    "total_images": 0,
                }, 200

            # 데이터베이스 저장
            upload_dir = current_app.config.get("UPLOAD_FOLDER", "uploads")
            os.makedirs(upload_dir, exist_ok=True)

            db_path = os.path.join(upload_dir, "furniture_index.faiss")
            db_meta_path = os.path.join(upload_dir, "furniture_metadata.pkl")

            save_success = _vectorizer.save_database(db_path, db_meta_path)

            if save_success:
                _db_loaded = True
                db_info = _vectorizer.get_database_info()

                return {
                    "status": "success",
                    "message": "VectorDB 초기화 완료",
                    "database_info": {
                        "total_images": db_info["total_images"],
                        "categories": db_info["categories"],
                        "category_count": db_info["category_count"],
                        "vector_dimension": db_info["vector_dimension"],
                        "device": db_info["device"],
                    },
                    "saved_to": {
                        "index_path": db_path,
                        "metadata_path": db_meta_path,
                    },
                }, 201

            else:
                return {
                    "status": "error",
                    "message": "데이터베이스 저장 실패",
                }, 500

        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            return {"status": "error", "message": str(e)}, 500


@api.route("/train-images")
class TrainImages(Resource):
    """기존 VectorDB에 이미지 추가/학습"""

    def post(self):
        """
        기존 벡터 데이터베이스에 새로운 이미지 추가 및 재학습

        요청 형식: multipart/form-data
        - files: 추가할 이미지 파일들 (다중 파일)
        - furniture_type: 가구 타입 (필수, 예: 'chair', 'table', 'lamp')
        - save_db: 변경사항 저장 여부 (선택, 기본값: true)

        또는 쿼리 파라미터 기반:
        - data_dir: 이미지 디렉토리 경로
        - furniture_type: 가구 타입
        - save_db: 데이터베이스 저장 여부

        Returns:
            JSON: 학습 결과 및 통계
        """
        try:
            vectorizer = get_vectorizer()

            # 데이터베이스 존재 확인
            if vectorizer.index.ntotal == 0:
                return {
                    "status": "error",
                    "message": "VectorDB가 초기화되지 않았습니다. 먼저 /init-database를 호출하세요.",
                }, 400

            initial_count = vectorizer.index.ntotal
            added_count = 0
            failed_count = 0

            # 경우 1: 파일 업로드 (multipart/form-data)
            if "files" in request.files:
                files = request.files.getlist("files")
                furniture_type = request.form.get("furniture_type")

                if not furniture_type:
                    return {
                        "status": "error",
                        "message": "furniture_type은 필수 파라미터입니다",
                    }, 400

                if not files:
                    return {
                        "status": "error",
                        "message": "추가할 파일이 없습니다",
                    }, 400

                # 임시 디렉토리 생성
                upload_dir = current_app.config.get("UPLOAD_FOLDER", "uploads")
                temp_dir = os.path.join(upload_dir, "temp_train", furniture_type)
                os.makedirs(temp_dir, exist_ok=True)

                logger.info(
                    f"Training with {len(files)} files for category: {furniture_type}"
                )

                # 파일 저장 및 벡터화
                for file in files:
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        filepath = os.path.join(temp_dir, filename)
                        file.save(filepath)

                        # 벡터 DB에 추가
                        if vectorizer.add_image_to_database(filepath, furniture_type):
                            added_count += 1
                        else:
                            failed_count += 1
                    else:
                        failed_count += 1

            # 경우 2: 디렉토리 기반 (쿼리 파라미터)
            elif "data_dir" in request.args:
                data_dir = request.args.get("data_dir")
                furniture_type = request.args.get("furniture_type")

                if not os.path.exists(data_dir):
                    return {
                        "status": "error",
                        "message": f"디렉토리를 찾을 수 없습니다: {data_dir}",
                    }, 400

                logger.info(f"Training from directory: {data_dir}")

                # 디렉토리 기반 추가
                success = vectorizer.add_images_incrementally(data_dir)

                if success:
                    added_count = vectorizer.index.ntotal - initial_count
                else:
                    return {
                        "status": "warning",
                        "message": "추가할 이미지가 없습니다",
                        "added_images": 0,
                        "total_images": vectorizer.index.ntotal,
                    }, 200

            else:
                return {
                    "status": "error",
                    "message": "파일 또는 data_dir을 제공해야 합니다",
                }, 400

            # 데이터베이스 저장
            save_db = request.args.get("save_db", "true").lower() == "true"
            if request.is_json and "save_db" in request.get_json():
                save_db = request.get_json().get("save_db", True)

            saved_to = None
            if save_db and added_count > 0:
                upload_dir = current_app.config.get("UPLOAD_FOLDER", "uploads")
                os.makedirs(upload_dir, exist_ok=True)

                db_path = os.path.join(upload_dir, "furniture_index.faiss")
                db_meta_path = os.path.join(upload_dir, "furniture_metadata.pkl")

                if vectorizer.save_database(db_path, db_meta_path):
                    saved_to = {
                        "index_path": db_path,
                        "metadata_path": db_meta_path,
                    }
                    logger.info(
                        f"Database saved: {db_path}, {db_meta_path}"
                    )

            # 최종 통계
            final_info = vectorizer.get_database_info()

            return {
                "status": "success",
                "message": f"{added_count}개의 이미지 추가 완료",
                "training_result": {
                    "added_images": added_count,
                    "failed_images": failed_count,
                    "initial_count": initial_count,
                    "final_count": vectorizer.index.ntotal,
                },
                "database_info": {
                    "total_images": final_info["total_images"],
                    "categories": final_info["categories"],
                    "category_count": final_info["category_count"],
                    "vector_dimension": final_info["vector_dimension"],
                    "device": final_info["device"],
                },
                "saved_to": saved_to,
            }, 200

        except Exception as e:
            logger.error(f"Error training images: {e}")
            return {"status": "error", "message": str(e)}, 500


@api.route("/add-images")
class AddImages(Resource):
    """데이터베이스에 이미지 추가 (레거시)"""

    def post(self):
        """
        지정된 디렉토리의 이미지를 데이터베이스에 추가

        쿼리 파라미터:
        - data_dir: 이미지 디렉토리 경로

        Returns:
            JSON: 추가 결과
        """
        try:
            data_dir = request.args.get("data_dir", "./data")

            if not os.path.exists(data_dir):
                return {
                    "status": "error",
                    "message": f"디렉토리를 찾을 수 없습니다: {data_dir}",
                }, 400

            vectorizer = get_vectorizer()

            # 기존 데이터베이스가 있으면 추가, 없으면 신규 생성
            if vectorizer.index.ntotal > 0:
                success = vectorizer.add_images_incrementally(data_dir)
            else:
                success = vectorizer.build_database(data_dir)

            if success:
                # 데이터베이스 저장
                upload_dir = current_app.config.get("UPLOAD_FOLDER", "uploads")
                os.makedirs(upload_dir, exist_ok=True)

                db_path = os.path.join(upload_dir, "furniture_index.faiss")
                db_meta_path = os.path.join(upload_dir, "furniture_metadata.pkl")

                vectorizer.save_database(db_path, db_meta_path)

                return {
                    "status": "success",
                    "message": "이미지 추가 완료",
                    "total_images": vectorizer.index.ntotal,
                }, 200
            else:
                return {
                    "status": "warning",
                    "message": "추가할 이미지가 없습니다",
                }, 200

        except Exception as e:
            logger.error(f"Error adding images: {e}")
            return {"status": "error", "message": str(e)}, 500
