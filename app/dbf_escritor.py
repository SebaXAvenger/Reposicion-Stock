"""
Escritor de tablas DBF de Visual FoxPro.

Este es el UNICO lugar del programa que escribe un DBF, y solo escribe
ROTACION.DBF, que es una tabla propia del modulo de reposicion: no forma
parte del maestro del ERP. Las tablas del sistema (ARTICULO, PROVEEDO,
DOCUM, DOCCUER) se abren siempre en modo lectura.

COMO REEMPLAZA EL ARCHIVO Y POR QUE:

  El PRG original hacia COPY TO sobre el destino, despues de comprobar que
  podia abrirlo EXCLUSIVE. Si el chequeo pasaba pero alguien abria la tabla
  entre el chequeo y el COPY TO, la escritura pisaba una tabla en uso.

  Aca se escribe SIEMPRE en un archivo temporal en la misma carpeta y
  recien al final se hace el reemplazo, que en Windows es atomico: o queda
  la tabla nueva entera, o queda la vieja intacta. Nunca una a medias.
  Si otro puesto tiene la tabla abierta, el reemplazo falla con un error
  claro y la tabla vieja sigue sirviendo.

EL CDX:

  El PRG creaba `INDEX ON ROT_ARTIC + ROT_ORIGE TAG ROTART`. El formulario
  de reposicion NO usa ese tag: lee ROTACION con un SELECT ... GROUP BY y
  nunca hace SEEK sobre ella. Escribir un CDX compacto desde Python seria
  reimplementar el arbol B de VFP para nada.

  Lo que si hay que hacer es BORRAR el CDX viejo. Si queda un ROTACION.CDX
  de la corrida anterior junto a una tabla nueva, VFP la abre y trabaja con
  un indice que apunta a registros que ya no existen. Ademas el byte de
  banderas del encabezado se escribe en cero, o sea "esta tabla no tiene
  CDX asociado", que es la verdad.
"""

from __future__ import annotations

import datetime
import os
import struct
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence

VERSION_VFP = 0x30
BYTE_IDIOMA_CP1252 = 0x03
BYTE_IDIOMA_CP850 = 0x02

CODEPAGE_A_BYTE = {
    "cp1252": 0x03, "cp850": 0x02, "cp437": 0x01, "cp852": 0x64,
    "cp865": 0x08, "cp866": 0x65, "cp1250": 0xC8, "cp1251": 0xC9,
}


class ErrorEscritura(Exception):
    pass


class TablaEnUso(ErrorEscritura):
    """El destino esta abierto por otro proceso."""


def escribir_tabla(
    destino: str | Path,
    campos: Sequence[tuple[str, str, int, int]],
    filas: Iterable[dict[str, Any]],
    codepage: str = "cp1252",
    borrar_cdx: bool = True,
) -> tuple[Path, int]:
    """Escribe la tabla completa y la deja en `destino`.

    campos = [(nombre, tipo, largo, decimales), ...]
    Devuelve (ruta, cantidad_de_registros).
    """
    destino = Path(destino)
    carpeta = destino.parent
    if not carpeta.is_dir():
        raise ErrorEscritura(f"No existe la carpeta de destino: {carpeta}")

    _validar_campos(campos)
    byte_idioma = CODEPAGE_A_BYTE.get(codepage, BYTE_IDIOMA_CP1252)

    # El temporal va en la MISMA carpeta que el destino: si fuera en TEMP,
    # el reemplazo cruzaria de volumen y dejaria de ser atomico.
    descriptor, ruta_temporal = tempfile.mkstemp(
        prefix=destino.stem + "_", suffix=".tmp", dir=str(carpeta)
    )
    os.close(descriptor)
    temporal = Path(ruta_temporal)

    try:
        cantidad = _volcar(temporal, campos, filas, codepage, byte_idioma)
        _reemplazar(temporal, destino)
    except Exception:
        temporal.unlink(missing_ok=True)
        raise

    if borrar_cdx:
        _borrar_indice(destino)

    return destino, cantidad


# ---------------------------------------------------------------------------

