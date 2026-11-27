import os
import secrets
import psycopg

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import (
    Blueprint, render_template, session,
    redirect, url_for, request, abort
)

lider_bp = Blueprint("lider", __name__)


def conectar_bd():

    return psycopg.connect(
        host=os.environ.get("DB_HOST"),
        port=os.environ.get("DB_PORT"),
        dbname=os.environ.get("DB_NAME"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD")
    )


def acceso_lider():

    if "usuario_id" not in session:
        return redirect(url_for("inicio"))

    if session.get("id_rol") != 2:
        return "Acceso denegado", 403

    return None


def validar_csrf():

    token = request.form.get("csrf_token")

    if not token or token != session.get("csrf_token"):
        abort(400)


# CONSULTAR CUPOS PUBLICADOS


@lider_bp.route("/horas-extras")
def horas_extras():

    acceso = acceso_lider()

    if acceso is not None:
        return acceso

    session.setdefault("csrf_token", secrets.token_hex(32))

    with conectar_bd() as conexion:

        with conexion.cursor() as cursor:

            cursor.execute("""
                SELECT
                    c.id_cupo,
                    c.fecha,
                    c.hora_inicio,
                    c.hora_fin,
                    ca.nombre_cargo,
                    c.cantidad_cupos,
                    c.estado,

                    COUNT(p.id_postulacion) FILTER (
                        WHERE p.estado = 'PENDIENTE'
                    ),

                    COUNT(p.id_postulacion) FILTER (
                        WHERE p.estado = 'APROBADA'
                    )

                FROM cupos_horas_extras c

                INNER JOIN cargos ca
                    ON c.id_cargo = ca.id_cargo

                LEFT JOIN postulaciones p
                    ON c.id_cupo = p.id_cupo

                WHERE c.id_lider = %s

                GROUP BY c.id_cupo, ca.nombre_cargo

                ORDER BY c.fecha DESC, c.hora_inicio

            """, (session["usuario_id"],))

            cupos = cursor.fetchall()

    return render_template(
        "lider/horas-extras.html",
        cupos=cupos,
        csrf_token=session["csrf_token"]
    )


# PUBLICAR CUPOS


@lider_bp.route("/publicar-cupo", methods=["GET", "POST"])
def publicar_cupo():

    acceso = acceso_lider()

    if acceso is not None:
        return acceso

    session.setdefault("csrf_token", secrets.token_hex(32))

    with conectar_bd() as conexion:

        with conexion.cursor() as cursor:

            if request.method == "POST":

                validar_csrf()

                id_cargo = request.form.get("id_cargo", type=int)
                cantidad = request.form.get("cantidad", type=int)

                try:

                    fecha = datetime.strptime(
                        request.form.get("fecha", ""),
                        "%Y-%m-%d"
                    ).date()

                    turno = request.form.get("turno")

                    horarios = {
                        "MANANA": "06:00",
                        "TARDE": "14:00",
                        "NOCHE": "22:00"
                    }

                    if turno not in horarios:
                        return "Turno no válido", 400

                    hora_inicio = datetime.strptime(
                        horarios[turno],
                        "%H:%M"
                    ).time()                

                    hora_fin = datetime.strptime(
                        request.form.get("hora_fin", ""),
                        "%H:%M"
                    ).time()

                except ValueError:

                    return "Fecha u horario no válido", 400

                if not id_cargo or not cantidad or cantidad < 1:
                    return "Datos del cupo no válidos", 400

                inicio = datetime.combine(fecha, hora_inicio)
                fin = datetime.combine(fecha, hora_fin)

                if hora_inicio == hora_fin:
                    return "Las horas no pueden ser iguales", 400

                if fin < inicio:
                    fin += timedelta(days=1)

                ahora = datetime.now(
                    ZoneInfo("America/Santiago")
                ).replace(tzinfo=None)

                if inicio <= ahora:
                    return "Debes seleccionar un horario futuro", 400

                cursor.execute("""
                    SELECT id_cargo
                    FROM cargos
                    WHERE id_cargo = %s
                """, (id_cargo,))

                if cursor.fetchone() is None:
                    return "Cargo no válido", 400

                cursor.execute("""
                    INSERT INTO cupos_horas_extras (
                        id_lider,
                        id_cargo,
                        fecha,
                        hora_inicio,
                        hora_fin,
                        cantidad_cupos,
                        estado
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, 'ABIERTO'
                    )
                """, (
                    session["usuario_id"],
                    id_cargo,
                    fecha,
                    hora_inicio,
                    hora_fin,
                    cantidad
                ))

                conexion.commit()

                return redirect(
                    url_for("lider.horas_extras")
                )

            cursor.execute("""
                SELECT id_cargo, nombre_cargo
                FROM cargos
                ORDER BY nombre_cargo
            """)

            cargos = cursor.fetchall()

    return render_template(
        "lider/publicar-cupo.html",
        cargos=cargos,
        csrf_token=session["csrf_token"]
    )


# CONSULTAR POSTULACIONES


@lider_bp.route("/postulaciones")
def postulaciones():

    acceso = acceso_lider()

    if acceso is not None:
        return acceso

    session.setdefault("csrf_token", secrets.token_hex(32))

    with conectar_bd() as conexion:

        with conexion.cursor() as cursor:

            cursor.execute("""
                SELECT
                    p.id_postulacion,
                    c.id_cupo,
                    t.nombre,
                    t.apellido,
                    ca.nombre_cargo,
                    c.fecha,
                    c.hora_inicio,
                    c.hora_fin,
                    p.fecha_postulacion,
                    p.estado,
                    c.estado

                FROM postulaciones p

                INNER JOIN trabajadores t
                    ON p.id_trabajador = t.id_trabajador

                INNER JOIN cupos_horas_extras c
                    ON p.id_cupo = c.id_cupo

                INNER JOIN cargos ca
                    ON t.id_cargo = ca.id_cargo

                WHERE c.id_lider = %s

                ORDER BY p.fecha_postulacion ASC

            """, (session["usuario_id"],))

            postulaciones = cursor.fetchall()

    return render_template(
        "lider/postulaciones.html",
        postulaciones=postulaciones,
        csrf_token=session["csrf_token"]
    )


# APROBAR O RECHAZAR POSTULACIONES


@lider_bp.route("/resolver-postulacion", methods=["POST"])
def resolver_postulacion():

    acceso = acceso_lider()

    if acceso is not None:
        return acceso

    validar_csrf()

    id_postulacion = request.form.get(
        "id_postulacion", type=int
    )

    decision = request.form.get("decision")

    if not id_postulacion:
        return "Postulación no válida", 400

    if decision not in ("APROBADA", "RECHAZADA"):
        return "Decisión no válida", 400

    with conectar_bd() as conexion:

        with conexion.cursor() as cursor:

            # Identificar al trabajador y al cupo

            cursor.execute("""
                SELECT p.id_trabajador, p.id_cupo
                FROM postulaciones p
                INNER JOIN cupos_horas_extras c
                    ON p.id_cupo = c.id_cupo
                WHERE p.id_postulacion = %s
                AND c.id_lider = %s
            """, (
                id_postulacion,
                session["usuario_id"]
            ))

            referencia = cursor.fetchone()

            if referencia is None:
                return "Postulación no encontrada", 404

            id_trabajador, id_cupo = referencia

            # Bloquear trabajador y cupo

            cursor.execute("""
                SELECT id_cargo
                FROM trabajadores
                WHERE id_trabajador = %s
                FOR UPDATE
            """, (id_trabajador,))

            trabajador = cursor.fetchone()

            cursor.execute("""
                SELECT
                    id_cargo,
                    fecha,
                    hora_inicio,
                    hora_fin,
                    cantidad_cupos,
                    estado
                FROM cupos_horas_extras
                WHERE id_cupo = %s
                AND id_lider = %s
                FOR UPDATE
            """, (
                id_cupo,
                session["usuario_id"]
            ))

            cupo = cursor.fetchone()

            if cupo is None:
                return "Cupo no encontrado", 404

            cursor.execute("""
                SELECT estado
                FROM postulaciones
                WHERE id_postulacion = %s
                FOR UPDATE
            """, (id_postulacion,))

            postulacion = cursor.fetchone()

            if not postulacion or postulacion[0] != "PENDIENTE":
                return "La postulación ya fue resuelta", 400

            if cupo[5] == "CANCELADO":
                return "El cupo está cancelado", 400

            if decision == "APROBADA":

                if cupo[5] != "ABIERTO":
                    return "El cupo no está abierto", 400

                if trabajador[0] != cupo[0]:
                    return "Cargo incompatible", 400

                inicio = datetime.combine(cupo[1], cupo[2])
                fin = datetime.combine(cupo[1], cupo[3])

                if fin <= inicio:
                    fin += timedelta(days=1)

                ahora = datetime.now(
                    ZoneInfo("America/Santiago")
                ).replace(tzinfo=None)

                if inicio <= ahora:
                    return "El horario del cupo ya comenzó", 400

                # Verificar ausencias

                cursor.execute("""
                    SELECT 1
                    FROM ausencias
                    WHERE id_trabajador = %s
                    AND fecha_inicio <= %s
                    AND fecha_fin >= %s
                """, (
                    id_trabajador,
                    (fin - timedelta(microseconds=1)).date(),
                    inicio.date()
                ))

                if cursor.fetchone():
                    return "El trabajador presenta una ausencia", 400

                # Verificar superposición con turnos ordinarios

                cursor.execute("""
                    SELECT 1
                    FROM asignaciones a
                    INNER JOIN turnos t
                        ON a.id_turno = t.id_turno
                    WHERE a.id_trabajador = %s
                    AND a.estado = 'PROGRAMADO'

                    AND a.fecha + t.hora_inicio < %s

                    AND a.fecha + t.hora_fin +
                        CASE
                            WHEN t.termina_dia_siguiente
                            THEN INTERVAL '1 day'
                            ELSE INTERVAL '0 day'
                        END > %s

                """, (
                    id_trabajador,
                    fin,
                    inicio
                ))

                if cursor.fetchone():
                    return "El cupo coincide con un turno ordinario", 400

                # Verificar otras horas extras aprobadas

                cursor.execute("""
                    SELECT 1
                    FROM postulaciones p
                    INNER JOIN cupos_horas_extras c
                        ON p.id_cupo = c.id_cupo
                    WHERE p.id_trabajador = %s
                    AND p.estado = 'APROBADA'
                    AND c.estado != 'CANCELADO'

                    AND c.fecha + c.hora_inicio < %s

                    AND c.fecha + c.hora_fin +
                        CASE
                            WHEN c.hora_fin <= c.hora_inicio
                            THEN INTERVAL '1 day'
                            ELSE INTERVAL '0 day'
                        END > %s

                """, (
                    id_trabajador,
                    fin,
                    inicio
                ))

                if cursor.fetchone():
                    return "Existe otra hora extra en ese horario", 400

                # Verificar vacantes

                cursor.execute("""
                    SELECT COUNT(*)
                    FROM postulaciones
                    WHERE id_cupo = %s
                    AND estado = 'APROBADA'
                """, (id_cupo,))

                aprobadas = cursor.fetchone()[0]

                if aprobadas >= cupo[4]:
                    return "No quedan vacantes disponibles", 400

            # Actualizar postulación

            cursor.execute("""
                UPDATE postulaciones
                SET estado = %s,
                    id_lider_resuelve = %s
                WHERE id_postulacion = %s
            """, (
                decision,
                session["usuario_id"],
                id_postulacion
            ))

            # Cerrar automáticamente si se llena el cupo

            if decision == "APROBADA":

                if aprobadas + 1 >= cupo[4]:

                    cursor.execute("""
                        UPDATE cupos_horas_extras
                        SET estado = 'CERRADO'
                        WHERE id_cupo = %s
                    """, (id_cupo,))

                    cursor.execute("""
                        UPDATE postulaciones
                        SET estado = 'RECHAZADA',
                            id_lider_resuelve = %s
                        WHERE id_cupo = %s
                        AND estado = 'PENDIENTE'
                    """, (
                        session["usuario_id"],
                        id_cupo
                    ))

        conexion.commit()

    return redirect(url_for("lider.postulaciones"))


# CANCELAR CUPO


@lider_bp.route("/cancelar-cupo", methods=["POST"])
def cancelar_cupo():

    acceso = acceso_lider()

    if acceso is not None:
        return acceso

    validar_csrf()

    id_cupo = request.form.get("id_cupo", type=int)

    if not id_cupo:
        return "Cupo no válido", 400

    with conectar_bd() as conexion:

        with conexion.cursor() as cursor:

            cursor.execute("""
                SELECT fecha, hora_inicio, estado
                FROM cupos_horas_extras
                WHERE id_cupo = %s
                AND id_lider = %s
                FOR UPDATE
            """, (
                id_cupo,
                session["usuario_id"]
            ))

            cupo = cursor.fetchone()

            if cupo is None:
                return "Cupo no encontrado", 404

            if cupo[2] == "CANCELADO":
                return "El cupo ya está cancelado", 400

            inicio = datetime.combine(cupo[0], cupo[1])

            ahora = datetime.now(
                ZoneInfo("America/Santiago")
            ).replace(tzinfo=None)

            if inicio <= ahora:
                return "No puedes cancelar un cupo iniciado", 400

            cursor.execute("""
                UPDATE cupos_horas_extras
                SET estado = 'CANCELADO'
                WHERE id_cupo = %s
            """, (id_cupo,))

            cursor.execute("""
                UPDATE postulaciones
                SET estado = 'CANCELADA',
                    id_lider_resuelve = %s
                WHERE id_cupo = %s
                AND estado IN ('PENDIENTE', 'APROBADA')
            """, (
                session["usuario_id"],
                id_cupo
            ))

        conexion.commit()

    return redirect(url_for("lider.horas_extras"))