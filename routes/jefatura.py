
import os
import re
import secrets

import psycopg
from psycopg import errors
from argon2 import PasswordHasher
from datetime import date
from flask import (
    Blueprint,
    render_template,
    session,
    redirect,
    url_for,
    request,
)


jefatura_bp = Blueprint("jefatura", __name__)
ph = PasswordHasher()


def conectar_bd():
    return psycopg.connect(
        host=os.environ.get("DB_HOST"),
        port=os.environ.get("DB_PORT"),
        dbname=os.environ.get("DB_NAME"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
    )


def acceso_jefatura():
    if "usuario_id" not in session:
        return redirect(url_for("inicio"))

    if session.get("id_rol") != 1:
        return "Acceso denegado", 403

    return None


@jefatura_bp.route("/trabajadores")
def jefatura_trabajadores():
    acceso = acceso_jefatura()
    if acceso is not None:
        return acceso

    try:
        with conectar_bd() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        t.id_trabajador,
                        t.nombre,
                        t.apellido,
                        u.correo,
                        r.nombre_rol
                    FROM trabajadores t
                    JOIN usuarios u
                        ON t.id_usuario = u.id_usuario
                    JOIN roles r
                        ON u.id_rol = r.id_rol
                    ORDER BY t.id_trabajador
                """)

                filas = cursor.fetchall()

        trabajadores = [
            {
                "id": fila[0],
                "nombre": f"{fila[1]} {fila[2]}",
                "correo": fila[3],
                "rol": fila[4],
            }
            for fila in filas
        ]

    except psycopg.Error:
        jefatura_bp.logger.exception(
            "Error al consultar trabajadores"
        ) if hasattr(jefatura_bp, "logger") else None
        return "Error al consultar trabajadores", 500

    return render_template(
        "jefatura/trabajadores.html",
        trabajadores=trabajadores,
    )


@jefatura_bp.route(
    "/ingreso-trabajadores",
    methods=["GET", "POST"],
)
def ingreso_trabajadores():
    acceso = acceso_jefatura()
    if acceso is not None:
        return acceso

    try:
        with conectar_bd() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute("""
                    SELECT id_cargo, nombre_cargo
                    FROM cargos
                    ORDER BY nombre_cargo
                """)

                cargos = [
                    {
                        "id_cargo": fila[0],
                        "nombre_cargo": fila[1],
                    }
                    for fila in cursor.fetchall()
                ]

        if request.method == "GET":
            session["csrf_token"] = secrets.token_hex(16)
            return render_template(
                "jefatura/ingreso-trabajadores.html",
                cargos=cargos,
                csrf_token=session["csrf_token"],  
            )

        # El formulario debe tener protección CSRF
        # antes de habilitar el registro.
        token = request.form.get("csrf_token", "")
        if not token or token != session.get("csrf_token"):
            session["csrf_token"] = secrets.token_hex(16)
            return render_template(
            "jefatura/ingreso-trabajadores.html",
            cargos=cargos,
            error="Solicitud no válida",
            csrf_token=session["csrf_token"],
        ), 400
        

        nombre = request.form.get("nombre", "").strip()
        apellido = request.form.get("apellido", "").strip()
        rut = request.form.get("rut", "").strip().upper()
        correo = request.form.get("correo", "").strip().lower()
        contrasena = request.form.get("contrasena", "")
        rol = request.form.get("rol", "")
        modalidad = request.form.get("modalidad_turno", "")
        cargo = request.form.get("cargo", "")

        if not all([
            nombre, apellido, rut, correo,
            contrasena, rol, modalidad, cargo,
        ]):
            error = "Debes completar todos los campos."
        elif len(nombre) > 20 or len(apellido) > 20:
            error = "Nombre y apellido admiten hasta 20 caracteres."
        elif len(rut) > 12:
            error = "El RUT es demasiado largo."
        elif len(correo) > 150 or "@" not in correo:
            error = "Correo electrónico no válido."
        elif len(contrasena) < 12:
            error = "La contraseña debe tener al menos 12 caracteres."
        elif rol not in ("1", "2", "3"):
            error = "Selecciona un rol válido."
        elif modalidad not in ("FIJO", "ROTATIVO"):
            error = "Selecciona una modalidad válida."
        elif not cargo.isdigit():
            error = "Selecciona un cargo válido."
        elif int(cargo) not in [
            item["id_cargo"] for item in cargos
        ]:
            error = "El cargo seleccionado no existe."
        else:
            error = None

        if error:
            return render_template(
                "jefatura/ingreso-trabajadores.html",
                cargos=cargos,
                error=error,
                 csrf_token=session["csrf_token"],
            ), 400

        hash_contrasena = ph.hash(contrasena)

        with conectar_bd() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO usuarios (
                        correo,
                        password_hash,
                        id_rol
                    )
                    VALUES (%s, %s, %s)
                    RETURNING id_usuario
                """, (
                    correo,
                    hash_contrasena,
                    int(rol),
                ))

                id_usuario = cursor.fetchone()[0]

                cursor.execute("""
                    INSERT INTO trabajadores (
                        id_usuario,
                        rut,
                        nombre,
                        apellido,
                        modalidad_turno,
                        id_cargo
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    id_usuario,
                    rut,
                    nombre,
                    apellido,
                    modalidad,
                    int(cargo),
                ))

        return redirect(
            url_for("jefatura.jefatura_trabajadores")
        )

    except errors.UniqueViolation:
        return render_template(
            "jefatura/ingreso-trabajadores.html",
            cargos=cargos,
            error="El correo o RUT ya está registrado.",
            csrf_token=session["csrf_token"],
        ), 400

    except psycopg.Error:
        return "Error al procesar los datos", 500

@jefatura_bp.route("/configuracion", methods=["GET", "POST"])
def configuracion():
    acceso = acceso_jefatura()
    if acceso is not None:
        return acceso

    # Validar y guardar los cambios
    if request.method == "POST":
    

        token = request.form.get("csrf_token", "")

        if not token or token != session.get("csrf_token"):
            return "Solicitud no válida", 400

        try:
            cantidades = {}

            for codigo in ("24", "11", "7"):
                cantidad = int(
                    request.form.get(f"cantidad_{codigo}", "")
                )

                if cantidad < 1 or cantidad > 2147483647:
                    return "Cantidad no válida", 400

                cantidades[codigo] = cantidad

        except ValueError:
            return "Debes ingresar cantidades válidas", 400

        try:
            with conectar_bd() as conexion:
                with conexion.cursor() as cursor:

                    for codigo, cantidad in cantidades.items():
                        cursor.execute("""
                            UPDATE dotacion_turnos
                            SET cantidad_minima = %s
                            WHERE id_turno = (
                                SELECT id_turno
                                FROM turnos
                                WHERE codigo_turno = %s
                            )
                        """, (cantidad, codigo))

                        if cursor.rowcount != 1:
                            raise ValueError("Dotación inexistente")

        except ValueError:
            return "No se encontraron todas las dotaciones", 400

        except psycopg.Error:
            return "Error al actualizar la dotación", 500

        return redirect(url_for("jefatura.configuracion"))

    # Consultar los datos
    try:
        with conectar_bd() as conexion:
            with conexion.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        id_turno,
                        codigo_turno,
                        nombre_turno,
                        hora_inicio,
                        hora_fin,
                        termina_dia_siguiente
                    FROM turnos
                    ORDER BY hora_inicio
                """)

                turnos = cursor.fetchall()

                cursor.execute("""
                    SELECT
                        codigo_turno,
                        nombre_turno,
                        cantidad_minima
                    FROM turnos
                    INNER JOIN dotacion_turnos
                    ON turnos.id_turno = dotacion_turnos.id_turno
                    ORDER BY hora_inicio
                """)

                dotaciones = cursor.fetchall()

    except psycopg.Error:
        return "Error al consultar la configuración", 500

    session["csrf_token"] = secrets.token_hex(16)

    return render_template(
        "jefatura/configuracion.html",
        turnos=turnos,
        dotaciones=dotaciones,
        csrf_token=session["csrf_token"]
    )
