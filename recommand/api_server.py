import os
import sys
from flask import Flask, jsonify, request
from flask_restx import Api, Resource, Namespace, fields
from werkzeug.utils import secure_filename
import json
from pathlib import Path

# 벡터화 엔진 임포트 시도
try:
    from vectorizer import FurnitureVectorizer
    from vectorize_images import ImageVectorizer
    IMPORTS_OK = True
except ImportError as e:
    print(f"[Warning] 모듈 임포트 실패: {e}")
    IMPORTS_OK = False
    FurnitureVectorizer = None
    ImageVectorizer = None

app = Flask(__name__)

# Flask-RESTX API 설정 (Swagger UI 자동 생성)
api = Api(
    app,
    version='1.0.0',
    title='MyRoom-AI API',
    description='지능형 가구 추천 시스템 API\n\n'
                '방의 이미지를 분석하여 스타일, 색상, 재질을 파악하고,\n'
                'AI 디자이너의 조언을 바탕으로 최적의 가구를 추천합니다.',
    doc='/api/docs'  # Swagger UI 경로
)

# 설정
UPLOAD_FOLDER = './temp_uploads'
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif'}

# 폴더 생성
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# 전역 벡터화 엔진 초기화
vectorizer = None

# ========================================
# Swagger 모델 정의
# ========================================

# 응답 모델
status_model = api.model('Status', {
    'status': fields.String(description='API 상태', example='running'),
    'service': fields.String(description='서비스 이름', example='MyRoom-AI Furniture Recommendation API'),
    'version': fields.String(description='API 버전', example='1.0.0'),
    'db_loaded': fields.Boolean(description='DB 로드 여부', example=True)
})

health_model = api.model('Health', {
    'health': fields.String(description='헬스 상태', example='healthy'),
    'message': fields.String(description='상태 메시지')
})

db_build_request = api.model('DatabaseBuildRequest', {
    'data_dir': fields.String(description='가구 이미지가 있는 디렉토리 경로', example='./data', default='./data')
})

db_info_model = api.model('DatabaseInfo', {
    'loaded': fields.Boolean(description='DB 로드 여부'),
    'total_items': fields.Integer(description='전체 가구 개수'),
    'furniture_types': fields.Raw(description='가구 유형별 개수'),
    'message': fields.String(description='메시지')
})

detected_object_model = api.model('DetectedObject', {
    'label': fields.String(description='객체 라벨', example='sofa'),
    'description': fields.String(description='객체 설명', example='comfortable leather sofa'),
    'box': fields.List(fields.Float, description='바운딩 박스 좌표 [x1, y1, x2, y2]')
})

image_analysis_model = api.model('ImageAnalysis', {
    'style': fields.String(description='스타일', example='modern'),
    'color': fields.String(description='주요 색상', example='white'),
    'material': fields.String(description='재질', example='leather'),
    'detected_objects': fields.List(fields.Nested(detected_object_model), description='감지된 객체'),
    'detailed_names': fields.List(fields.String, description='상세 객체 이름')
})

search_result_model = api.model('SearchResult', {
    'furniture_id': fields.String(description='가구 ID'),
    'furniture_type': fields.String(description='가구 유형'),
    'image_url': fields.String(description='이미지 URL'),
    'similarity': fields.Float(description='유사도 점수'),
    'metadata': fields.Raw(description='메타데이터')
})

search_text_request = api.model('SearchTextRequest', {
    'query': fields.String(required=True, description='검색 쿼리 텍스트', example='white leather sofa'),
    'furniture_type': fields.String(description='가구 유형 필터', example='sofa'),
    'top_k': fields.Integer(description='반환할 결과 개수', example=5, default=5)
})

recommendation_model = api.model('Recommendation', {
    'category': fields.String(description='가구 카테고리'),
    'room_analysis': fields.Nested(api.model('RoomAnalysis', {
        'style': fields.String(description='방 스타일'),
        'color': fields.String(description='방 색상'),
        'material': fields.String(description='방 재질')
    })),
    'designer_advice': fields.String(description='AI 디자이너 조언'),
    'search_query': fields.String(description='생성된 검색 쿼리'),
    'results': fields.List(fields.Nested(search_result_model), description='추천 결과'),
    'result_count': fields.Integer(description='결과 개수')
})

