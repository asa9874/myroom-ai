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


@api.route("/health")
class HealthCheck(Resource):
    """서비스 상태 확인"""

    def get(self):
        """
        추천 시스템 상태 확인

        Returns:
            JSON: 서비스 상태 및 데이터베이스 정보
        """
        try:
            vectorizer = get_vectorizer()
            db_info = vectorizer.get_database_info()

            return {
                "status": "ok",
                "message": "Recommendation service is running",
                "database": db_info,
                "timestamp": __import__("datetime").datetime.now().isoformat(),
            }, 200

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "error", "message": str(e)}, 500


@api.route("/categories")
class Categories(Resource):
    """가구 카테고리 관리"""

    def get(self):
        """
        데이터베이스의 모든 가구 카테고리 조회

        Returns:
            JSON: 카테고리 목록 및 개수
        """
        try:
            search_engine = get_search_engine()
            categories = search_engine.get_categories()

            return {
                "status": "success",
                "categories": categories,
                "total_categories": len(categories),
            }, 200

        except Exception as e:
            logger.error(f"Error fetching categories: {e}")
            return {"status": "error", "message": str(e)}, 500


@api.route("/statistics")
class Statistics(Resource):
    """데이터베이스 통계"""

    def get(self):
        """
        데이터베이스의 통계 정보 조회

        Returns:
            JSON: 통계 정보
        """
        try:
            search_engine = get_search_engine()
            stats = search_engine.get_statistics()

            return {"status": "success", "statistics": stats}, 200

        except Exception as e:
            logger.error(f"Error fetching statistics: {e}")
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

                return {
                    "status": "success",
                    "room_analysis": room_context,
                    "recommendation": {
                        "target_category": target_category,
                        "reasoning": reasoning,
                        "search_query": search_query,
                        "results": recommendations,
                        "result_count": len(recommendations),
                    },
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
