from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/add', methods=['POST'])
def add_numbers():
    data = request.get_json()
    
    # 입력 유효성 검사
    if not data or 'a' not in data or 'b' not in data:
        return jsonify({'error': 'Request body must contain "a" and "b".'}), 400
    
    try:
        a = int(data['a'])
        b = int(data['b'])
    except ValueError:
        return jsonify({'error': '"a" and "b" must be integers.'}), 400

    result = a + b
    return jsonify({'sum': result})

if __name__ == '__main__':
    app.run(debug=True)