batch_recommendation_model = api.model('BatchRecommendation', {
    'room_analysis': fields.Raw(description='방 분석 정보'),
    'recommendations': fields.List(fields.Nested(api.model('CategoryRecommendation', {
        'category': fields.String(description='가구 카테고리'),
        'designer_advice': fields.String(description='디자이너 조언'),
        'search_query': fields.String(description='검색 쿼리'),
        'results': fields.List(fields.Nested(search_result_model)),
        'result_count': fields.Integer(description='결과 개수')
    })))
})

# 에러 모델
error_model = api.model('Error', {
    'success': fields.Boolean(description='성공 여부', example=False),
    'message': fields.String(description='에러 메시지', example='에러가 발생했습니다.')
})

# 성공 응답 모델
success_response = api.model('SuccessResponse', {
    'success': fields.Boolean(description='성공 여부', example=True),
    'message': fields.String(description='성공 메시지')
})



def allowed_file(filename):
    """파일이 허용된 확장자인지 확인"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def init_vectorizer():
    """벡터화 엔진 초기화"""
    global vectorizer
    if not IMPORTS_OK:
        print("[Error] 필수 모듈을 임포트할 수 없습니다")
        return False
    
    try:
        print("[API] 벡터화 엔진 초기화 중...")
        vectorizer = FurnitureVectorizer()
        
        # DB 로드 시도
        if vectorizer.load_database():
            print("[API] DB 로드 성공")
        else:
            print("[API] 저장된 DB를 찾을 수 없습니다. 비어있는 상태로 시작합니다.")
        
        return True
    except Exception as e:
        print(f"[Error] 벡터화 엔진 초기화 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


# ========================================
# 1. 기본 상태 확인 API
# ========================================

@api.route('/api/status')
class Status(Resource):
    """API 상태 확인"""
    @api.doc('get_status', description='API 서버의 현재 상태를 확인합니다.')
    @api.marshal_with(status_model)
    def get(self):
        """API 상태 조회"""
        return {
            "status": "running",
            "service": "MyRoom-AI Furniture Recommendation API",
            "version": "1.0.0",
            "db_loaded": vectorizer is not None and vectorizer.index.ntotal > 0
        }, 200


@api.route('/api/health')
class Health(Resource):
    """헬스 체크"""
    @api.doc('health_check', description='서버의 헬스 상태를 확인합니다.')
    @api.response(200, 'Success', health_model)
    @api.response(503, 'Service Unavailable', error_model)
    def get(self):
        """Health check"""
        if vectorizer is None:
            return {"health": "unhealthy", "message": "Vectorizer engine not initialized."}, 503
        return {"health": "healthy"}, 200


# ========================================
# 2. DB 관리 API
# ========================================

@api.route('/api/db/build')
class BuildDatabase(Resource):
    """가구 이미지 DB 구축"""
    @api.doc('build_database', description='가구 이미지 디렉토리를 스캔하여 벡터 DB를 구축합니다.')
    @api.expect(db_build_request, validate=False)
    @api.response(200, 'Success', success_response)
    @api.response(400, 'Bad Request', error_model)
    @api.response(500, 'Internal Server Error', error_model)
    def post(self):
        """
        가구 이미지 DB 구축
        
        지정된 디렉토리의 가구 이미지를 스캔하여 벡터 데이터베이스를 생성합니다.
        """
        try:
            data = request.get_json() or {}
            data_dir = data.get('data_dir', './data')
            
            if not os.path.exists(data_dir):
                return {
                    "success": False,
                    "message": f"Directory not found: {data_dir}"
                }, 400
            
            print(f"[API] DB 구축 시작: {data_dir}")
            img_vectorizer = ImageVectorizer()
            img_vectorizer.build_database(data_dir)
            img_vectorizer.save_database()
            
            # 새로운 DB 로드
            global vectorizer
            vectorizer.load_database()
            
            return {
                "success": True,
                "message": "Database built successfully",
                "total_items": vectorizer.index.ntotal
            }, 200
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }, 500


@api.route('/api/db/info')
class DatabaseInfo(Resource):
    """DB 정보 조회"""
    @api.doc('get_database_info', description='현재 로드된 가구 DB의 정보를 조회합니다.')
    @api.marshal_with(db_info_model)
    def get(self):
        """DB 정보 조회"""
        if vectorizer is None or vectorizer.index.ntotal == 0:
            return {
                "loaded": False,
                "total_items": 0,
                "message": "Database not loaded."
            }, 200
        
        # 메타데이터 분석
        furniture_types = {}
        for meta in vectorizer.metadata:
            ftype = meta['furniture_type']
            furniture_types[ftype] = furniture_types.get(ftype, 0) + 1
        
        return {
            "loaded": True,
            "total_items": vectorizer.index.ntotal,
            "furniture_types": furniture_types
        }, 200


# ========================================
# 3. 이미지 분석 API
# ========================================

# 이미지 업로드를 위한 파서
upload_parser = api.parser()
upload_parser.add_argument('image', location='files', type='file', required=True, help='분석할 이미지 파일')

@api.route('/api/analyze/image')
class AnalyzeImage(Resource):
    """방의 이미지를 분석하여 스타일, 색상, 재질, 감지된 객체 추출"""
    @api.doc('analyze_image', description='업로드된 방 이미지를 분석하여 스타일, 색상, 재질 및 감지된 객체를 추출합니다.')
    @api.expect(upload_parser)
    @api.response(200, 'Success', api.model('AnalyzeImageResponse', {
        'success': fields.Boolean(example=True),
        'analysis': fields.Nested(image_analysis_model)
    }))
    @api.response(400, 'Bad Request', error_model)
    @api.response(500, 'Internal Server Error', error_model)
    def post(self):
        """
        이미지 분석
        
        방의 이미지를 분석하여 스타일, 색상, 재질 및 감지된 가구/객체 정보를 반환합니다.
        """
        try:
            if 'image' not in request.files:
                return {
                    "success": False,
                    "message": "Image file is required."
                }, 400
            
            file = request.files['image']
            if file.filename == '':
                return {
                    "success": False,
                    "message": "No file selected."
                }, 400
            
            if not allowed_file(file.filename):
                return {
                    "success": False,
                    "message": f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
                }, 400
            
            # 파일 저장
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # 이미지 분석
            style, color, material, detailed_names, detected_items = vectorizer.get_image_attributes(filepath)
            
            # 감지된 객체 정보 정제
            detected_objects = []
            for item in detected_items:
                detected_objects.append({
                    "label": item['label'],
                    "description": item.get('description', ''),
                    "box": item['box']
                })
            
            # 파일 정리
            os.remove(filepath)
            
            return {
                "success": True,
                "analysis": {
                    "style": style,
                    "color": color,
                    "material": material,
                    "detected_objects": detected_objects,
                    "detailed_names": detailed_names
                }
            }, 200
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }, 500


# ========================================
# 4. 검색 API
# ========================================

# 이미지 검색 파서
search_image_parser = api.parser()
search_image_parser.add_argument('image', location='files', type='file', required=True, help='검색할 이미지')
search_image_parser.add_argument('furniture_type', type=str, required=False, help='가구 유형 필터 (예: sofa, chair, table)')
search_image_parser.add_argument('top_k', type=int, default=5, help='반환할 결과 개수')

@api.route('/api/search/image')
class SearchByImage(Resource):
    """이미지 기반 유사 가구 검색"""
    @api.doc('search_by_image', description='업로드된 이미지와 유사한 가구를 검색합니다.')
    @api.expect(search_image_parser)
    @api.response(200, 'Success', api.model('SearchImageResponse', {
        'success': fields.Boolean(example=True),
        'results': fields.List(fields.Nested(search_result_model)),
        'count': fields.Integer(description='결과 개수')
    }))
    @api.response(400, 'Bad Request', error_model)
    @api.response(500, 'Internal Server Error', error_model)
    def post(self):
        """
        이미지 기반 검색
        
        업로드된 이미지와 유사한 가구를 벡터 DB에서 검색합니다.
        """
        try:
            if 'image' not in request.files:
                return {
                    "success": False,
                    "message": "Image file is required."
                }, 400
            
            file = request.files['image']
            if not allowed_file(file.filename):
                return {
                    "success": False,
                    "message": "File type not allowed."
                }, 400
            
            furniture_type = request.form.get('furniture_type')
            top_k = int(request.form.get('top_k', 5))
            
            # 파일 저장
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # 검색
            results = vectorizer.search_similar(
                query_image_path=filepath,
                furniture_type=furniture_type,
                top_k=top_k
            )
            
            # 파일 정리
            os.remove(filepath)
            
            return {
                "success": True,
                "results": results,
                "count": len(results)
            }, 200
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }, 500


@api.route('/api/search/text')
class SearchByText(Resource):
    """텍스트 기반 유사 가구 검색"""
    @api.doc('search_by_text', description='텍스트 쿼리를 사용하여 유사한 가구를 검색합니다.')
    @api.expect(search_text_request, validate=True)
    @api.response(200, 'Success', api.model('SearchTextResponse', {
        'success': fields.Boolean(example=True),
        'results': fields.List(fields.Nested(search_result_model)),
        'count': fields.Integer(description='결과 개수'),
        'query': fields.String(description='검색 쿼리')
    }))
    @api.response(400, 'Bad Request', error_model)
    @api.response(500, 'Internal Server Error', error_model)
    def post(self):
        """
        텍스트 기반 검색
        
        텍스트 쿼리를 사용하여 유사한 가구를 벡터 DB에서 검색합니다.
        """
        try:
            data = request.get_json()
            if not data or 'query' not in data:
                return {
                    "success": False,
                    "message": "Query text is required."
                }, 400
            
            query = data['query']
            furniture_type = data.get('furniture_type')
            top_k = int(data.get('top_k', 5))
            
            # 검색
            results = vectorizer.search_similar(
                text_query=query,
                furniture_type=furniture_type,
                top_k=top_k
            )
            
            return {
                "success": True,
                "results": results,
                "count": len(results),
                "query": query
            }, 200
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }, 500


# ========================================
# 5. 추천 API
# ========================================

# 가구 추천 파서
recommend_parser = api.parser()
recommend_parser.add_argument('image', location='files', type='file', required=True, help='방 이미지')
recommend_parser.add_argument('category', type=str, required=True, help='추천받을 가구 카테고리 (예: sofa, chair, table)')

@api.route('/api/recommend')
class RecommendFurniture(Resource):
    """방의 이미지를 기반으로 가구 추천 받기"""
    @api.doc('recommend_furniture', description='방 이미지를 분석하여 AI 디자이너의 조언과 함께 가구를 추천합니다.')
    @api.expect(recommend_parser)
    @api.response(200, 'Success', api.model('RecommendResponse', {
        'success': fields.Boolean(example=True),
        'recommendation': fields.Nested(recommendation_model)
    }))
    @api.response(400, 'Bad Request', error_model)
    @api.response(500, 'Internal Server Error', error_model)
    def post(self):
        """
        가구 추천
        
        방 이미지를 분석하여 스타일, 색상, 재질을 파악하고,
        AI 디자이너의 조언을 바탕으로 최적의 가구를 추천합니다.
        """
        try:
            if 'image' not in request.files:
                return {
                    "success": False,
                    "message": "Image file is required."
                }, 400
            
            category = request.form.get('category')
            if not category:
                return {
                    "success": False,
                    "message": "Category is required."
                }, 400
            
            file = request.files['image']
            if not allowed_file(file.filename):
                return {
                    "success": False,
                    "message": "File type not allowed."
                }, 400
            
            # 파일 저장
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # 1. 이미지 분석
            style, color, material, detailed_names, detected_items = vectorizer.get_image_attributes(filepath)
            
            global_context = {
                "style": style,
                "color": color,
                "material": material
            }
            
            # 2. Gemini LLM 조언
            reasoning, search_query = vectorizer.ask_llm_designer(
                global_context,
                detailed_names,
                category
            )
            
            # 3. 검색 실행
            results = vectorizer.search_similar(
                text_query=search_query,
                furniture_type=category,
                top_k=5
            )
            
            # 파일 정리
            os.remove(filepath)
            
            return {
                "success": True,
                "recommendation": {
                    "category": category,
                    "room_analysis": {
                        "style": style,
                        "color": color,
                        "material": material
                    },
                    "designer_advice": reasoning,
                    "search_query": search_query,
                    "results": results,
                    "result_count": len(results)
                }
            }, 200
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }, 500


# 배치 추천 파서
batch_recommend_parser = api.parser()
batch_recommend_parser.add_argument('image', location='files', type='file', required=True, help='방 이미지')
batch_recommend_parser.add_argument('categories', type=str, required=True, help='추천받을 가구 카테고리 목록 (JSON 배열, 예: ["sofa", "chair", "table"])')

@api.route('/api/recommend/batch')
class RecommendBatch(Resource):
    """여러 카테고리에 대해 한 번에 추천받기"""
    @api.doc('recommend_batch', description='방 이미지를 분석하여 여러 가구 카테고리에 대한 추천을 한 번에 받습니다.')
    @api.expect(batch_recommend_parser)
    @api.response(200, 'Success', api.model('BatchRecommendResponse', {
        'success': fields.Boolean(example=True),
        'room_analysis': fields.Raw(description='방 분석 정보'),
        'recommendations': fields.List(fields.Nested(api.model('CategoryRec', {
            'category': fields.String(),
            'designer_advice': fields.String(),
            'search_query': fields.String(),
            'results': fields.List(fields.Nested(search_result_model)),
            'result_count': fields.Integer()
        })))
    }))
    @api.response(400, 'Bad Request', error_model)
    @api.response(500, 'Internal Server Error', error_model)
    def post(self):
        """
        배치 추천
        
        방 이미지를 한 번 분석하여 여러 가구 카테고리에 대한 추천을 동시에 받습니다.
        효율적으로 전체 방의 코디를 받을 수 있습니다.
        """
        try:
            if 'image' not in request.files:
                return {
                    "success": False,
                    "message": "Image file is required."
                }, 400
            
            categories_str = request.form.get('categories', '[]')
            try:
                categories = json.loads(categories_str)
            except:
                return {
                    "success": False,
                    "message": "Categories must be a JSON list."
                }, 400
            
            if not categories:
                return {
                    "success": False,
                    "message": "At least one category is required."
                }, 400
            
            file = request.files['image']
            if not allowed_file(file.filename):
                return {
                    "success": False,
                    "message": "File type not allowed."
                }, 400
            
            # 파일 저장
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # 1. 이미지 분석
            style, color, material, detailed_names, detected_items = vectorizer.get_image_attributes(filepath)
            
            global_context = {
                "style": style,
                "color": color,
                "material": material
            }
            
            # 2. 각 카테고리별 추천
            recommendations = []
            for category in categories:
                reasoning, search_query = vectorizer.ask_llm_designer(
                    global_context,
                    detailed_names,
                    category
                )
                
                results = vectorizer.search_similar(
                    text_query=search_query,
                    furniture_type=category,
                    top_k=5
                )
                
                recommendations.append({
                    "category": category,
                    "designer_advice": reasoning,
                    "search_query": search_query,
                    "results": results,
                    "result_count": len(results)
                })
            
            # 파일 정리
            os.remove(filepath)
            
            return {
                "success": True,
                "room_analysis": global_context,
                "recommendations": recommendations
            }, 200
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }, 500


# ========================================
# 6. 에러 핸들러
# ========================================

# Flask-RESTX handles 404s automatically for its routes
# Custom error handler removed to prevent conflicts with Swagger UI

@app.errorhandler(500)
def internal_error(error):
    return {
        "success": False,
        "message": "Internal server error occurred."
    }, 500


# ========================================
# 앱 시작
# ========================================

if __name__ == '__main__':
    # 벡터화 엔진 초기화
    if not init_vectorizer():
        print("[Error] 벡터화 엔진 초기화 실패")
        sys.exit(1)
    
    print("[API] Flask-RESTful 서버 시작...")
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False
    )
