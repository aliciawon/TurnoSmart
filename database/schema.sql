CREATE TABLE roles (
id_rol INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
nombre_rol VARCHAR(30) NOT NULL UNIQUE
);
CREATE TABLE usuarios (
id_usuario INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
nombre VARCHAR(100) NOT NULL,
correo VARCHAR(150) NOT NULL UNIQUE,
password_hash VARCHAR(255) NOT NULL,
id_rol INTEGER NOT NULL REFERENCES roles (id_rol)
);
CREATE TABLE cargos (
id_cargo INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
nombre_cargo VARCHAR (50) NOT NULL UNIQUE
);
CREATE TABLE trabajadores (
id_usuario INTEGER UNIQUE REFERENCES usuarios(id_usuario),
id_trabajador INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
rut varchar(12) NOT NULL UNIQUE,
nombre VARCHAR(20) NOT NULL,
apellido VARCHAR(20) NOT NULL,
modalidad_turno VARCHAR(20) NOT NULL CHECK (modalidad_turno IN ('FIJO', 'ROTATIVO')),
id_cargo INTEGER NOT NULL REFERENCES cargos(id_cargo)
);
CREATE TABLE turnos (
ID_turno INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
codigo_turno VARCHAR(20) NOT NULL UNIQUE, 
nombre_turno VARCHAR(30) NOT NULL,
hora_inicio TIME NOT NULL,
hora_fin TIME NOT NULL,
termina_dia_siguiente BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE asignaciones (
id_asignacion INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
id_trabajador INTEGER NOT NULL REFERENCES trabajadores(id_trabajador),
id_turno INTEGER REFERENCES turnos(id_turno),
fecha DATE NOT NULL,
estado VARCHAR(20) NOT NULL CHECK (
(estado = 'PROGRAMADO' AND id_turno IS NOT NULL)
OR
(estado IN ('LIBRE', 'LS') AND id_turno IS NULL)
)
);
CREATE TABLE ausencias(
id_ausencia INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
id_trabajador INTEGER NOT NULL REFERENCES trabajadores(id_trabajador),
tipo_ausencia VARCHAR(30) NOT NULL CHECK (tipo_ausencia IN ('VACACIONES', 'LICENCIA', 'INASISTENCIA')),
fecha_inicio DATE NOT NULL,
fecha_fin DATE NOT NULL CHECK (fecha_fin >=fecha_inicio),
observacion VARCHAR(255)
);
CREATE TABLE cupos_horas_extras(
id_cupo INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
id_lider INTEGER NOT NULL REFERENCES usuarios(id_usuario),
id_cargo INTEGER NOT NULL REFERENCES cargos(id_cargo),
fecha DATE NOT NULL,
hora_inicio TIME NOT NULL,
hora_fin TIME NOT NULL,
cantidad_cupos INTEGER NOT NULL CHECK (cantidad_cupos > 0),
estado VARCHAR(20) NOT NULL CHECK (estado IN ('ABIERTO', 'CERRADO', 'CANCELADO'))
);