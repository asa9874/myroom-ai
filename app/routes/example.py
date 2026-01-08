"""
예제 API

REST API의 기본 CRUD 작업을 보여주는 예제 엔드포인트
"""

from flask import request
from flask_restx import Namespace, Resource, fields
from http import HTTPStatus


# 네임스페이스 생성
ns = Namespace('examples', description='예제 API')

# 데이터 모델 정의
item_model = ns.model('Item', {
    'id': fields.Integer(readonly=True, description='아이템 고유 ID'),
    'name': fields.String(required=True, description='아이템 이름', example='샘플 아이템'),
    'description': fields.String(description='아이템 설명', example='이것은 샘플 아이템입니다'),
    'created_at': fields.String(readonly=True, description='생성 시간')
})

# 아이템 생성 요청 모델
item_input = ns.model('ItemInput', {
    'name': fields.String(required=True, description='아이템 이름', example='새 아이템'),
    'description': fields.String(description='아이템 설명', example='새로운 아이템입니다')
})

# 인메모리 데이터 저장소 (예제용)
items = {}
item_counter = 1


@ns.route('/')
class ItemList(Resource):
    """아이템 목록 리소스"""
    
    @ns.doc('list_items')
    @ns.marshal_list_with(item_model)
    @ns.response(200, '성공')
    def get(self):
        """
        모든 아이템 조회
        
        저장된 모든 아이템의 목록을 반환합니다.
        """
        return list(items.values())
    
    @ns.doc('create_item')
    @ns.expect(item_input, validate=True)
    @ns.marshal_with(item_model, code=HTTPStatus.CREATED)
    @ns.response(201, '아이템 생성 성공')
    @ns.response(400, '잘못된 요청')
    def post(self):
        """
        새 아이템 생성
        
        새로운 아이템을 생성하고 저장합니다.
        """
        global item_counter
        
        data = request.json
        
        # 새 아이템 생성
        new_item = {
            'id': item_counter,
            'name': data['name'],
            'description': data.get('description', ''),
            'created_at': __import__('datetime').datetime.now().isoformat()
        }
        
        items[item_counter] = new_item
        item_counter += 1
        
        return new_item, HTTPStatus.CREATED


@ns.route('/<int:item_id>')
@ns.param('item_id', '아이템 ID')
class Item(Resource):
    """개별 아이템 리소스"""
    
    @ns.doc('get_item')
    @ns.marshal_with(item_model)
    @ns.response(200, '성공')
    @ns.response(404, '아이템을 찾을 수 없음')
    def get(self, item_id):
        """
        특정 아이템 조회
        
        ID로 특정 아이템을 조회합니다.
        """
        if item_id not in items:
            ns.abort(404, f"아이템 {item_id}를 찾을 수 없습니다.")
        
        return items[item_id]
    
    @ns.doc('update_item')
    @ns.expect(item_input, validate=True)
    @ns.marshal_with(item_model)
    @ns.response(200, '아이템 수정 성공')
    @ns.response(404, '아이템을 찾을 수 없음')
    def put(self, item_id):
        """
        아이템 수정
        
        기존 아이템의 정보를 수정합니다.
        """
        if item_id not in items:
            ns.abort(404, f"아이템 {item_id}를 찾을 수 없습니다.")
        
        data = request.json
        
        # 아이템 업데이트
        items[item_id]['name'] = data['name']
        items[item_id]['description'] = data.get('description', '')
        
        return items[item_id]
    
    @ns.doc('delete_item')
    @ns.response(204, '아이템 삭제 성공')
    @ns.response(404, '아이템을 찾을 수 없음')
    def delete(self, item_id):
        """
        아이템 삭제
        
        특정 아이템을 삭제합니다.
        """
        if item_id not in items:
            ns.abort(404, f"아이템 {item_id}를 찾을 수 없습니다.")
        
        del items[item_id]
        
        return '', HTTPStatus.NO_CONTENT


@ns.route('/search')
class ItemSearch(Resource):
    """아이템 검색 리소스"""
    
    @ns.doc('search_items')
    @ns.marshal_list_with(item_model)
    @ns.param('q', '검색 쿼리', required=False)
    @ns.response(200, '성공')
    def get(self):
        """
        아이템 검색
        
        이름 또는 설명에 검색어가 포함된 아이템을 찾습니다.
        """
        query = request.args.get('q', '').lower()
        
        if not query:
            return list(items.values())
        
        # 이름 또는 설명에 검색어가 포함된 아이템 필터링
        results = [
            item for item in items.values()
            if query in item['name'].lower() or query in item['description'].lower()
        ]
        
        return results