@jefatura_bp.route("/disponibilidad", methods=["GET", "POST"])
def disponibilidad():
    acceso = acceso_jefatura()
    if acceso is not None:
        return acceso

    # Registrar una nueva ausencia
    if request.method == "POST":

        token = request.form.get("csrf_token", "")

        if not token or token != session.get("csrf_token"):
            return "Solicitud no válida", 400

        id_trabajador = request.form.get("id_trabajador", "")
        tipo_ausencia = request.form.get("tipo_ausencia", "")
        fecha_inicio = request.form.get("fecha_inicio", "")
        fecha_fin = request.form.get("fecha_fin", "")
        observacion = request.form.get("observacion", "").strip()
        

        # Validar trabajador y fechas
        try:
            id_trabajador = int(id_trabajador)
            fecha_inicio = date.fromisoformat(fecha_inicio)
            fecha_fin = date.fromisoformat(fecha_fin)

        except ValueError:
            return "Trabajador o fechas no válidas", 400

        # Validar tipo de ausencia
        if tipo_ausencia not in (
            "VACACIONES", "LICENCIA", "INASISTENCIA"
        ):
            return "Tipo de ausencia no válido", 400

        # Validar periodo
        if fecha_fin < fecha_inicio:
            return "La fecha de término no puede ser anterior al inicio", 400

        if len(observacion) > 255:
            return "La observación es demasiado extensa", 400

        try:
            with conectar_bd() as conexion:
                with conexion.cursor() as cursor:

                    # Comprobar que el trabajador existe
                    cursor.execute("""
                        SELECT id_trabajador
                        FROM trabajadores
                        WHERE id_trabajador = %s
                        FOR UPDATE
                    """, (id_trabajador,))

                    if cursor.fetchone() is None:
                        return "El trabajador no existe", 400

                    # Comprobar ausencias superpuestas
                    cursor.execute("""
                        SELECT id_ausencia
                        FROM ausencias
                        WHERE id_trabajador = %s
                        AND fecha_inicio <= %s
                        AND fecha_fin >= %s
                    """, (
                        id_trabajador,
                        fecha_fin,
                        fecha_inicio
                    ))

                    if cursor.fetchone() is not None:
                        return "El trabajador ya tiene una ausencia durante ese periodo", 400

                    # Registrar ausencia
                    cursor.execute("""
                        INSERT INTO ausencias (
                            id_trabajador,
                            tipo_ausencia,
                            fecha_inicio,
                            fecha_fin,
                            observacion
                        )
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        id_trabajador,
                        tipo_ausencia,
                        fecha_inicio,
                        fecha_fin,
                        observacion
                    ))

        except psycopg.Error:
            return "Error al registrar la ausencia", 500

        return redirect(url_for("jefatura.disponibilidad"))

    # Consultar trabajadores y ausencias
    try:
        with conectar_bd() as conexion:
            with conexion.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        id_trabajador,
                        nombre,
                        apellido
                    FROM trabajadores
                    ORDER BY nombre, apellido;
                """)

                trabajadores = cursor.fetchall()

                cursor.execute("""
                    SELECT
                        ausencias.id_ausencia,
                        trabajadores.nombre,
                        trabajadores.apellido,
                        ausencias.tipo_ausencia,
                        ausencias.fecha_inicio,
                        ausencias.fecha_fin,
                        ausencias.observacion
                    FROM ausencias
                    INNER JOIN trabajadores
                    ON ausencias.id_trabajador = trabajadores.id_trabajador
                    ORDER BY ausencias.fecha_inicio;
                """)

                ausencias = cursor.fetchall()

    except psycopg.Error:
        return "Error al consultar disponibilidad", 500

    session["csrf_token"] = secrets.token_hex(16)

    return render_template(
        "jefatura/disponibilidad.html",
        trabajadores=trabajadores,
        ausencias=ausencias,
        csrf_token=session["csrf_token"]
    )
