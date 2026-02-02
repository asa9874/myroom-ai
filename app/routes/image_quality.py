"""
이미지 품질 검증 API

3D 모델 생성 전 이미지 품질을 검증하는 API 엔드포인트
"""

import os
import tempfile
import logging
from flask import request, current_app
from flask_restx import Namespace, Resource, fields
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage

# 이미지 품질 검증 모듈 import
from app.utils.image_quality import (
    detailed_validate,
    quick_validate,
    get_image_score,
    is_good_for_3d
)
from app.utils.model3d_generator import Model3DGenerator, QUALITY_THRESHOLDS

logger = logging.getLogger(__name__)

# 네임스페이스 생성
ns = Namespace('image-quality', description='이미지 품질 검증 API')

# 파일 업로드 파서
upload_parser = ns.parser()
upload_parser.add_argument(
    'image', 
    location='files', 
    type=FileStorage, 
    required=True, 
    help='검증할 이미지 파일 (jpg, png, webp)'
)
upload_parser.add_argument(
    'strict_mode',
    location='form',
    type=str,
    required=False,
    default='false',
    help='엄격 모드 (true: 80점 이상 필요, false: 50점 이상)'
)

# 응답 모델 정의
quality_scores_model = ns.model('QualityScores', {
    'blur_score': fields.Float(description='흐림 점수 (0-100)'),
    'brightness_score': fields.Float(description='밝기 점수 (0-100)'),
    'contrast_score': fields.Float(description='대비 점수 (0-100)'),
    'object_score': fields.Float(description='객체 완전성 점수 (0-100)'),
    'composition_score': fields.Float(description='구도 점수 (0-100)')
})

object_info_model = ns.model('ObjectInfo', {
    'detected_objects': fields.Integer(description='감지된 객체 수'),
    'main_object_ratio': fields.Float(description='주 객체 비율'),
    'multi_object_penalty': fields.Float(description='다중 객체 페널티')
})

quality_result_model = ns.model('QualityResult', {
    'success': fields.Boolean(description='요청 성공 여부'),
    'score': fields.Float(description='종합 품질 점수 (0-100)'),
    'quality_tier': fields.String(description='품질 등급 (premium/standard/basic/rejected)'),
    'can_proceed': fields.Boolean(description='3D 모델 생성 진행 가능 여부'),
    'is_valid': fields.Boolean(description='최소 품질 기준 충족 여부'),
    'scores': fields.Nested(quality_scores_model, description='개별 점수'),
    'issues': fields.List(fields.String, description='발견된 문제점'),
    'recommendations': fields.List(fields.String, description='개선 권장사항'),
    'object_info': fields.Nested(object_info_model, description='객체 감지 정보'),
    'processing_params': fields.Raw(description='권장 처리 파라미터'),
    'thresholds': fields.Raw(description='품질 기준 임계값')
})

quick_result_model = ns.model('QuickResult', {
    'success': fields.Boolean(description='요청 성공 여부'),
    'score': fields.Float(description='품질 점수 (0-100)'),
    'is_good': fields.Boolean(description='3D 모델링에 적합 여부'),
    'message': fields.String(description='결과 메시지'),
    'quality_tier': fields.String(description='품질 등급')
})

thresholds_model = ns.model('Thresholds', {
    'premium': fields.Integer(description='프리미엄 등급 기준'),
    'standard': fields.Integer(description='표준 등급 기준'),
    'minimum': fields.Integer(description='최소 등급 기준')
})


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}


