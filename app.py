
from flask import Flask, render_template, request, session, redirect, url_for
import psycopg
from dotenv import load_dotenv
import os
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from routes.jefatura import jefatura_bp

load_dotenv()

db_host = os.environ.get("DB_HOST")
db_port = os.environ.get("DB_PORT")
db_name = os.environ.get("DB_NAME")
db_user = os.environ.get("DB_USER")
db_password = os.environ.get("DB_PASSWORD")

ph = PasswordHasher()

app = Flask(__name__)
app.register_blueprint(jefatura_bp, url_prefix="/jefatura")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")

@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/recuperar-contrasena")
def recuperar_contrasena():
    return render_template("recuperar-contrasena.html")

@app.route("/panel")
def panel():
    if "usuario_id" not in session:
        return render_template("index.html", error="Debes iniciar sesión para acceder al panel")
    rol = session.get("id_rol")
    if rol == 1:
        return render_template("jefatura/panel-jefatura.html")
    if rol == 2:
        print("Es Lider")
    if rol == 3:
        print("Es Trabajador")
    
    return render_template("panel.html")

@app.route("/cerrar-sesion", methods=["POST"])
def cerrar_sesion():
    session.clear()
    return render_template("index.html", error="Has cerrado sesión correctamente")


@app.route("/login", methods=["POST"])
def login():
    correo = request.form.get("correo")
    contrasena = request.form.get("contrasena")

    error_login = "Correo electrónico o contraseña incorrectos"

    if not correo or not contrasena:
        return render_template("index.html", error=error_login, correo=correo)

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
        return render_template("index.html", error=error_login, correo=correo)

    hash_contrasena = usuario[2]

    try:
        ph.verify(hash_contrasena, contrasena)

    except VerifyMismatchError:
        return render_template("index.html", error=error_login, correo=correo)

    except VerificationError:
        app.logger.exception("Error al verificar el hash")
        return "Error interno del servidor", 500
    
    session.clear()

    session["usuario_id"] = usuario[0]
    session["correo"] = usuario[1]
    session["id_rol"] = usuario[3]

    return redirect(url_for("panel"))


if __name__ == "__main__":
    app.run(debug=True)


# python = Abre el intérprete de Python en la terminal.
# from argon2 import PasswordHasher = Importa la herramienta Argon2.
# ph = PasswordHasher() = Crea el objeto para generar hashes
# ph.hash("TurnoSmart2026!") = Convierte nuestra contraseña de prueba en un hash seguro.
# exit() = Sale del intérprete de Python.
#ph.hash() genera un hash nuevo.
# ph.verify() comprueba si una contraseña coincide con un hash existente.
#correo de prueba = jefatura@turnosmart.cl
#contraseña de prueba = TurnoSmart2026!