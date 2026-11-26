
import os
import re
import secrets

import psycopg
from psycopg import errors
from argon2 import PasswordHasher
from datetime import date
from services.generador_rol import (
    obtener_dias_mes,
    generar_propuesta,
    calcular_cobertura
)
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

@jefatura_bp.route("/planificacion", methods=["GET", "POST"])
def planificacion():

    acceso = acceso_jefatura()

    if acceso is not None:
        return acceso

    hoy = date.today()

    datos = request.form if request.method == "POST" else request.args

    mes = datos.get("mes", hoy.month, type=int)
    anio = datos.get("anio", hoy.year, type=int)

    if not 1 <= mes <= 12 or not 2026 <= anio <= 2100:
        return "Mes o año no válido", 400

    # Validar seguridad

    if request.method == "POST":

        token = request.form.get("csrf_token", "")

        if not token or token != session.get("csrf_token"):
            return "Solicitud no válida", 400

    session.setdefault("csrf_token", secrets.token_hex(16))

    dias = obtener_dias_mes(anio, mes)

    fecha_inicio = dias[0]["fecha"]
    fecha_fin = dias[-1]["fecha"]

    estado_rol = "SIN GUARDAR"

    try:

        with conectar_bd() as conexion:

            with conexion.cursor() as cursor:

                # Consultar trabajadores

                cursor.execute("""
                    SELECT
                        id_trabajador,
                        nombre,
                        apellido,
                        modalidad_turno,
                        id_turno_fijo
                    FROM trabajadores
                    ORDER BY id_trabajador
                """)

                trabajadores = cursor.fetchall()

                # Consultar turnos

                cursor.execute("""
                    SELECT
                        id_turno,
                        codigo_turno
                    FROM turnos
                """)

                turnos = cursor.fetchall()

                turnos_por_codigo = {
                    turno[1]: turno[0]
                    for turno in turnos
                }

                # Consultar ausencias

                cursor.execute("""
                    SELECT
                        id_trabajador,
                        tipo_ausencia,
                        fecha_inicio,
                        fecha_fin
                    FROM ausencias
                    WHERE fecha_inicio <= %s
                    AND fecha_fin >= %s
                """, (fecha_fin, fecha_inicio))

                ausencias = cursor.fetchall()

                # Consultar dotacion minima

                cursor.execute("""
                    SELECT
                        t.codigo_turno,
                        t.nombre_turno,
                        d.cantidad_minima
                    FROM dotacion_turnos d
                    INNER JOIN turnos t
                        ON d.id_turno = t.id_turno
                    ORDER BY t.id_turno
                """)

                dotaciones = cursor.fetchall()

                # GUARDAR BORRADOR

                if request.method == "POST":

                    if not trabajadores:
                        return "No hay trabajadores registrados", 400

                    # Crear rol mensual sin duplicarlo

                    cursor.execute("""
                        INSERT INTO roles_mensuales (
                            mes,
                            anio,
                            estado
                        )
                        VALUES (%s, %s, 'BORRADOR')
                        ON CONFLICT (mes, anio)
                        DO NOTHING
                        RETURNING id_rol_mensual
                    """, (mes, anio))

                    rol_nuevo = cursor.fetchone()

                    # Impedir sobrescribir roles existentes

                    if rol_nuevo is None:

                        return (
                            "El rol de este periodo ya existe. "
                            "No se puede sobrescribir.",
                            409
                        )

                    # Generar propuesta

                    propuesta = generar_propuesta(
                        anio,
                        mes,
                        trabajadores,
                        turnos,
                        ausencias,
                        dotaciones
                    )

                    # Guardar asignaciones

                    for trabajador in propuesta:

                        id_trabajador = trabajador[
                            "id_trabajador"
                        ]

                        for turno in trabajador["turnos"]:

                            codigo = turno["codigo"]
                            fecha = turno["fecha"]

                            # Las ausencias se registran
                            # en su propia tabla

                            if codigo in ("VAC", "LIC", "INA"):
                                continue

                            # Guardar descansos

                            if codigo in ("L", "LS"):

                                id_turno = None

                                estado = (
                                    "LIBRE" if codigo == "L"
                                    else "LS"
                                )

                            # Guardar turnos trabajados

                            else:

                                id_turno = turnos_por_codigo.get(
                                    codigo
                                )

                                if id_turno is None:

                                    raise ValueError(
                                        f"Turno no válido: {codigo}"
                                    )

                                estado = "PROGRAMADO"

                            cursor.execute("""
                                INSERT INTO asignaciones (
                                    id_trabajador,
                                    id_turno,
                                    fecha,
                                    estado
                                )
                                VALUES (%s, %s, %s, %s)
                            """, (
                                id_trabajador,
                                id_turno,
                                fecha,
                                estado
                            ))

                    conexion.commit()

                    return redirect(
                        url_for(
                            "jefatura.planificacion",
                            mes=mes,
                            anio=anio
                        )
                    )

                # CONSULTAR ROL EXISTENTE

                cursor.execute("""
                    SELECT
                        id_rol_mensual,
                        estado
                    FROM roles_mensuales
                    WHERE mes = %s
                    AND anio = %s
                """, (mes, anio))

                rol_guardado = cursor.fetchone()

                # RECUPERAR ROL GUARDADO

                if rol_guardado:

                    estado_rol = rol_guardado[1]

                    cursor.execute("""
                        SELECT
                            a.id_trabajador,
                            a.fecha,
                            a.estado,
                            t.codigo_turno
                        FROM asignaciones a
                        LEFT JOIN turnos t
                            ON a.id_turno = t.id_turno
                        WHERE a.fecha BETWEEN %s AND %s
                    """, (fecha_inicio, fecha_fin))

                    asignaciones = cursor.fetchall()

                    asignaciones_guardadas = {}

                    for asignacion in asignaciones:

                        id_trabajador = asignacion[0]
                        fecha = asignacion[1]
                        estado = asignacion[2]
                        codigo = asignacion[3]

                        if estado == "LIBRE":
                            codigo = "L"

                        elif estado == "LS":
                            codigo = "LS"

                        asignaciones_guardadas[
                            (id_trabajador, fecha)
                        ] = codigo

                    codigos_ausencia = {
                        "VACACIONES": "VAC",
                        "LICENCIA": "LIC",
                        "INASISTENCIA": "INA"
                    }

                    propuesta = []

                    for trabajador in trabajadores:

                        fila = {
                            "id_trabajador": trabajador[0],
                            "nombre": trabajador[1],
                            "apellido": trabajador[2],
                            "turnos": []
                        }

                        for dia in dias:

                            fecha = dia["fecha"]

                            codigo = asignaciones_guardadas.get(
                                (trabajador[0], fecha),
                                "-"
                            )

                            # Mostrar ausencias registradas

                            for ausencia in ausencias:

                                if (
                                    ausencia[0] == trabajador[0]
                                    and ausencia[2] <= fecha <= ausencia[3]
                                ):

                                    codigo = codigos_ausencia[
                                        ausencia[1]
                                    ]

                                    break

                            fila["turnos"].append({
                                "fecha": fecha,
                                "codigo": codigo
                            })

                        propuesta.append(fila)

                # GENERAR PROPUESTA SI NO EXISTE ROL

                else:

                    propuesta = generar_propuesta(
                        anio,
                        mes,
                        trabajadores,
                        turnos,
                        ausencias,
                        dotaciones
                    )

        # Calcular cobertura diaria

        cobertura = calcular_cobertura(
            dias,
            propuesta,
            dotaciones
        )

    except psycopg.Error as error:

        print("Error de planificación:", error)

        return "Error al procesar planificación", 500

    except ValueError as error:

        return str(error), 400

    return render_template(
        "jefatura/planificacion.html",
        mes=mes,
        anio=anio,
        dias=dias,
        propuesta=propuesta,
        cobertura=cobertura,
        estado_rol=estado_rol,
        csrf_token=session["csrf_token"]
    )

