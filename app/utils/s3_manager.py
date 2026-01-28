"""
AWS S3 파일 업로드 관리 모듈

3D 모델과 이미지를 S3에 업로드하고 접근 가능한 URL을 반환합니다.
"""

import os
import logging
from typing import Tuple
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    boto3 = None
    ClientError = Exception
    NoCredentialsError = Exception

logger = logging.getLogger(__name__)


class S3Manager:
    """AWS S3 파일 업로드 및 관리 클래스"""
    
    def __init__(self, config):
        """
        S3 Manager 초기화
        
        Args:
            config: Flask Config 객체 또는 딕셔너리 (AWS 설정 포함)
        """
        self.config = config
        self.bucket_name = config.get('AWS_S3_BUCKET_NAME') or os.environ.get('AWS_S3_BUCKET_NAME')
        self.region = config.get('AWS_S3_REGION') or os.environ.get('AWS_S3_REGION', 'ap-northeast-2')
        self.folder = config.get('AWS_S3_FOLDER') or os.environ.get('AWS_S3_FOLDER', '3d-models')
        
        # AWS 자격증명
        self.access_key = config.get('AWS_ACCESS_KEY_ID') or os.environ.get('AWS_ACCESS_KEY_ID')
        self.secret_key = config.get('AWS_SECRET_ACCESS_KEY') or os.environ.get('AWS_SECRET_ACCESS_KEY')
        
        # S3 클라이언트 초기화
        self.s3_client = None
        self._initialize_s3_client()
    
    def _initialize_s3_client(self):
        """S3 클라이언트 초기화"""
        try:
            if not boto3:
                logger.error("boto3 라이브러리가 설치되지 않았습니다. 'pip install boto3'를 실행하세요.")
                raise ImportError("boto3 is not installed")
            
            if not self.access_key or not self.secret_key:
                logger.error("AWS 자격증명이 설정되지 않았습니다. .env 파일을 확인하세요.")
                raise ValueError("AWS credentials not configured")
            
            self.s3_client = boto3.client(
                's3',
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            )
            
            logger.info(f"✅ S3 클라이언트 초기화 성공: {self.bucket_name} ({self.region})")
            
        except (NoCredentialsError, ValueError) as e:
            logger.error(f"❌ S3 클라이언트 초기화 실패: {e}")
            self.s3_client = None
        except Exception as e:
            logger.error(f"❌ S3 클라이언트 초기화 중 오류: {e}")
            self.s3_client = None
    
    def upload_file(self, file_path: str, member_id: int, model3d_id: int,
                   file_type: str = 'model') -> Tuple[bool, str]:
        """
        파일을 S3에 업로드
        
        Args:
            file_path: 로컬 파일 경로
            member_id: 회원 ID
            model3d_id: 3D 모델 ID
            file_type: 파일 타입 ('model', 'image', 'thumbnail')
            
        Returns:
            (성공 여부, S3 URL 또는 에러 메시지) 튜플
        """
        try:
            if not os.path.exists(file_path):
                logger.error(f"파일을 찾을 수 없습니다: {file_path}")
                return False, f"File not found: {file_path}"
            
            if not self.s3_client:
                logger.error("S3 클라이언트가 초기화되지 않았습니다.")
                return False, "S3 client not initialized"
            
            # S3 키 생성
            # 3D 모델: folder/member_id/model3d_id_filename
            # 다른 파일: folder/file_type/member_id/model3d_id/filename
            filename = os.path.basename(file_path)
            
            if file_type == 'model':
                # 3D 모델은 간단한 경로 사용: 3ds/1/302_20260128_204530.glb
                s3_key = f"{self.folder}/{member_id}/{model3d_id}_{filename}"
            else:
                # 다른 파일 타입은 기존 경로 유지
                s3_key = f"{self.folder}/{file_type}/member_{member_id}/model_{model3d_id}/{filename}"
            
            # 파일 업로드
            logger.info(f"S3 업로드 시작: {file_path} → {s3_key}")
            
            self.s3_client.upload_file(
                file_path,
                self.bucket_name,
                s3_key,
                ExtraArgs={'ContentType': self._get_content_type(filename)}
            )
            
            # S3 URL 생성
            s3_url = f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
            
            logger.info(f"✅ S3 업로드 성공: {s3_url}")
            
            return True, s3_url
            
        except ClientError as e:
            error_msg = f"S3 업로드 실패 (ClientError): {e}"
            logger.error(error_msg)
            return False, error_msg
        
        except Exception as e:
            error_msg = f"S3 업로드 중 오류: {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def upload_model_3d(self, file_path: str, member_id: int, model3d_id: int) -> Tuple[bool, str]:
        """
        3D 모델 파일을 S3에 업로드
        
        Args:
            file_path: 로컬 3D 모델 파일 경로
            member_id: 회원 ID
            model3d_id: 3D 모델 ID
            
        Returns:
            (성공 여부, S3 URL 또는 에러 메시지) 튜플
        """
        return self.upload_file(file_path, member_id, model3d_id, file_type='model')
    
    def upload_image(self, file_path: str, member_id: int, model3d_id: int) -> Tuple[bool, str]:
        """
        이미지 파일을 S3에 업로드
        
        Args:
            file_path: 로컬 이미지 파일 경로
            member_id: 회원 ID
            model3d_id: 3D 모델 ID
            
        Returns:
            (성공 여부, S3 URL 또는 에러 메시지) 튜플
        """
        return self.upload_file(file_path, member_id, model3d_id, file_type='image')
    
    def upload_thumbnail(self, file_path: str, member_id: int, model3d_id: int) -> Tuple[bool, str]:
        """
        썸네일 파일을 S3에 업로드
        
        Args:
            file_path: 로컬 썸네일 파일 경로
            member_id: 회원 ID
            model3d_id: 3D 모델 ID
            
        Returns:
            (성공 여부, S3 URL 또는 에러 메시지) 튜플
        """
        return self.upload_file(file_path, member_id, model3d_id, file_type='thumbnail')
    
    @staticmethod
    def _get_content_type(filename: str) -> str:
        """
        파일 확장자에 따른 Content-Type 반환
        
        Args:
            filename: 파일명
            
        Returns:
            Content-Type 문자열
        """
        ext = Path(filename).suffix.lower()
        
        content_types = {
            '.glb': 'model/gltf-binary',
            '.gltf': 'model/gltf+json',
            '.obj': 'model/obj',
            '.mtl': 'model/mtl',
            '.fbx': 'model/x-fbx',
            '.zip': 'application/zip',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        
        return content_types.get(ext, 'application/octet-stream')
    
    def delete_file(self, s3_key: str) -> Tuple[bool, str]:
        """
        S3의 파일 삭제
        
        Args:
            s3_key: S3 버킷 내 파일 경로 (폴더 포함)
            
        Returns:
            (성공 여부, 메시지) 튜플
        """
        try:
            if not self.s3_client:
                logger.error("S3 클라이언트가 초기화되지 않았습니다.")
                return False, "S3 client not initialized"
            
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            logger.info(f"✅ S3 파일 삭제 성공: {s3_key}")
            return True, f"File deleted: {s3_key}"
            
        except ClientError as e:
            error_msg = f"S3 파일 삭제 실패: {e}"
            logger.error(error_msg)
            return False, error_msg
        
        except Exception as e:
            error_msg = f"S3 파일 삭제 중 오류: {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def is_available(self) -> bool:
        """
        S3 서비스 가용 여부 확인
        
        Returns:
            S3 클라이언트가 정상 초기화되었는지 여부
        """
        return self.s3_client is not None
