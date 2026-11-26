import calendar
from datetime import date
from functools import lru_cache



# GENERAR CALENDARIO MENSUAL


def obtener_dias_mes(anio, mes):

    cantidad_dias = calendar.monthrange(anio, mes)[1]

    nombres_dias = [
        "LU", "MA", "MI", "JU", "VI", "SA", "DO"
    ]

    dias = []

    for numero in range(1, cantidad_dias + 1):

        fecha = date(anio, mes, numero)

        dias.append({
            "numero": numero,
            "fecha": fecha,
            "nombre": nombres_dias[fecha.weekday()],
            "fin_semana": fecha.weekday() >= 5
        })

    return dias



# GENERAR PROPUESTA DE TURNOS


def generar_propuesta(
    anio, mes, trabajadores, turnos, ausencias,
    dotaciones=None
):

    dias = obtener_dias_mes(anio, mes)

    propuesta = []

    rotacion = ["24", "11", "7"]

    equivalencias = {
        "24": "24",
        "66": "24",
        "11": "11",
        "180": "11",
        "7": "7"
    }

    turnos_por_id = {
        turno[0]: turno[1]
        for turno in turnos
    }

    codigos_ausencia = {
        "VACACIONES": "VAC",
        "LICENCIA": "LIC",
        "INASISTENCIA": "INA"
    }

    minimos = {
        codigo: minimo
        for codigo, nombre, minimo in (dotaciones or [])
    }

    cobertura_diaria = [
        {"24": 0, "11": 0, "7": 0}
        for dia in dias
    ]

    trabajadores_ordenados = sorted(
        trabajadores,
        key=lambda trabajador: trabajador[3] != "FIJO"
    )

    for indice, trabajador in enumerate(trabajadores_ordenados):

        id_trabajador = trabajador[0]
        nombre = trabajador[1]
        apellido = trabajador[2]
        modalidad = trabajador[3]
        id_turno_fijo = trabajador[4]

        ausencias_trabajador = {}

        for dia in dias:

            fecha = dia["fecha"]

            for ausencia in ausencias:

                if (
                    ausencia[0] == id_trabajador
                    and ausencia[2] <= fecha <= ausencia[3]
                ):

                    ausencias_trabajador[fecha] = (
                        codigos_ausencia[ausencia[1]]
                    )

                    break

        # Seleccionar turno inicial

        if modalidad == "FIJO":

            turno_inicial = turnos_por_id.get(id_turno_fijo)

            if turno_inicial not in equivalencias:

                raise ValueError(
                    f"{nombre} {apellido} no tiene turno fijo válido"
                )

        else:

            preferencia = rotacion[indice % 3]

            turno_inicial = max(
                rotacion,
                key=lambda turno: (
                    max(
                        0,
                        minimos.get(turno, 0)
                        - cobertura_diaria[0][turno]
                    ),
                    turno == preferencia
                )
            )

        # Domingos disponibles sin ausencias

        domingos = [
            dia["fecha"]
            for dia in dias
            if dia["fecha"].weekday() == 6
            and dia["fecha"] not in ausencias_trabajador
        ]

        objetivo_domingos = min(2, len(domingos))

        domingos_preferidos = set()

        if domingos:

            domingos_preferidos.add(
                domingos[indice % len(domingos)]
            )

            domingos_preferidos.add(
                domingos[(indice + 2) % len(domingos)]
            )

        # Buscar un calendario compatible

        @lru_cache(maxsize=None)
        def buscar(
            posicion,
            turno_actual,
            consecutivos,
            descansos,
            anterior,
            domingos_libres,
            dias_ciclo
        ):

            # Final del mes

            if posicion == len(dias):

                if domingos_libres == objetivo_domingos:
                    return ()

                return None

            fecha = dias[posicion]["fecha"]

            es_domingo = fecha.weekday() == 6

            # Respetar ausencias

            if fecha in ausencias_trabajador:

                codigo = ausencias_trabajador[fecha]

                resto = buscar(
                    posicion + 1,
                    turno_actual,
                    0,
                    0,
                    codigo,
                    domingos_libres,
                    dias_ciclo
                )

                if resto is not None:
                    return (codigo,) + resto

                return None

            # Determinar opciones de descanso y trabajo

            if consecutivos >= 6:

                opciones = ["descansar"]

            elif anterior == "LS":

                opciones = ["descansar"]

            elif fecha in domingos_preferidos:

                opciones = ["descansar", "trabajar"]

            elif consecutivos >= 5:

                opciones = ["descansar", "trabajar"]

            elif descansos == 1:

                opciones = ["descansar", "trabajar"]

            elif (
                consecutivos >= 3
                and (fecha.toordinal() + indice) % 7 == 5
            ):

                opciones = ["descansar", "trabajar"]

            else:

                opciones = ["trabajar", "descansar"]

            for opcion in opciones:

                
                # DESCANSAR
                

                if opcion == "descansar":

                    codigo = "LS" if anterior == "7" else "L"

                    # LS no cuenta como domingo completo

                    if es_domingo and codigo == "LS":
                        continue

                    nuevos_domingos = domingos_libres

                    if es_domingo:

                        nuevos_domingos += 1

                    if nuevos_domingos > objetivo_domingos:
                        continue

                    resto = buscar(
                        posicion + 1,
                        turno_actual,
                        0,
                        min(descansos + 1, 2),
                        codigo,
                        nuevos_domingos,
                        dias_ciclo
                    )

                    if resto is not None:

                        return (codigo,) + resto

                
                # TRABAJAR
                

                else:

                    nuevo_turno = turno_actual

                    nuevo_ciclo = dias_ciclo

                    # Rotar solamente despues del descanso

                    if (
                        modalidad == "ROTATIVO"
                        and descansos >= 1
                        and dias_ciclo > 0
                    ):

                        indice_turno = rotacion.index(
                            turno_actual
                        )

                        nuevo_turno = rotacion[
                            (indice_turno + 1) % 3
                        ]

                        nuevo_ciclo = 0

                    codigo = nuevo_turno

                    # Turnos reducidos

                    if nuevo_ciclo in (1, 3, 4):

                        if codigo == "24":

                            codigo = "66"

                        elif codigo == "11":

                            codigo = "180"

                    # Evitar cambio directo despues de noche

                    if (
                        anterior == "7"
                        and codigo != "7"
                    ):

                        continue

                    # Evitar cambio directo de tarde a mañana

                    if (
                        anterior in ("11", "180")
                        and codigo in ("24", "66")
                    ):

                        continue

                    resto = buscar(
                        posicion + 1,
                        nuevo_turno,
                        consecutivos + 1,
                        0,
                        codigo,
                        domingos_libres,
                        nuevo_ciclo + 1
                    )

                    if resto is not None:

                        return (codigo,) + resto

            return None

        calendario = buscar(
            0,
            turno_inicial,
            indice % 5,
            0,
            None,
            0,
            0
        )

        if calendario is None:

            raise ValueError(
                f"No se encontró un rol compatible para "
                f"{nombre} {apellido}. "
                f"Se requiere revisión de Jefatura."
            )

        fila = {
            "id_trabajador": id_trabajador,
            "nombre": nombre,
            "apellido": apellido,
            "turnos": []
        }

        for posicion, codigo in enumerate(calendario):

            fila["turnos"].append({
                "fecha": dias[posicion]["fecha"],
                "codigo": codigo
            })

            turno_principal = equivalencias.get(codigo)

            if turno_principal:

                cobertura_diaria[posicion][turno_principal] += 1

        propuesta.append(fila)

        buscar.cache_clear()

    return propuesta



# CALCULAR COBERTURA Y DOTACION


def calcular_cobertura(dias, propuesta, dotaciones):

    cobertura = []

    equivalencias = {
        "24": "24",
        "66": "24",
        "11": "11",
        "180": "11",
        "7": "7"
    }

    for indice, dia in enumerate(dias):

        cantidades = {
            "24": 0,
            "11": 0,
            "7": 0
        }

        for trabajador in propuesta:

            codigo = trabajador["turnos"][indice]["codigo"]

            turno_principal = equivalencias.get(codigo)

            if turno_principal:

                cantidades[turno_principal] += 1

        detalle = {
            "fecha": dia["fecha"],
            "turnos": []
        }

        for codigo, nombre, minimo in dotaciones:

            asignados = cantidades.get(codigo, 0)

            faltantes = max(0, minimo - asignados)

            detalle["turnos"].append({
                "codigo": codigo,
                "nombre": nombre,
                "minimo": minimo,
                "asignados": asignados,
                "faltantes": faltantes,
                "cumple": asignados >= minimo
            })

        cobertura.append(detalle)

    return cobertura