@jefatura_bp.route("/editar-asignacion", methods=["POST"])
def editar_asignacion():

    acceso = acceso_jefatura()

    if acceso is not None:
        return acceso

    # Validar seguridad

    token = request.form.get("csrf_token", "")

    if not token or token != session.get("csrf_token"):
        return "Solicitud no válida", 400

    # Recuperar datos

    try:

        id_trabajador = int(
            request.form.get("id_trabajador", "")
        )

        fecha = date.fromisoformat(
            request.form.get("fecha", "")
        )

        codigo = request.form.get("codigo", "")

    except ValueError:

        return "Datos no válidos", 400

    codigos_validos = [
        "24", "66", "11", "180", "7", "L", "LS"
    ]

    if codigo not in codigos_validos:

        return "Código de turno no válido", 400

    try:

        with conectar_bd() as conexion:

            with conexion.cursor() as cursor:

                # Verificar estado del rol mensual

                cursor.execute("""
                    SELECT estado
                    FROM roles_mensuales
                    WHERE mes = %s AND anio = %s
                    FOR UPDATE
                """, (fecha.month, fecha.year))

                rol = cursor.fetchone()

                if not rol or rol[0] != "BORRADOR":

                    return (
                        "Solo se pueden modificar roles en borrador",
                        409
                    )

                # Verificar trabajador y turno fijo

                cursor.execute("""
                    SELECT
                        tr.modalidad_turno,
                        t.codigo_turno
                    FROM trabajadores tr
                    LEFT JOIN turnos t
                        ON tr.id_turno_fijo = t.id_turno
                    WHERE tr.id_trabajador = %s
                    FOR UPDATE OF tr
                """, (id_trabajador,))

                trabajador = cursor.fetchone()

                if not trabajador:

                    return "Trabajador no encontrado", 404

                equivalencias = {
                    "24": "24",
                    "66": "24",
                    "11": "11",
                    "180": "11",
                    "7": "7"
                }

                if (
                    trabajador[0] == "FIJO"
                    and codigo in equivalencias
                    and equivalencias.get(codigo)
                    != equivalencias.get(trabajador[1])
                ):

                    return "No se puede cambiar el turno fijo", 400

                # Verificar ausencias

                cursor.execute("""
                    SELECT id_ausencia
                    FROM ausencias
                    WHERE id_trabajador = %s
                    AND %s BETWEEN fecha_inicio AND fecha_fin
                """, (id_trabajador, fecha))

                if cursor.fetchone():

                    return (
                        "El trabajador tiene una ausencia registrada",
                        400
                    )

                # Determinar turno y estado

                if codigo in ("L", "LS"):

                    id_turno = None

                    estado = (
                        "LIBRE" if codigo == "L" else "LS"
                    )

                else:

                    cursor.execute("""
                        SELECT id_turno
                        FROM turnos
                        WHERE codigo_turno = %s
                    """, (codigo,))

                    turno = cursor.fetchone()

                    if not turno:

                        return "Turno no encontrado", 404

                    id_turno = turno[0]

                    estado = "PROGRAMADO"

                # Actualizar asignacion

                cursor.execute("""
                    INSERT INTO asignaciones (
                        id_trabajador,
                        id_turno,
                        fecha,
                        estado
                    )
                    VALUES (%s, %s, %s, %s)

                    ON CONFLICT (id_trabajador, fecha)

                    DO UPDATE SET
                        id_turno = EXCLUDED.id_turno,
                        estado = EXCLUDED.estado
                """, (
                    id_trabajador,
                    id_turno,
                    fecha,
                    estado
                ))

        return redirect(
            url_for(
                "jefatura.planificacion",
                mes=fecha.month,
                anio=fecha.year
            )
        )

    except psycopg.Error as error:

        print("Error al editar asignación:", error)

        return "Error al modificar asignación", 500

