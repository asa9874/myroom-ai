from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/hello', methods=['GET'])
def hello():
    """기본적인 문자열 반환 API"""
    return jsonify({"message": "Hello, World!"})

@app.route('/greet/<name>', methods=['GET'])
def greet(name):
    """이름을 받아서 인사말을 반환하는 API"""
    return jsonify({"message": f"Hello, {name}!"})

@app.route('/api/status', methods=['GET'])
def status():
    """API 상태를 반환"""
    return jsonify({"status": "running", "version": "1.0.0"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
