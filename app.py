
from flask import Flask, render_template, request
import psycopg
from dotenv import load_dotenv
import os
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

load_dotenv()

db_host = os.environ.get("DB_HOST")
db_port = os.environ.get("DB_PORT")
db_name = os.environ.get("DB_NAME")
db_user = os.environ.get("DB_USER")
db_password = os.environ.get("DB_PASSWORD")

ph = PasswordHasher()

app = Flask(__name__)


@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/recuperar-contrasena")
def recuperar_contrasena():
    return render_template("recuperar-contrasena.html")


@app.route("/login", methods=["POST"])
def login():
    correo = request.form.get("correo")
    contrasena = request.form.get("contrasena")

    error_login = "Correo electrónico o contraseña incorrectos"

    if not correo or not contrasena:
        return render_template("index.html", error=error_login)

    try:
        conexion = psycopg.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password
        )

        try:
            with conexion.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id_usuario, correo, password_hash, id_rol
                    FROM usuarios
                    WHERE correo = %s
                    """,
                    (correo,)
                )
                usuario = cursor.fetchone()

        finally:
            conexion.close()

    except psycopg.Error:
        app.logger.exception("Error al consultar la base de datos")
        return "Error interno del servidor", 500

    if usuario is None:
        return render_template("index.html", error=error_login)

    hash_contrasena = usuario[2]

    try:
        ph.verify(hash_contrasena, contrasena)

    except VerifyMismatchError:
        return render_template("index.html", error=error_login)

    except VerificationError:
        app.logger.exception("Error al verificar el hash")
        return "Error interno del servidor", 500

    return "Inicio de sesión exitoso"


if __name__ == "__main__":
    app.run(debug=True)
