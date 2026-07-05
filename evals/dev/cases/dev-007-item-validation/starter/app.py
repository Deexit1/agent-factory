from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/items", methods=["POST"])
def create_item():
    data = request.get_json(force=True)
    name = data.get("name")
    price = data.get("price")
    return jsonify(name=name, price=price), 201


if __name__ == "__main__":
    app.run()
