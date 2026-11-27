import os
import psycopg
import secrets

from datetime import date
from flask import abort
from flask import Blueprint, render_template, session, redirect, url_for, request
from services.generador_rol import obtener_dias_mes

trabajador_bp = Blueprint("trabajador", __name__)


def conectar_bd():

    return psycopg.connect(
        host=os.environ.get("DB_HOST"),
        port=os.environ.get("DB_PORT"),
        dbname=os.environ.get("DB_NAME"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD")
    )


def acceso_trabajador():

    if "usuario_id" not in session:
        return redirect(url_for("inicio"))

    if session.get("id_rol") != 3:
        return "Acceso denegado", 403

    return None


@trabajador_bp.route("/mi-rol")
def mi_rol():

    acceso = acceso_trabajador()

    if acceso is not None:
        return acceso

    hoy = date.today()

    mes = request.args.get("mes", hoy.month, type=int)
    anio = request.args.get("anio", hoy.year, type=int)

    if not 1 <= mes <= 12 or not 2026 <= anio <= 2100:
        return "Periodo no válido", 400

    dias = obtener_dias_mes(anio, mes)

    fecha_inicio = dias[0]["fecha"]
    fecha_fin = dias[-1]["fecha"]

    rol_publicado = False
    calendario = []

    try:

        with conectar_bd() as conexion:

            with conexion.cursor() as cursor:

                # Identificar al trabajador conectado

                cursor.execute("""
                    SELECT id_trabajador, nombre, apellido
                    FROM trabajadores
                    WHERE id_usuario = %s
                """, (session["usuario_id"],))

                trabajador = cursor.fetchone()

                if trabajador is None:
                    return "Trabajador no registrado", 404

                id_trabajador = trabajador[0]

                # Verificar que el rol esté publicado

                cursor.execute("""
                    SELECT id_rol_mensual
                    FROM roles_mensuales
                    WHERE mes = %s
                    AND anio = %s
                    AND estado = 'PUBLICADO'
                """, (mes, anio))

                rol = cursor.fetchone()

                if rol is not None:

                    rol_publicado = True

                    # Consultar asignaciones individuales

                    cursor.execute("""
                        SELECT
                            a.fecha,
                            a.estado,
                            t.codigo_turno,
                            t.nombre_turno,
                            t.hora_inicio,
                            t.hora_fin,
                            t.termina_dia_siguiente
                        FROM asignaciones a
                        LEFT JOIN turnos t
                            ON a.id_turno = t.id_turno
                        WHERE a.id_trabajador = %s
                        AND a.fecha BETWEEN %s AND %s
                        ORDER BY a.fecha
                    """, (
                        id_trabajador,
                        fecha_inicio,
                        fecha_fin
                    ))

                    asignaciones = {
                        fila[0]: fila
                        for fila in cursor.fetchall()
                    }

                    # Consultar ausencias individuales

                    cursor.execute("""
                        SELECT
                            tipo_ausencia,
                            fecha_inicio,
                            fecha_fin
                        FROM ausencias
                        WHERE id_trabajador = %s
                        AND fecha_inicio <= %s
                        AND fecha_fin >= %s
                    """, (
                        id_trabajador,
                        fecha_fin,
                        fecha_inicio
                    ))

                    ausencias = cursor.fetchall()

                    for dia in dias:

                        fecha = dia["fecha"]

                        registro = {
                            "fecha": fecha,
                            "dia": dia["nombre"],
                            "codigo": "-",
                            "nombre": "Sin asignación",
                            "inicio": "-",
                            "fin": "-"
                        }

                        asignacion = asignaciones.get(fecha)

                        if asignacion:

                            if asignacion[1] == "LIBRE":

                                registro["codigo"] = "L"
                                registro["nombre"] = "Libre"

                            elif asignacion[1] == "LS":

                                registro["codigo"] = "LS"
                                registro["nombre"] = "Saliente libre"

                            else:

                                registro["codigo"] = asignacion[2]
                                registro["nombre"] = asignacion[3]

                                registro["inicio"] = (
                                    asignacion[4].strftime("%H:%M")
                                )

                                registro["fin"] = (
                                    asignacion[5].strftime("%H:%M")
                                )

                                if asignacion[6]:
                                    registro["fin"] += " (+1 día)"

                        # Las ausencias tienen prioridad

                        for ausencia in ausencias:

                            if ausencia[1] <= fecha <= ausencia[2]:

                                codigos = {
                                    "VACACIONES": "VAC",
                                    "LICENCIA": "LIC",
                                    "INASISTENCIA": "INA"
                                }

                                registro["codigo"] = codigos[ausencia[0]]
                                registro["nombre"] = ausencia[0]
                                registro["inicio"] = "-"
                                registro["fin"] = "-"

                                break

                        calendario.append(registro)

    except psycopg.Error as error:

        print("Error al consultar rol individual:", error)

        return "Error al consultar el rol mensual", 500

    return render_template(
        "trabajador/mi-rol.html",
        trabajador=trabajador,
        mes=mes,
        anio=anio,
        calendario=calendario,
        rol_publicado=rol_publicado
    )

@trabajador_bp.route("/horas-extras")
def horas_extras():

    acceso = acceso_trabajador()

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
                    (
                        SELECT COUNT(*)
                        FROM postulaciones p
                        WHERE p.id_cupo = c.id_cupo
                        AND p.estado = 'APROBADA'
                    ) AS aprobadas

                FROM cupos_horas_extras c

                INNER JOIN cargos ca
                    ON c.id_cargo = ca.id_cargo

                INNER JOIN trabajadores t
                    ON t.id_cargo = c.id_cargo

                WHERE t.id_usuario = %s
                AND c.estado = 'ABIERTO'
                AND c.fecha + c.hora_inicio > LOCALTIMESTAMP

                AND NOT EXISTS (
                    SELECT 1
                    FROM postulaciones p
                    WHERE p.id_cupo = c.id_cupo
                    AND p.id_trabajador = t.id_trabajador
                )

                AND NOT EXISTS (
                    SELECT 1
                    FROM ausencias a
                    WHERE a.id_trabajador = t.id_trabajador
                    AND c.fecha BETWEEN
                        a.fecha_inicio AND a.fecha_fin
                )

                ORDER BY c.fecha, c.hora_inicio

            """, (session["usuario_id"],))

            cupos = cursor.fetchall()

    cupos = [
        cupo for cupo in cupos
        if cupo[5] > cupo[6]
    ]

    return render_template(
        "trabajador/horas-extras.html",
        cupos=cupos,
        csrf_token=session["csrf_token"]
    )


@trabajador_bp.route("/postular", methods=["POST"])
def postular():

    acceso = acceso_trabajador()

    if acceso is not None:
        return acceso

    token = request.form.get("csrf_token")

    if not token or token != session.get("csrf_token"):
        abort(400)

    id_cupo = request.form.get("id_cupo", type=int)

    if not id_cupo:
        return "Cupo no válido", 400

    with conectar_bd() as conexion:

        with conexion.cursor() as cursor:

            cursor.execute("""
                SELECT id_trabajador, id_cargo
                FROM trabajadores
                WHERE id_usuario = %s
                FOR UPDATE
            """, (session["usuario_id"],))

            trabajador = cursor.fetchone()

            if trabajador is None:
                return "Trabajador no registrado", 404

            cursor.execute("""
                SELECT id_cargo, fecha, cantidad_cupos
                FROM cupos_horas_extras
                WHERE id_cupo = %s
                AND estado = 'ABIERTO'
                AND fecha + hora_inicio > LOCALTIMESTAMP
                FOR UPDATE
            """, (id_cupo,))

            cupo = cursor.fetchone()

            if cupo is None:
                return "Cupo no disponible", 400

            if trabajador[1] != cupo[0]:
                return "Cargo incompatible", 400

            cursor.execute("""
                SELECT 1
                FROM ausencias
                WHERE id_trabajador = %s
                AND %s BETWEEN fecha_inicio AND fecha_fin
            """, (trabajador[0], cupo[1]))

            if cursor.fetchone():
                return "No estás disponible para esta fecha", 400

            cursor.execute("""
                SELECT COUNT(*)
                FROM postulaciones
                WHERE id_cupo = %s
                AND estado = 'APROBADA'
            """, (id_cupo,))

            aprobadas = cursor.fetchone()[0]

            if aprobadas >= cupo[2]:
                return "No quedan vacantes disponibles", 400

            cursor.execute("""
                INSERT INTO postulaciones (
                    id_cupo,
                    id_trabajador,
                    estado
                )
                VALUES (%s, %s, 'PENDIENTE')
                ON CONFLICT (id_cupo, id_trabajador)
                DO NOTHING
                RETURNING id_postulacion
            """, (id_cupo, trabajador[0]))

            if cursor.fetchone() is None:
                return "Ya tienes una postulación para este cupo", 409

        conexion.commit()

    return redirect(url_for("trabajador.mis_postulaciones"))


@trabajador_bp.route("/mis-postulaciones")
def mis_postulaciones():

    acceso = acceso_trabajador()

    if acceso is not None:
        return acceso

    session.setdefault("csrf_token", secrets.token_hex(32))

    with conectar_bd() as conexion:

        with conexion.cursor() as cursor:

            cursor.execute("""
                SELECT
                    p.id_postulacion,
                    c.fecha,
                    c.hora_inicio,
                    c.hora_fin,
                    ca.nombre_cargo,
                    p.fecha_postulacion,
                    p.estado,
                    c.estado

                FROM postulaciones p

                INNER JOIN trabajadores t
                    ON p.id_trabajador = t.id_trabajador

                INNER JOIN cupos_horas_extras c
                    ON p.id_cupo = c.id_cupo

                INNER JOIN cargos ca
                    ON c.id_cargo = ca.id_cargo

                WHERE t.id_usuario = %s

                ORDER BY p.fecha_postulacion DESC

            """, (session["usuario_id"],))

            postulaciones = cursor.fetchall()

    return render_template(
        "trabajador/mis-postulaciones.html",
        postulaciones=postulaciones,
        csrf_token=session["csrf_token"]
    )


@trabajador_bp.route("/cancelar-postulacion", methods=["POST"])
def cancelar_postulacion():

    acceso = acceso_trabajador()

    if acceso is not None:
        return acceso

    token = request.form.get("csrf_token")

    if not token or token != session.get("csrf_token"):
        abort(400)

    id_postulacion = request.form.get(
        "id_postulacion", type=int
    )

    if not id_postulacion:
        return "Postulación no válida", 400

    with conectar_bd() as conexion:

        with conexion.cursor() as cursor:

            cursor.execute("""
                UPDATE postulaciones p
                SET estado = 'CANCELADA'

                FROM trabajadores t

                WHERE p.id_trabajador = t.id_trabajador
                AND t.id_usuario = %s
                AND p.id_postulacion = %s
                AND p.estado = 'PENDIENTE'

                RETURNING p.id_postulacion

            """, (
                session["usuario_id"],
                id_postulacion
            ))

            if cursor.fetchone() is None:
                return "No puedes cancelar esta postulación", 400

        conexion.commit()

    return redirect(url_for("trabajador.mis_postulaciones"))