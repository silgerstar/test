from flask import Flask, request, jsonify

app = Flask(__name__)

@app.get("/")
def health():
    return {"ok": True}

@app.post("/add")
def add_numbers():
    data = request.get_json()
    if not data or 'a' not in data or 'b' not in data:
        return jsonify({'error': 'Request body must contain "a" and "b".'}), 400
    try:
        a = int(data['a']); b = int(data['b'])
    except ValueError:
        return jsonify({'error': '"a" and "b" must be integers.'}), 400
    return jsonify({'sum': a + b})
# ⛔️ __main__에서 app.run() 넣지 않음
