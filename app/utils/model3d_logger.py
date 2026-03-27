"""
3D 모델 평가 로거 (Model3DLogger)

평가 결과를 JSON 파일로 저장합니다:
- model3d_pre_<timestamp>.json: 원본 3D 모델 평가
- model3d_post_<timestamp>.json: 업스케일 3D 모델 평가
- model3d_comparison_<timestamp>.json: 비교 평가 결과
"""

import os
import json
import logging
from typing import Dict, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class Model3DLogger:
    """3D 모델 평가 결과 로거"""
    
    def __init__(self, log_dir: str = "logs/model3d_evaluation"):
        """
        로거 초기화
        
        Args:
            log_dir: 로그 저장 디렉토리 (기본값: logs/model3d_evaluation)
        """
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        logger.info(f"Model3DLogger initialized: {log_dir}")
    
    def log_evaluation(
        self,
        eval_result: Dict[str, Any],
        session_id: str = "default"
    ) -> str:
        """
        단일 평가 결과 저장
        
        Args:
            eval_result: 평가 결과 딕셔너리
            session_id: 세션 ID (파일명에 포함됨)
            
        Returns:
            저장된 파일 경로
        """
        try:
            # 타임스탬프 추출
            timestamp = eval_result.get('timestamp', datetime.now().isoformat())
            timestamp_str = datetime.fromisoformat(timestamp).strftime("%Y%m%d_%H%M%S_%f")[:15]
            
            # 파일명 구성
            step = eval_result.get('step', 'unknown')
            filename = f"model3d_{step}_{timestamp_str}_{session_id}.json"
            filepath = os.path.join(self.log_dir, filename)
            
            # 결과 저장
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(eval_result, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Evaluation log saved: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to save evaluation log: {e}", exc_info=True)
            raise
    
    def log_comparison(
        self,
        comparison_result: Dict[str, Any],
        session_id: str = "default"
    ) -> str:
        """
        비교 평가 결과 저장
        
        Args:
            comparison_result: 비교 결과 딕셔너리
            session_id: 세션 ID (파일명에 포함됨)
            
        Returns:
            저장된 파일 경로
        """
        try:
            # 타임스탬프 추출
            timestamp = comparison_result.get('timestamp', datetime.now().isoformat())
            timestamp_str = datetime.fromisoformat(timestamp).strftime("%Y%m%d_%H%M%S_%f")[:15]
            
            # 파일명 구성
            filename = f"model3d_comparison_{timestamp_str}_{session_id}.json"
            filepath = os.path.join(self.log_dir, filename)
            
            # 결과 저장
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(comparison_result, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Comparison log saved: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to save comparison log: {e}", exc_info=True)
            raise
    
    def log_batch(
        self,
        batch_results: list,
        session_id: str = "batch"
    ) -> str:
        """
        배치 평가 결과 저장 (여러 모델)
        
        Args:
            batch_results: 평가 결과 리스트
            session_id: 세션 ID
            
        Returns:
            저장된 파일 경로
        """
        try:
            # 타임스탬프
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:15]
            
            # 파일명 구성
            filename = f"model3d_batch_{timestamp_str}_{session_id}.json"
            filepath = os.path.join(self.log_dir, filename)
            
            # 배치 데이터 구성
            batch_data = {
                'timestamp': datetime.now().isoformat(),
                'total_count': len(batch_results),
                'results': batch_results
            }
            
            # 결과 저장
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(batch_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Batch log saved: {filepath} ({len(batch_results)} models)")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to save batch log: {e}", exc_info=True)
            raise
    
    def get_latest_logs(self, pattern: str = "*.json", limit: int = 5) -> list:
        """
        최근 로그 파일 조회
        
        Args:
            pattern: 파일 패턴 (기본값: *.json)
            limit: 반환 개수 제한
            
        Returns:
            로그 파일 경로 리스트 (최신순)
        """
        try:
            log_files = sorted(
                Path(self.log_dir).glob(pattern),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            return [str(f) for f in log_files[:limit]]
            
        except Exception as e:
            logger.error(f"Failed to get latest logs: {e}")
            return []
    
    def load_log(self, filepath: str) -> Dict[str, Any]:
        """
        로그 파일 로드
        
        Args:
            filepath: 로그 파일 경로
            
        Returns:
            로그 데이터 딕셔너리
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"Log loaded: {filepath}")
            return data
            
        except Exception as e:
            logger.error(f"Failed to load log: {e}")
            raise
    
    def generate_summary(self, results: list) -> Dict[str, Any]:
        """
        평가 결과 요약 생성
        
        Args:
            results: 평가 결과 리스트
            
        Returns:
            요약 데이터
        """
        if not results:
            return {'error': 'No results to summarize'}
        
        summary = {
            'total_count': len(results),
            'timestamp': datetime.now().isoformat(),
            'statistics': {
                'average_quality': 0.0,
                'excellent_count': 0,
                'good_count': 0,
                'fair_count': 0,
                'poor_count': 0,
                'average_file_size': 0
            },
            'quality_distribution': {}
        }
        
        try:
            total_quality = 0
            total_size = 0
            
            for result in results:
                # 품질 통계
                quality = result.get('overall_quality', 0)
                total_quality += quality
                
                # 품질 등급 분포
                level = result.get('quality_level', 'unknown')
                if level == 'excellent':
                    summary['statistics']['excellent_count'] += 1
                elif level == 'good':
                    summary['statistics']['good_count'] += 1
                elif level == 'fair':
                    summary['statistics']['fair_count'] += 1
                elif level == 'poor':
                    summary['statistics']['poor_count'] += 1
                
                # 파일 크기
                total_size += result.get('file_size', 0)
            
            # 평균값 계산
            summary['statistics']['average_quality'] = total_quality / len(results)
            summary['statistics']['average_file_size'] = total_size // len(results)
            
            # 품질 분포율
            if summary['statistics']['total_count'] > 0:
                summary['quality_distribution'] = {
                    'excellent': f"{summary['statistics']['excellent_count'] / len(results) * 100:.1f}%",
                    'good': f"{summary['statistics']['good_count'] / len(results) * 100:.1f}%",
                    'fair': f"{summary['statistics']['fair_count'] / len(results) * 100:.1f}%",
                    'poor': f"{summary['statistics']['poor_count'] / len(results) * 100:.1f}%"
                }
            
            logger.info(f"Summary generated: avg_quality={summary['statistics']['average_quality']:.1f}")
            
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
        
        return summary


def create_logger(log_dir: str = "logs/model3d_evaluation") -> Model3DLogger:
    """로거 생성 헬퍼 함수"""
    return Model3DLogger(log_dir)