def allowed_file(filename):
    """허용된 파일 확장자 확인"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@ns.route('/validate')
class ImageQualityValidate(Resource):
    """이미지 품질 상세 검증"""
    
    @ns.doc('validate_image_quality')
    @ns.expect(upload_parser)
    @ns.marshal_with(quality_result_model)
    @ns.response(200, '검증 성공')
    @ns.response(400, '잘못된 요청')
    @ns.response(500, '서버 오류')
    def post(self):
        """
        이미지 품질 상세 검증
        
        업로드된 이미지의 품질을 검증하고 3D 모델 생성 가능 여부를 판단합니다.
        
        **검증 항목:**
        - 흐림 정도 (blur)
        - 밝기 (brightness)
        - 대비 (contrast)
        - 객체 완전성 (object completeness)
        - 구도 (composition)
        
        **품질 등급:**
        - premium (80점 이상): 최고 품질 3D 모델 생성 가능
        - standard (70점 이상): 표준 품질 3D 모델 생성 가능
        - basic (50점 이상): 기본 품질, 품질 저하 가능
        - rejected (50점 미만): 3D 모델 생성 불가
        """
        # 파일 확인
        if 'image' not in request.files:
            return {'success': False, 'error': '이미지 파일이 필요합니다'}, 400
        
        file = request.files['image']
        
        if file.filename == '':
            return {'success': False, 'error': '파일이 선택되지 않았습니다'}, 400
        
        if not allowed_file(file.filename):
            return {
                'success': False, 
                'error': f'허용되지 않은 파일 형식입니다. 허용: {", ".join(ALLOWED_EXTENSIONS)}'
            }, 400
        
        # strict_mode 파라미터 처리
        strict_mode = request.form.get('strict_mode', 'false').lower() == 'true'
        
        # 임시 파일로 저장
        temp_dir = tempfile.mkdtemp()
        filename = secure_filename(file.filename)
        temp_path = os.path.join(temp_dir, filename)
        
        try:
            file.save(temp_path)
            logger.info(f"이미지 품질 검증 요청: {filename}")
            
            # Generator의 품질 검증 메서드 사용
            generator = Model3DGenerator(enable_quality_check=True)
            result = generator.validate_image_quality(temp_path, strict_mode=strict_mode)
            
            return {
                'success': True,
                'score': result['score'],
                'quality_tier': result['quality_tier'],
                'can_proceed': result['can_proceed'],
                'is_valid': result['score'] >= QUALITY_THRESHOLDS['minimum'],
                'scores': result.get('scores', {}),
                'issues': result.get('issues', []),
                'recommendations': result.get('recommendations', []),
                'object_info': result.get('object_info', {}),
                'processing_params': result.get('processing_params', {}),
                'thresholds': QUALITY_THRESHOLDS
            }
            
        except Exception as e:
            logger.error(f"이미지 품질 검증 실패: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}, 500
            
        finally:
            # 임시 파일 정리
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                os.rmdir(temp_dir)
            except Exception as e:
                logger.warning(f"임시 파일 정리 실패: {e}")


@ns.route('/quick-check')
class ImageQuickCheck(Resource):
    """빠른 이미지 품질 검사"""
    
    @ns.doc('quick_check')
    @ns.expect(upload_parser)
    @ns.marshal_with(quick_result_model)
    @ns.response(200, '검사 성공')
    @ns.response(400, '잘못된 요청')
    def post(self):
        """
        빠른 이미지 품질 검사
        
        간단한 품질 점수와 3D 모델링 적합 여부만 확인합니다.
        상세 검증보다 빠르게 결과를 반환합니다.
        """
        if 'image' not in request.files:
            return {'success': False, 'error': '이미지 파일이 필요합니다'}, 400
        
        file = request.files['image']
        
        if file.filename == '' or not allowed_file(file.filename):
            return {'success': False, 'error': '유효한 이미지 파일을 업로드해주세요'}, 400
        
        temp_dir = tempfile.mkdtemp()
        filename = secure_filename(file.filename)
        temp_path = os.path.join(temp_dir, filename)
        
        try:
            file.save(temp_path)
            
            # 빠른 검사
            generator = Model3DGenerator(enable_quality_check=True)
            passed, score, message = generator.quick_quality_check(temp_path)
            
            # 품질 등급 결정
            if score >= QUALITY_THRESHOLDS['premium']:
                tier = 'premium'
            elif score >= QUALITY_THRESHOLDS['standard']:
                tier = 'standard'
            elif score >= QUALITY_THRESHOLDS['minimum']:
                tier = 'basic'
            else:
                tier = 'rejected'
            
            return {
                'success': True,
                'score': score,
                'is_good': passed,
                'message': message,
                'quality_tier': tier
            }
            
        except Exception as e:
            logger.error(f"빠른 품질 검사 실패: {e}")
            return {'success': False, 'error': str(e)}, 500
            
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                os.rmdir(temp_dir)
            except:
                pass


@ns.route('/thresholds')
class QualityThresholds(Resource):
    """품질 기준 임계값 조회"""
    
    @ns.doc('get_thresholds')
    @ns.marshal_with(thresholds_model)
    @ns.response(200, '성공')
    def get(self):
        """
        품질 기준 임계값 조회
        
        현재 설정된 품질 등급별 임계값을 반환합니다.
        
        - **premium**: 프리미엄 등급 (최고 품질)
        - **standard**: 표준 등급
        - **minimum**: 최소 등급 (이하는 거부)
        """
        return QUALITY_THRESHOLDS


@ns.route('/batch-validate')
class BatchValidate(Resource):
    """여러 이미지 일괄 검증"""
    
    batch_parser = ns.parser()
    batch_parser.add_argument(
        'images',
        location='files',
        type=FileStorage,
        required=True,
        action='append',
        help='검증할 이미지 파일들'
    )
    
    @ns.doc('batch_validate')
    @ns.expect(batch_parser)
    @ns.response(200, '검증 성공')
    @ns.response(400, '잘못된 요청')
    def post(self):
        """
        여러 이미지 일괄 검증
        
        여러 이미지를 한 번에 검증하여 결과를 반환합니다.
        """
        if 'images' not in request.files:
            return {'success': False, 'error': '이미지 파일들이 필요합니다'}, 400
        
        files = request.files.getlist('images')
        
        if not files:
            return {'success': False, 'error': '파일이 선택되지 않았습니다'}, 400
        
        results = []
        temp_dir = tempfile.mkdtemp()
        
        try:
            generator = Model3DGenerator(enable_quality_check=True)
            
            for file in files:
                if file.filename == '' or not allowed_file(file.filename):
                    results.append({
                        'filename': file.filename or 'unknown',
                        'success': False,
                        'error': '유효하지 않은 파일'
                    })
                    continue
                
                filename = secure_filename(file.filename)
                temp_path = os.path.join(temp_dir, filename)
                
                try:
                    file.save(temp_path)
                    passed, score, message = generator.quick_quality_check(temp_path)
                    
                    results.append({
                        'filename': filename,
                        'success': True,
                        'score': score,
                        'is_good': passed,
                        'message': message
                    })
                except Exception as e:
                    results.append({
                        'filename': filename,
                        'success': False,
                        'error': str(e)
                    })
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            
            # 요약 통계
            successful = [r for r in results if r.get('success')]
            passed_count = sum(1 for r in successful if r.get('is_good'))
            avg_score = sum(r.get('score', 0) for r in successful) / len(successful) if successful else 0
            
            return {
                'success': True,
                'total': len(files),
                'processed': len(successful),
                'passed': passed_count,
                'failed': len(successful) - passed_count,
                'average_score': round(avg_score, 1),
                'results': results
            }
            
        except Exception as e:
            logger.error(f"일괄 검증 실패: {e}")
            return {'success': False, 'error': str(e)}, 500
            
        finally:
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
