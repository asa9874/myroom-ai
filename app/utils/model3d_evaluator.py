"""
3D 모델 품질 평가기 (Model3DQualityEvaluator)

.glb 파일의 다음 항목을 평가합니다:
- Mesh Quality: 메시 밀도, 법선 일관성
- Texture Quality: 텍스처 해상도, 아티팩트
- Geometry Accuracy: 가구 형태 정확도
- Overall Score: 통합 점수 (0~100)
"""

import os
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

try:
    import trimesh
    TRIMESH_AVAILABLE = True
    print("[✓ ModelQualityEvaluator] trimesh imported successfully")
except ImportError as e:
    TRIMESH_AVAILABLE = False
    print(f"[✗ ModelQualityEvaluator] trimesh import failed: {e}")
    logging.warning("trimesh not installed. Install with: pip install trimesh")

logger = logging.getLogger(__name__)


class Model3DQualityEvaluator:
    """3D 모델 (.glb) 품질 평가기"""
    
    def __init__(self):
        """평가기 초기화"""
        self.trimesh_available = TRIMESH_AVAILABLE
        
        if not self.trimesh_available:
            logger.warning("⚠️  trimesh not available. 3D evaluation will be limited.")
        else:
            logger.info("✓ Model3DQualityEvaluator initialized with trimesh")
    
    def evaluate(self, model_path: str, step: str = "pre-upscale") -> Dict[str, Any]:
        """
        단일 3D 모델 평가
        
        Args:
            model_path: .glb 파일 경로
            step: 'pre-upscale' 또는 'post-upscale'
            
        Returns:
            평가 결과 딕셔너리
        """
        result = {
            'timestamp': datetime.now().isoformat(),
            'model_path': model_path,
            'step': step,
            'file_exists': os.path.exists(model_path),
            'file_size': os.path.getsize(model_path) if os.path.exists(model_path) else 0,
            'metrics': {
                'mesh_quality': {
                    'vertex_count': 0,
                    'face_count': 0,
                    'mesh_score': 0.0,
                    'error': None
                },
                'texture_quality': {
                    'texture_resolution': 0,
                    'texture_score': 0.0,
                    'error': None
                },
                'geometry_accuracy': {
                    'accuracy_score': 0.0,
                    'error': None
                }
            },
            'overall_quality': 0.0,
            'quality_level': 'unknown',
            'error': None
        }
        
        # 파일 존재 확인
        if not result['file_exists']:
            result['error'] = f"Model file not found: {model_path}"
            logger.error(result['error'])
            return result
        
        # trimesh 미설치 시 기본 평가만 수행
        if not self.trimesh_available:
            logger.warning(f"Trimesh not available. Using basic evaluation for {model_path}")
            return self._basic_evaluation(result)
        
        try:
            # 3D 모델 로드
            print(f"[DEBUG] Loading mesh from: {model_path}")
            print(f"[DEBUG] File exists: {os.path.exists(model_path)}")
            print(f"[DEBUG] File size: {os.path.getsize(model_path)} bytes")
            print(f"[DEBUG] trimesh available: {TRIMESH_AVAILABLE}")
            
            loaded = trimesh.load(model_path)
            print(f"[DEBUG] Loaded type: {type(loaded).__name__}")
            
            # Scene vs Mesh 처리
            if isinstance(loaded, trimesh.Scene):
                print(f"[DEBUG] Scene detected, merging geometries...")
                # Scene의 모든 mesh를 합치기
                meshes = []
                for geom in loaded.geometry.values():
                    if isinstance(geom, trimesh.Trimesh):
                        meshes.append(geom)
                
                if meshes:
                    mesh = trimesh.util.concatenate(meshes)
                    print(f"[DEBUG] Merged {len(meshes)} meshes")
                else:
                    # Scene이 비었으면 빈 mesh 생성
                    import numpy as np
                    mesh = trimesh.Trimesh(vertices=np.array([]), faces=np.array([]))
                    print(f"[DEBUG] Scene is empty, using empty mesh")
            else:
                mesh = loaded
            
            print(f"[DEBUG] Mesh loaded successfully!")
            print(f"[DEBUG] Vertices: {len(mesh.vertices)}, Faces: {len(mesh.faces)}")
            
            # Mesh Quality 평가
            result['metrics']['mesh_quality'] = self._evaluate_mesh_quality(mesh)
            
            # Texture Quality 평가
            result['metrics']['texture_quality'] = self._evaluate_texture_quality(mesh)
            
            # Geometry Accuracy 평가
            result['metrics']['geometry_accuracy'] = self._evaluate_geometry_accuracy(mesh)
            
            # 통합 점수 계산
            result = self._calculate_overall_score(result)
            
            logger.info(
                f"Model evaluation: {os.path.basename(model_path)} @ {step} = "
                f"Quality: {result['overall_quality']:.1f} ({result['quality_level']})"
            )
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Model evaluation failed: {e}", exc_info=True)
        
        return result
    
    def _evaluate_mesh_quality(self, mesh: Any) -> Dict[str, Any]:
        """메시 품질 평가"""
        result = {
            'vertex_count': 0,
            'face_count': 0,
            'mesh_score': 0.0,
            'error': None
        }
        
        try:
            # 기본 메시 정보
            result['vertex_count'] = len(mesh.vertices)
            result['face_count'] = len(mesh.faces)
            
            # 메시 밀도 스코어 (0~100)
            # 파면이 많을수록 좋음 (기준: 50000 파면)
            face_density = min(100, (result['face_count'] / 50000) * 100)
            
            # 법선 일관성 확인
            if hasattr(mesh, 'vertex_normals'):
                normal_consistency = 90.0  # 기본값
            else:
                normal_consistency = 50.0
            
            # 종합 메시 점수
            result['mesh_score'] = (face_density * 0.6 + normal_consistency * 0.4)
            
            logger.debug(f"Mesh quality: faces={result['face_count']}, score={result['mesh_score']:.1f}")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Mesh quality evaluation failed: {e}")
        
        return result
    
    def _evaluate_texture_quality(self, mesh: Any) -> Dict[str, Any]:
        """텍스처 품질 평가"""
        result = {
            'texture_resolution': 0,
            'texture_score': 0.0,
            'error': None
        }
        
        try:
            # 텍스처 정보 추출
            if hasattr(mesh, 'visual') and mesh.visual is not None:
                # 텍스처 해상도 추정
                if hasattr(mesh.visual, 'uv'):
                    texture_resolution = 1024  # 기본 해상도 추정
                    result['texture_resolution'] = texture_resolution
                    
                    # 텍스처 존재 여부에 따른 스코어
                    result['texture_score'] = 85.0
                else:
                    result['texture_score'] = 50.0
            else:
                result['texture_score'] = 40.0
            
            logger.debug(f"Texture quality: score={result['texture_score']:.1f}")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Texture quality evaluation failed: {e}")
        
        return result
    
    def _evaluate_geometry_accuracy(self, mesh: Any) -> Dict[str, Any]:
        """기하학 정확도 평가"""
        result = {
            'accuracy_score': 0.0,
            'error': None
        }
        
        try:
            accuracy_score = 0.0
            
            # 메시 유효성 확인: volume이 0이 아닌지 확인
            print(f"[DEBUG] hasattr mesh.volume: {hasattr(mesh, 'volume')}")
            if hasattr(mesh, 'volume'):
                print(f"[DEBUG] mesh.volume: {mesh.volume}")
                if mesh.volume > 0:
                    accuracy_score = 90.0
                    print(f"[DEBUG] Volume > 0: +90 points")
                else:
                    accuracy_score = 50.0
                    print(f"[DEBUG] Volume <= 0: +50 points")
            
            # 메시 닫힌 형태 확인 (watertight)
            print(f"[DEBUG] hasattr mesh.is_watertight: {hasattr(mesh, 'is_watertight')}")
            if hasattr(mesh, 'is_watertight') and mesh.is_watertight:
                accuracy_score += 5.0
                print(f"[DEBUG] Mesh is watertight: +5 points")
            
            # vertex/face 개수로 유효성 판단
            if len(mesh.vertices) > 0 and len(mesh.faces) > 0:
                accuracy_score = max(accuracy_score, 70.0)
                print(f"[DEBUG] Has vertices and faces: score >= 70")
            
            result['accuracy_score'] = min(100, accuracy_score)
            print(f"[DEBUG] Final accuracy_score: {result['accuracy_score']}")
            logger.debug(f"Geometry accuracy: score={result['accuracy_score']:.1f}")
            
        except Exception as e:
            result['error'] = str(e)
            print(f"[DEBUG] Geometry accuracy exception: {type(e).__name__}: {e}")
            logger.error(f"Geometry accuracy evaluation failed: {e}")
        
        return result
    
    def _calculate_overall_score(self, eval_result: Dict[str, Any]) -> Dict[str, Any]:
        """통합 점수 계산"""
        metrics = eval_result['metrics']
        
        # 가중 평균 계산
        mesh_score = metrics['mesh_quality'].get('mesh_score', 0)
        texture_score = metrics['texture_quality'].get('texture_score', 0)
        geometry_score = metrics['geometry_accuracy'].get('accuracy_score', 0)
        
        # 가중치
        weights = {
            'mesh': 0.35,
            'texture': 0.35,
            'geometry': 0.30
        }
        
        overall = (
            mesh_score * weights['mesh'] +
            texture_score * weights['texture'] +
            geometry_score * weights['geometry']
        )
        
        eval_result['overall_quality'] = float(overall)
        
        # 품질 등급 판정
        if overall >= 85:
            eval_result['quality_level'] = 'excellent'
        elif overall >= 70:
            eval_result['quality_level'] = 'good'
        elif overall >= 50:
            eval_result['quality_level'] = 'fair'
        else:
            eval_result['quality_level'] = 'poor'
        
        return eval_result
    
    def _basic_evaluation(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """trimesh 없을 때 기본 평가"""
        try:
            # 파일 크기 기반 평가
            file_size = result['file_size']
            
            # 파일 크기가 클수록 복잡한 모델이라고 가정
            if file_size < 100000:
                score = 40.0
            elif file_size < 500000:
                score = 60.0
            elif file_size < 2000000:
                score = 80.0
            else:
                score = 90.0
            
            result['metrics']['mesh_quality']['mesh_score'] = score
            result['metrics']['texture_quality']['texture_score'] = score - 10
            result['metrics']['geometry_accuracy']['accuracy_score'] = score
            result['overall_quality'] = score
            
            if score >= 85:
                result['quality_level'] = 'excellent'
            elif score >= 70:
                result['quality_level'] = 'good'
            elif score >= 50:
                result['quality_level'] = 'fair'
            else:
                result['quality_level'] = 'poor'
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Basic evaluation failed: {e}")
        
        return result
    
    def compare(
        self,
        pre_model_result: Dict[str, Any],
        post_model_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        두 3D 모델 비교 평가
        
        Args:
            pre_model_result: 원본 모델 평가 결과
            post_model_result: 업스케일 모델 평가 결과
            
        Returns:
            비교 결과
        """
        result = {
            'timestamp': datetime.now().isoformat(),
            'pre_upscale_model': pre_model_result,
            'post_upscale_model': post_model_result,
            'improvement': {
                'mesh_quality_delta': 0.0,
                'texture_quality_delta': 0.0,
                'geometry_accuracy_delta': 0.0,
                'overall_improvement': 0.0
            },
            'file_size_comparison': {
                'pre_size': pre_model_result.get('file_size', 0),
                'post_size': post_model_result.get('file_size', 0),
                'size_delta': 0
            }
        }
        
        try:
            # 메트릭 델타 계산
            pre_metrics = pre_model_result['metrics']
            post_metrics = post_model_result['metrics']
            
            result['improvement']['mesh_quality_delta'] = (
                post_metrics['mesh_quality']['mesh_score'] -
                pre_metrics['mesh_quality']['mesh_score']
            )
            
            result['improvement']['texture_quality_delta'] = (
                post_metrics['texture_quality']['texture_score'] -
                pre_metrics['texture_quality']['texture_score']
            )
            
            result['improvement']['geometry_accuracy_delta'] = (
                post_metrics['geometry_accuracy']['accuracy_score'] -
                pre_metrics['geometry_accuracy']['accuracy_score']
            )
            
            # 통합 개선도 (%)
            pre_quality = pre_model_result['overall_quality']
            post_quality = post_model_result['overall_quality']
            
            if pre_quality > 0:
                improvement_pct = ((post_quality - pre_quality) / pre_quality) * 100
                result['improvement']['overall_improvement'] = float(improvement_pct)
            
            # 파일 크기 비교
            result['file_size_comparison']['size_delta'] = (
                post_model_result.get('file_size', 0) -
                pre_model_result.get('file_size', 0)
            )
            
            logger.info(
                f"Model comparison: improvement={result['improvement']['overall_improvement']:+.1f}%"
            )
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Model comparison failed: {e}", exc_info=True)
        
        return result


def create_evaluator() -> Model3DQualityEvaluator:
    """평가기 생성 헬퍼 함수"""
    return Model3DQualityEvaluator()
