"""
Escritor minimo de DBF. SOLO PARA GENERAR DATOS DE PRUEBA.

El programa nunca escribe sobre las tablas del ERP; esto existe unicamente
para poder armar un juego de tablas ficticias y probar la aplicacion sin
acceso al sistema real.
"""

from __future__ import annotations

import datetime
import struct
from pathlib import Path
from typing import Any, Sequence

# 0x03 = Windows ANSI (cp1252), que es lo que declara el formulario original
BYTE_IDIOMA_CP1252 = 0x03
BYTE_IDIOMA_CP850 = 0x02


def escribir_dbf(
    ruta: str | Path,
    campos: Sequence[tuple[str, str, int, int]],
    filas: Sequence[dict[str, Any]],
    byte_idioma: int = BYTE_IDIOMA_CP1252,
    codepage: str = "cp1252",
) -> Path:
    """campos = [(nombre, tipo, largo, decimales), ...]"""
    ruta = Path(ruta)
    largo_registro = 1 + sum(c[2] for c in campos)
    largo_encabezado = 32 + 32 * len(campos) + 1
    hoy = datetime.date.today()

    with open(ruta, "wb") as salida:
        cabecera = bytearray(32)
        cabecera[0] = 0x30                     # Visual FoxPro
        cabecera[1] = hoy.year - 1900
        cabecera[2] = hoy.month
        cabecera[3] = hoy.day
        struct.pack_into("<I", cabecera, 4, len(filas))
        struct.pack_into("<H", cabecera, 8, largo_encabezado)
        struct.pack_into("<H", cabecera, 10, largo_registro)
        cabecera[29] = byte_idioma
        salida.write(cabecera)

        desplazamiento = 1
        for nombre, tipo, largo, decimales in campos:
            descriptor = bytearray(32)
            crudo = nombre.upper().encode("ascii")[:10]
            descriptor[0: len(crudo)] = crudo
            descriptor[11] = ord(tipo)
            struct.pack_into("<I", descriptor, 12, desplazamiento)
            descriptor[16] = largo
            descriptor[17] = decimales
            salida.write(descriptor)
            desplazamiento += largo

        salida.write(b"\x0D")

        for fila in filas:
            salida.write(b" ")
            for nombre, tipo, largo, decimales in campos:
                salida.write(
                    _codificar(fila.get(nombre.upper()), tipo, largo, decimales, codepage)
                )

        salida.write(b"\x1A")

    return ruta


def _codificar(valor: Any, tipo: str, largo: int, decimales: int, codepage: str) -> bytes:
    if tipo == "C":
        texto = "" if valor is None else str(valor)
        return texto.encode(codepage, "replace")[:largo].ljust(largo, b" ")

    if tipo in ("N", "F"):
        if valor is None:
            return b" " * largo
        if decimales:
            texto = f"{float(valor):.{decimales}f}"
        else:
            texto = str(int(round(float(valor))))
        return texto.encode("ascii")[-largo:].rjust(largo, b" ")

    if tipo == "D":
        if not valor:
            return b" " * 8
        return valor.strftime("%Y%m%d").encode("ascii")

    if tipo == "L":
        if valor is None:
            return b"?"
        return b"T" if valor else b"F"

    return b" " * largo