@jefatura_bp.route("/publicar-rol", methods=["POST"])
def publicar_rol():

    acceso = acceso_jefatura()

    if acceso is not None:
        return acceso

    # Validar seguridad

    token = request.form.get("csrf_token", "")

    if not token or token != session.get("csrf_token"):
        return "Solicitud no válida", 400

    # Recuperar periodo

    try:

        mes = int(request.form.get("mes", ""))
        anio = int(request.form.get("anio", ""))

    except ValueError:

        return "Periodo no válido", 400

    if not 1 <= mes <= 12 or not 2026 <= anio <= 2100:

        return "Mes o año no válido", 400

    try:

        with conectar_bd() as conexion:

            with conexion.cursor() as cursor:

                # Verificar estado del rol

                cursor.execute("""
                    SELECT id_rol_mensual, estado
                    FROM roles_mensuales
                    WHERE mes = %s AND anio = %s
                    FOR UPDATE
                """, (mes, anio))

                rol = cursor.fetchone()

                if not rol:

                    return "El rol mensual no existe", 404

                if rol[1] != "BORRADOR":

                    return "El rol ya está publicado", 409

                # Verificar que existan asignaciones

                dias = obtener_dias_mes(anio, mes)

                cursor.execute("""
                    SELECT COUNT(*)
                    FROM asignaciones
                    WHERE fecha BETWEEN %s AND %s
                """, (
                    dias[0]["fecha"],
                    dias[-1]["fecha"]
                ))

                cantidad = cursor.fetchone()[0]

                if cantidad == 0:

                    return "El rol no tiene asignaciones", 400

                # Publicar rol mensual

                cursor.execute("""
                    UPDATE roles_mensuales
                    SET estado = 'PUBLICADO',
                        fecha_publicacion = CURRENT_TIMESTAMP
                    WHERE id_rol_mensual = %s
                    AND estado = 'BORRADOR'
                """, (rol[0],))

        return redirect(
            url_for(
                "jefatura.planificacion",
                mes=mes,
                anio=anio
            )
        )

    except psycopg.Error as error:

        print("Error al publicar rol:", error)

        return "Error al publicar el rol mensual", 500

