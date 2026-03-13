"""
3D 모델 파라미터 런타임 관리 API

- 런타임 적용: 파일 변경 없이 서버 메모리에 즉시 반영
- 파일 저장: 필요할 때만 명시적으로 저장
"""

from flask import request
from flask_restx import Namespace, Resource, fields

from app.utils.model3d_params import Model3DParameterManager, RuntimeModel3DParameterStore

ns = Namespace('model3d-params', description='3D 파라미터 런타임 관리 API')

status_model = ns.model('RuntimeParamStatus', {
    'success': fields.Boolean(description='성공 여부'),
    'message': fields.String(description='상태 메시지')
})


@ns.route('/runtime')
class RuntimeParams(Resource):
    @ns.doc('get_runtime_params')
    def get(self):
        """현재 런타임 파라미터 조회"""
        store = RuntimeModel3DParameterStore(Model3DParameterManager())
        return {
            'success': True,
            'params': store.get_params()
        }

    @ns.doc('apply_runtime_params')
    @ns.response(200, '런타임 반영 성공', status_model)
    @ns.response(400, '잘못된 요청', status_model)
    def put(self):
        """런타임 파라미터 전체 적용 (파일 미저장)"""
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return {'success': False, 'message': 'JSON 객체를 요청 본문으로 보내주세요.'}, 400

        store = RuntimeModel3DParameterStore(Model3DParameterManager())
        applied = store.apply_params(payload)
        return {
            'success': True,
            'message': '런타임 파라미터가 적용되었습니다.',
            'params': applied
        }


@ns.route('/runtime/save')
class RuntimeParamsSave(Resource):
    @ns.doc('save_runtime_params_to_file')
    @ns.response(200, '저장 성공', status_model)
    def post(self):
        """현재 런타임 파라미터를 파일에 저장"""
        store = RuntimeModel3DParameterStore(Model3DParameterManager())
        saved = store.persist_to_file()
        return {
            'success': True,
            'message': '현재 런타임 파라미터를 파일에 저장했습니다.',
            'params': saved
        }


@ns.route('/runtime/reload')
class RuntimeParamsReload(Resource):
    @ns.doc('reload_runtime_params_from_file')
    @ns.response(200, '리로드 성공', status_model)
    def post(self):
        """파일 기준으로 런타임 파라미터 재로딩"""
        store = RuntimeModel3DParameterStore(Model3DParameterManager())
        loaded = store.reload_from_file()
        return {
            'success': True,
            'message': '파일 기준으로 런타임 파라미터를 다시 불러왔습니다.',
            'params': loaded
        }
