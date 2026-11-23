from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv(Path(__file__).parent / ".env")

from controlador import api as api_rest
from db import auth

app = Flask(__name__)
auth.configurar(app)
app.register_blueprint(api_rest.api)


@app.get("/")
def inicio():
    return jsonify(servicio="Apertura de Datos", api="/api")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4200, threaded=True)