@jefatura_bp.route("/horas-extras")
def horas_extras():

    acceso = acceso_jefatura()

    if acceso is not None:
        return acceso

    try:

        with conectar_bd() as conexion:

            with conexion.cursor() as cursor:

                # Consultar cupos publicados

                cursor.execute("""
                    SELECT
                        c.id_cupo,
                        c.fecha,
                        c.hora_inicio,
                        c.hora_fin,
                        ca.nombre_cargo,
                        u.correo,
                        c.cantidad_cupos,
                        c.estado,

                        COUNT(p.id_postulacion) FILTER (
                            WHERE p.estado = 'PENDIENTE'
                        ),

                        COUNT(p.id_postulacion) FILTER (
                            WHERE p.estado = 'APROBADA'
                        ),

                        COUNT(p.id_postulacion) FILTER (
                            WHERE p.estado = 'RECHAZADA'
                        ),

                        COUNT(p.id_postulacion) FILTER (
                            WHERE p.estado = 'CANCELADA'
                        )

                    FROM cupos_horas_extras c

                    INNER JOIN cargos ca
                        ON c.id_cargo = ca.id_cargo

                    INNER JOIN usuarios u
                        ON c.id_lider = u.id_usuario

                    LEFT JOIN postulaciones p
                        ON c.id_cupo = p.id_cupo

                    GROUP BY
                        c.id_cupo,
                        ca.nombre_cargo,
                        u.correo

                    ORDER BY c.fecha DESC, c.hora_inicio
                """)

                cupos = cursor.fetchall()

                # Consultar postulaciones

                cursor.execute("""
                    SELECT
                        p.id_postulacion,
                        p.id_cupo,
                        t.nombre,
                        t.apellido,
                        c.fecha,
                        c.hora_inicio,
                        c.hora_fin,
                        p.fecha_postulacion,
                        p.estado,
                        u.correo

                    FROM postulaciones p

                    INNER JOIN trabajadores t
                        ON p.id_trabajador = t.id_trabajador

                    INNER JOIN cupos_horas_extras c
                        ON p.id_cupo = c.id_cupo

                    LEFT JOIN usuarios u
                        ON p.id_lider_resuelve = u.id_usuario

                    ORDER BY p.fecha_postulacion DESC
                """)

                postulaciones = cursor.fetchall()

        # Indicadores generales

        indicadores = {

            "publicados": len(cupos),

            "abiertos": sum(
                1 for cupo in cupos
                if cupo[7] == "ABIERTO"
            ),

            "cerrados": sum(
                1 for cupo in cupos
                if cupo[7] == "CERRADO"
            ),

            "cancelados": sum(
                1 for cupo in cupos
                if cupo[7] == "CANCELADO"
            ),

            "pendientes": sum(
                cupo[8] for cupo in cupos
            ),

            "aprobadas": sum(
                cupo[9] for cupo in cupos
            ),

            "rechazadas": sum(
                cupo[10] for cupo in cupos
            ),

            "postulaciones_canceladas": sum(
                cupo[11] for cupo in cupos
            )
        }

    except psycopg.Error as error:

        print("Error al consultar horas extras:", error)

        return "Error al consultar horas extras", 500

    return render_template(
        "jefatura/horas-extras.html",
        cupos=cupos,
        postulaciones=postulaciones,
        indicadores=indicadores
    )

