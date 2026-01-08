"""
3D 모델 관련 라우트

생성된 3D 모델 조회 및 관리 API를 제공합니다.
"""

import os
import json
from flask import Blueprint, jsonify, send_file, current_app
from flask_restx import Namespace, Resource, fields
from datetime import datetime

# Blueprint 생성
model3d_bp = Blueprint('model3d', __name__)

# Namespace 생성
api = Namespace('model3d', description='3D 모델 관련 API')

# API 모델 정의
model3d_info = api.model('Model3DInfo', {
    'memberId': fields.Integer(required=True, description='사용자 ID'),
    'imageUrl': fields.String(required=True, description='원본 이미지 URL'),
    'model3dPath': fields.String(required=True, description='생성된 3D 모델 경로'),
    'processedAt': fields.String(required=True, description='처리 완료 시각')
})


@api.route('/models')
class Model3DList(Resource):
    """3D 모델 목록 조회"""
    
    @api.doc('get_model3d_list')
    @api.marshal_list_with(model3d_info)
    def get(self):
        """
        생성된 3D 모델 목록 조회
        
        처리 로그에서 생성된 3D 모델 목록을 조회합니다.
        """
        try:
            log_file = os.path.join(
                current_app.config['UPLOAD_FOLDER'],
                'logs',
                'processing_log.json'
            )
            
            if not os.path.exists(log_file):
                return [], 200
            
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            
            return logs, 200
            
        except Exception as e:
            current_app.logger.error(f"모델 목록 조회 실패: {e}")
            api.abort(500, f"모델 목록 조회 중 오류 발생: {str(e)}")


@api.route('/models/<int:member_id>')
class Model3DByMember(Resource):
    """특정 사용자의 3D 모델 조회"""
    
    @api.doc('get_model3d_by_member')
    @api.marshal_list_with(model3d_info)
    def get(self, member_id):
        """
        특정 사용자의 3D 모델 목록 조회
        
        Args:
            member_id: 사용자 ID
        """
        try:
            log_file = os.path.join(
                current_app.config['UPLOAD_FOLDER'],
                'logs',
                'processing_log.json'
            )
            
            if not os.path.exists(log_file):
                return [], 200
            
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            
            # 특정 사용자의 모델만 필터링
            member_models = [log for log in logs if log.get('memberId') == member_id]
            
            return member_models, 200
            
        except Exception as e:
            current_app.logger.error(f"사용자 모델 조회 실패: {e}")
            api.abort(500, f"사용자 모델 조회 중 오류 발생: {str(e)}")


@api.route('/models/latest')
class LatestModel3D(Resource):
    """최근 생성된 3D 모델 조회"""
    
    @api.doc('get_latest_model3d')
    @api.marshal_with(model3d_info)
    def get(self):
        """
        최근 생성된 3D 모델 조회
        
        가장 최근에 처리된 3D 모델 정보를 반환합니다.
        """
        try:
            log_file = os.path.join(
                current_app.config['UPLOAD_FOLDER'],
                'logs',
                'processing_log.json'
            )
            
            if not os.path.exists(log_file):
                api.abort(404, "생성된 모델이 없습니다.")
            
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            
            if not logs:
                api.abort(404, "생성된 모델이 없습니다.")
            
            # 가장 최근 모델 반환
            latest_model = logs[-1]
            
            return latest_model, 200
            
        except Exception as e:
            current_app.logger.error(f"최근 모델 조회 실패: {e}")
            api.abort(500, f"최근 모델 조회 중 오류 발생: {str(e)}")


@api.route('/stats')
class Model3DStats(Resource):
    """3D 모델 생성 통계"""
    
    @api.doc('get_model3d_stats')
    def get(self):
        """
        3D 모델 생성 통계 조회
        
        전체 생성 개수, 사용자별 통계 등을 반환합니다.
        """
        try:
            log_file = os.path.join(
                current_app.config['UPLOAD_FOLDER'],
                'logs',
                'processing_log.json'
            )
            
            if not os.path.exists(log_file):
                return {
                    'totalCount': 0,
                    'memberStats': {},
                    'recentModels': []
                }, 200
            
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            
            # 통계 계산
            total_count = len(logs)
            member_stats = {}
            
            for log in logs:
                member_id = log.get('memberId')
                if member_id:
                    member_stats[member_id] = member_stats.get(member_id, 0) + 1
            
            # 최근 5개 모델
            recent_models = logs[-5:] if len(logs) >= 5 else logs
            
            return {
                'totalCount': total_count,
                'memberStats': member_stats,
                'recentModels': recent_models
            }, 200
            
        except Exception as e:
            current_app.logger.error(f"통계 조회 실패: {e}")
            api.abort(500, f"통계 조회 중 오류 발생: {str(e)}")