def _validar_campos(campos: Sequence[tuple[str, str, int, int]]) -> None:
    vistos = set()
    for nombre, tipo, largo, decimales in campos:
        clave = nombre.upper()
        if len(clave) > 10:
            raise ErrorEscritura(
                f"El nombre de campo '{nombre}' pasa los 10 caracteres que "
                f"admite el formato DBF."
            )
        if clave in vistos:
            raise ErrorEscritura(f"Campo repetido: {nombre}")
        vistos.add(clave)
        if tipo not in "CNFDL":
            raise ErrorEscritura(
                f"Tipo de campo no soportado por el escritor: {tipo} "
                f"(campo {nombre}). Solo se escriben C, N, F, D y L."
            )
        if tipo in "NF" and largo > 20:
            raise ErrorEscritura(f"El campo numerico {nombre} es demasiado ancho.")
        if tipo == "D" and largo != 8:
            raise ErrorEscritura(f"El campo fecha {nombre} tiene que medir 8.")
        if tipo == "L" and largo != 1:
            raise ErrorEscritura(f"El campo logico {nombre} tiene que medir 1.")


def _volcar(
    ruta: Path,
    campos: Sequence[tuple[str, str, int, int]],
    filas: Iterable[dict[str, Any]],
    codepage: str,
    byte_idioma: int,
) -> int:
    largo_registro = 1 + sum(c[2] for c in campos)
    largo_encabezado = 32 + 32 * len(campos) + 1
    hoy = datetime.date.today()
    cantidad = 0

    with open(ruta, "wb") as salida:
        salida.write(bytes(largo_encabezado))          # reservado, se reescribe

        salida.seek(0)
        cabecera = bytearray(32)
        cabecera[0] = VERSION_VFP
        cabecera[1] = hoy.year - 1900
        cabecera[2] = hoy.month
        cabecera[3] = hoy.day
        struct.pack_into("<H", cabecera, 8, largo_encabezado)
        struct.pack_into("<H", cabecera, 10, largo_registro)
        cabecera[28] = 0x00        # sin CDX, sin memo, no pertenece a un DBC
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

        # Se escribe por lotes: un write por registro sobre un recurso de
        # red cuesta carisimo.
        lote: list[bytes] = []
        for fila in filas:
            partes = [b" "]
            for nombre, tipo, largo, decimales in campos:
                partes.append(
                    _codificar(fila.get(nombre.upper()), tipo, largo, decimales, codepage)
                )
            lote.append(b"".join(partes))
            cantidad += 1
            if len(lote) >= 2000:
                salida.write(b"".join(lote))
                lote.clear()
        if lote:
            salida.write(b"".join(lote))

        salida.write(b"\x1A")

        # Recien ahora se sabe cuantos registros hubo
        salida.seek(4)
        salida.write(struct.pack("<I", cantidad))
        salida.flush()
        os.fsync(salida.fileno())

    return cantidad


def _reemplazar(temporal: Path, destino: Path) -> None:
    """Reemplazo atomico, con un mensaje util si la tabla esta en uso."""
    try:
        os.replace(str(temporal), str(destino))
    except PermissionError as error:
        raise TablaEnUso(
            f"No se pudo reemplazar {destino.name}: la tabla esta abierta por "
            f"otro puesto, o por el propio ERP.\n\n"
            f"Cerrala en los demas puestos y volve a intentar. La tabla "
            f"anterior quedo intacta.\n\n({error})"
        ) from error
    except OSError as error:
        raise ErrorEscritura(
            f"No se pudo escribir {destino}: {error}"
        ) from error


def _borrar_indice(destino: Path) -> None:
    """Saca el CDX viejo, que quedo apuntando a registros que ya no existen."""
    for sufijo in (".cdx", ".CDX", ".Cdx"):
        candidato = destino.with_suffix(sufijo)
        if candidato.is_file():
            try:
                candidato.unlink()
            except OSError:
                pass


def _codificar(
    valor: Any, tipo: str, largo: int, decimales: int, codepage: str
) -> bytes:
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
        crudo = texto.encode("ascii")
        if len(crudo) > largo:
            # VFP escribe asteriscos cuando el numero no entra en el ancho.
            # Es preferible eso a truncar y grabar un numero distinto.
            return b"*" * largo
        return crudo.rjust(largo, b" ")

    if tipo == "D":
        if not valor:
            return b" " * 8
        if isinstance(valor, datetime.datetime):
            valor = valor.date()
        return valor.strftime("%Y%m%d").encode("ascii")

    if tipo == "L":
        if valor is None:
            return b"?"
        return b"T" if valor else b"F"

    return b" " * largo