@jefatura_bp.route("/reportes")
def reportes():

    acceso = acceso_jefatura()

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

    try:

        with conectar_bd() as conexion:

            with conexion.cursor() as cursor:

                # Total de trabajadores

                cursor.execute("""
                    SELECT
                        COUNT(*),
                        COUNT(*) FILTER (
                            WHERE modalidad_turno = 'FIJO'
                        ),
                        COUNT(*) FILTER (
                            WHERE modalidad_turno = 'ROTATIVO'
                        )
                    FROM trabajadores
                """)

                trabajadores = cursor.fetchone()

                # Trabajadores por cargo

                cursor.execute("""
                    SELECT
                        c.nombre_cargo,
                        COUNT(t.id_trabajador)
                    FROM cargos c
                    LEFT JOIN trabajadores t
                        ON c.id_cargo = t.id_cargo
                    GROUP BY c.id_cargo, c.nombre_cargo
                    ORDER BY c.nombre_cargo
                """)

                cargos = cursor.fetchall()

                # Estado del rol mensual

                cursor.execute("""
                    SELECT estado
                    FROM roles_mensuales
                    WHERE mes = %s AND anio = %s
                """, (mes, anio))

                rol = cursor.fetchone()

                estado_rol = rol[0] if rol else "SIN GUARDAR"

                # Asignaciones por turno

                cursor.execute("""
                    SELECT
                        t.codigo_turno,
                        t.nombre_turno,
                        COUNT(a.id_asignacion)
                    FROM turnos t
                    LEFT JOIN asignaciones a
                        ON t.id_turno = a.id_turno
                        AND a.fecha BETWEEN %s AND %s
                        AND a.estado = 'PROGRAMADO'
                        AND NOT EXISTS (
                            SELECT 1
                            FROM ausencias au
                            WHERE au.id_trabajador = a.id_trabajador
                            AND a.fecha BETWEEN
                                au.fecha_inicio AND au.fecha_fin
                        )
                    GROUP BY
                        t.id_turno,
                        t.codigo_turno,
                        t.nombre_turno
                    ORDER BY t.id_turno
                """, (fecha_inicio, fecha_fin))

                turnos = cursor.fetchall()

                # Ausencias del periodo

                cursor.execute("""
                    SELECT
                        COUNT(*) FILTER (
                            WHERE tipo_ausencia = 'VACACIONES'
                        ),
                        COUNT(*) FILTER (
                            WHERE tipo_ausencia = 'LICENCIA'
                        ),
                        COUNT(*) FILTER (
                            WHERE tipo_ausencia = 'INASISTENCIA'
                        )
                    FROM ausencias
                    WHERE fecha_inicio <= %s
                    AND fecha_fin >= %s
                """, (fecha_fin, fecha_inicio))

                ausencias = cursor.fetchone()

                # Cupos de horas extras

                cursor.execute("""
                    SELECT
                        COUNT(*),
                        COUNT(*) FILTER (
                            WHERE estado = 'ABIERTO'
                        ),
                        COUNT(*) FILTER (
                            WHERE estado = 'CERRADO'
                        ),
                        COUNT(*) FILTER (
                            WHERE estado = 'CANCELADO'
                        ),
                        COALESCE(
                            SUM(cantidad_cupos) FILTER (
                                WHERE estado != 'CANCELADO'
                            ), 0
                        )
                    FROM cupos_horas_extras
                    WHERE fecha BETWEEN %s AND %s
                """, (fecha_inicio, fecha_fin))

                cupos = cursor.fetchone()

                # Postulaciones de horas extras

                cursor.execute("""
                    SELECT
                        COUNT(*),
                        COUNT(*) FILTER (
                            WHERE p.estado = 'PENDIENTE'
                        ),
                        COUNT(*) FILTER (
                            WHERE p.estado = 'APROBADA'
                        ),
                        COUNT(*) FILTER (
                            WHERE p.estado = 'RECHAZADA'
                        ),
                        COUNT(*) FILTER (
                            WHERE p.estado = 'CANCELADA'
                        ),
                        COUNT(*) FILTER (
                            WHERE p.estado = 'APROBADA'
                            AND c.estado != 'CANCELADO'
                        )
                    FROM postulaciones p
                    INNER JOIN cupos_horas_extras c
                        ON p.id_cupo = c.id_cupo
                    WHERE c.fecha BETWEEN %s AND %s
                """, (fecha_inicio, fecha_fin))

                postulaciones = cursor.fetchone()

        # Porcentaje de cobertura de horas extras

        cobertura_extras = None

        if cupos[4] > 0:

            cobertura_extras = round(
                postulaciones[5] / cupos[4] * 100, 2
            )

    except psycopg.Error as error:

        print("Error al generar reportes:", error)

        return "Error al generar reportes", 500

    return render_template(
        "jefatura/reportes.html",
        mes=mes,
        anio=anio,
        trabajadores=trabajadores,
        cargos=cargos,
        estado_rol=estado_rol,
        turnos=turnos,
        ausencias=ausencias,
        cupos=cupos,
        postulaciones=postulaciones,
        cobertura_extras=cobertura_extras
    )