from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

conversion_factors = {
    'meter': 1.0,
    'kilometer': 1000.0,
    'foot': 0.3048,
    'mile': 1609.34
}


@app.route('/')
def home():
    return "Unit Converter API is running."


@app.route('/convert', methods=['GET'])
def convert():
    from_unit = request.args.get('from')
    to_unit = request.args.get('to')
    value = request.args.get('value', type=float)

    if from_unit not in conversion_factors or to_unit not in conversion_factors:
        return jsonify({'error': 'Invalid units'}), 400
    if value is None:
        return jsonify({'error': 'Missing value'}), 400

    # Convert to meters first, then to target unit
    value_in_meters = value * conversion_factors[from_unit]
    converted_value = value_in_meters / conversion_factors[to_unit]

    return jsonify({
        'from': from_unit,
        'to': to_unit,
        'input': value,
        'result': converted_value
    })


if __name__ == '__main__':
    app.run(debug=True)
