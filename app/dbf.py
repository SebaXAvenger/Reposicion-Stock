"""
Lector de tablas DBF de Visual FoxPro, en modo solo lectura.

POR QUE UN LECTOR PROPIO Y NO UNA LIBRERIA:

  1. Lectura selectiva de campos. ARTICULO tiene decenas de campos y este
     programa usa once. Decodificar el resto es trabajo tirado a la basura:
     en un catalogo de 33.000 filas la diferencia es de varios segundos a
     unas decimas.

  2. Control del codepage. Las tablas del ERP pueden estar en cp850 (DOS) o
     cp1252 (Windows). Si se elige mal, las descripciones con enie y acentos
     salen rotas. Aca se lee el byte de language driver del encabezado y se
     puede forzar a mano desde la configuracion.

  3. Tipos propios de VFP9 (I, B, Y, T, V) que las librerias generalistas
     orientadas a dBase III manejan a medias.

  4. Nada de bloqueos. Se abre el archivo en 'rb' y se lee. El ERP puede
     tener la tabla abierta SHARED al mismo tiempo sin que se molesten.
     Este programa NUNCA escribe sobre los datos del ERP.

El CDX no se lee ni se necesita: el catalogo entra entero en memoria y los
SEEK del formulario original se reemplazan por diccionarios.
"""

from __future__ import annotations

import datetime
import struct
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

# Codigos de "language driver" (byte 29 del encabezado) -> codec de Python.
# Es la tabla estandar de dBase/VFP. Los dos que importan en la practica son
# 0x03 (Windows ANSI, o sea cp1252) y 0x02 (DOS latinoamericano, cp850).
CODEPAGES: dict[int, str] = {
    0x01: "cp437", 0x02: "cp850", 0x03: "cp1252", 0x04: "mac_roman",
    0x08: "cp865", 0x09: "cp437", 0x0A: "cp850", 0x0B: "cp437",
    0x0D: "cp437", 0x0E: "cp850", 0x0F: "cp437", 0x10: "cp850",
    0x11: "cp437", 0x12: "cp850", 0x13: "cp932", 0x14: "cp850",
    0x15: "cp437", 0x16: "cp850", 0x17: "cp865", 0x18: "cp437",
    0x19: "cp437", 0x1A: "cp850", 0x1B: "cp437", 0x1C: "cp863",
    0x1D: "cp850", 0x1F: "cp852", 0x22: "cp852", 0x23: "cp852",
    0x24: "cp860", 0x25: "cp850", 0x26: "cp866", 0x37: "cp850",
    0x40: "cp852", 0x4D: "cp936", 0x4E: "cp949", 0x4F: "cp950",
    0x50: "cp874", 0x57: "cp1252", 0x58: "cp1252", 0x59: "cp1252",
    0x64: "cp852", 0x65: "cp866", 0x66: "cp865", 0x67: "cp861",
    0x68: "cp895", 0x69: "cp620", 0x6A: "cp737", 0x6B: "cp857",
    0x78: "cp950", 0x79: "cp949", 0x7A: "cp936", 0x7B: "cp932",
    0x7C: "cp874", 0x7D: "cp1255", 0x7E: "cp1256", 0x96: "mac_cyrillic",
    0x97: "mac_latin2", 0x98: "mac_greek", 0xC8: "cp1250", 0xC9: "cp1251",
    0xCA: "cp1254", 0xCB: "cp1253", 0xCC: "cp1257",
}

MARCA_BORRADO = 0x2A   # '*' en el primer byte del registro
MARCA_ACTIVO = 0x20    # ' '

# Cuanto se lee de una. Importa mas de lo que parece: estas tablas viven en
# un recurso de red. Con bloques chicos, un ARTICULO.DBF de 784 bytes por
# registro sale a diez registros por llamada al sistema, o sea miles de
# idas y vueltas por la red para leer un archivo de 26 MB. Con 1 MB por
# lectura son unas pocas decenas.
BLOQUE_LECTURA = 1 << 20


class ErrorDBF(Exception):
    pass


class Campo:
    """Descriptor de un campo del encabezado."""

    __slots__ = ("nombre", "tipo", "largo", "decimales", "inicio", "fin")

    def __init__(self, nombre: str, tipo: str, largo: int, decimales: int, inicio: int):
        self.nombre = nombre
        self.tipo = tipo
        self.largo = largo
        self.decimales = decimales
        self.inicio = inicio
        self.fin = inicio + largo

    def __repr__(self) -> str:  # pragma: no cover - ayuda de diagnostico
        return f"<Campo {self.nombre} {self.tipo}({self.largo},{self.decimales})>"


class TablaDBF:
    """Tabla DBF abierta para lectura secuencial."""

    def __init__(
        self,
        ruta: str | Path,
        codepage: str | None = None,
        incluir_borrados: bool = False,
    ):
        self.ruta = Path(ruta)
        if not self.ruta.is_file():
            raise ErrorDBF(f"No se encontro la tabla: {self.ruta}")

        self.incluir_borrados = incluir_borrados
        self._archivo = open(self.ruta, "rb")
        try:
            self._leer_encabezado()
        except Exception:
            self._archivo.close()
            raise

        # El codepage explicito de la configuracion gana sobre el del archivo.
        if codepage and codepage != "auto":
            self.codepage = codepage
            self.codepage_origen = "forzado por configuracion"
        else:
            self.codepage = CODEPAGES.get(self.byte_idioma, "cp1252")
            self.codepage_origen = (
                f"byte de idioma 0x{self.byte_idioma:02X} del encabezado"
                if self.byte_idioma in CODEPAGES
                else "cp1252 por defecto (el encabezado no declara idioma)"
            )

        self._memo = _AbridorMemo(self.ruta, self.codepage)

    # -- encabezado -----------------------------------------------------

    def _leer_encabezado(self) -> None:
        cabecera = self._archivo.read(32)
        if len(cabecera) < 32:
            raise ErrorDBF(f"Encabezado incompleto: {self.ruta}")

        (
            self.version,
            aa, mm, dd,
            self.cantidad_registros,
            self.largo_encabezado,
            self.largo_registro,
        ) = struct.unpack("<BBBBIHH", cabecera[:12])

        self.banderas = cabecera[28]
        self.byte_idioma = cabecera[29]
        try:
            self.ultima_actualizacion = datetime.date(1900 + aa, mm or 1, dd or 1)
        except ValueError:
            self.ultima_actualizacion = None

        self.campos: list[Campo] = []
        self._por_nombre: dict[str, Campo] = {}

        posicion = 1  # el byte 0 del registro es la marca de borrado
        self._archivo.seek(32)
        while True:
            bruto = self._archivo.read(32)
            if not bruto or bruto[0] in (0x0D, 0x00):
                break
            if len(bruto) < 32:
                break
            nombre = bruto[:11].split(b"\x00")[0].decode("ascii", "replace").strip()
            tipo = chr(bruto[11])
            largo = bruto[16]
            decimales = bruto[17]
            if not nombre:
                continue
            campo = Campo(nombre.upper(), tipo, largo, decimales, posicion)
            posicion += largo
            self.campos.append(campo)
            self._por_nombre[campo.nombre] = campo

        if not self.campos:
            raise ErrorDBF(f"La tabla no declara campos: {self.ruta}")

        # Coherencia: si el encabezado miente sobre el largo del registro,
        # el resto de la lectura se corre y no se nota hasta ver basura.
        if self.largo_registro < posicion:
            self.largo_registro = posicion

    # -- consulta -------------------------------------------------------

    @property
    def nombres(self) -> list[str]:
        return [c.nombre for c in self.campos]

    def tiene(self, nombre: str) -> bool:
        return nombre.upper() in self._por_nombre

    def campo(self, nombre: str) -> Campo:
        try:
            return self._por_nombre[nombre.upper()]
        except KeyError:
            raise ErrorDBF(
                f"La tabla {self.ruta.name} no tiene el campo {nombre}. "
                f"Campos disponibles: {', '.join(self.nombres)}"
            ) from None

    # -- lectura --------------------------------------------------------

    def filas(
        self,
        campos: Sequence[str] | None = None,
        bloque: int = BLOQUE_LECTURA,
    ) -> Iterator[dict[str, Any]]:
        """Recorre la tabla devolviendo un dict por registro.

        `campos` limita que columnas se decodifican. Es la optimizacion mas
        importante del lector: pedir once campos de una tabla de ochenta
        evita decodificar el 85% de cada registro.

        Los registros borrados se saltan, igual que hacia SET DELETED ON en
        el entorno del formulario original.
        """
        seleccion = self._resolver_seleccion(campos)
        conversores = [(c.nombre, c.inicio, c.fin, self._conversor(c)) for c in seleccion]

        self._archivo.seek(self.largo_encabezado)
        largo = self.largo_registro
        por_lote = max(1, bloque // largo)
        leidos = 0
        total = self.cantidad_registros
        incluir_borrados = self.incluir_borrados

        while leidos < total:
            cuantos = min(por_lote, total - leidos)
            datos = self._archivo.read(cuantos * largo)
            if not datos:
                break
            reales = len(datos) // largo
            for i in range(reales):
                base = i * largo
                marca = datos[base]
                if marca == MARCA_BORRADO and not incluir_borrados:
                    continue
                # Un byte de marca que no es ' ' ni '*' indica desfasaje:
                # se corta antes de escupir numeros inventados.
                if marca not in (MARCA_ACTIVO, MARCA_BORRADO):
                    if marca == 0x1A:  # fin de archivo
                        return
                fila = {}
                for nombre, inicio, fin, convertir in conversores:
                    fila[nombre] = convertir(datos[base + inicio: base + fin])
                if incluir_borrados:
                    fila["_BORRADO"] = marca == MARCA_BORRADO
                yield fila
            leidos += reales
            if reales < cuantos:
                break

    def tuplas(
        self,
        campos: Sequence[str],
        bloque: int = BLOQUE_LECTURA,
    ) -> Iterator[tuple]:
        """Igual que `filas()` pero devuelve tuplas en vez de diccionarios.

        POR QUE EXISTE: DOCUM y DOCCUER tienen millones de renglones. Armar
        un diccionario por registro cuesta mas que decodificar los campos.
        Con tuplas el recorrido de DOCCUER baja casi a la mitad, y el orden
        de las columnas lo fija el llamador, asi que no se pierde claridad.
        """
        seleccion = self._resolver_seleccion(campos)
        conversores = [(c.inicio, c.fin, self._conversor(c)) for c in seleccion]

        self._archivo.seek(self.largo_encabezado)
        largo = self.largo_registro
        por_lote = max(1, bloque // largo)
        leidos = 0
        total = self.cantidad_registros
        incluir_borrados = self.incluir_borrados

        while leidos < total:
            cuantos = min(por_lote, total - leidos)
            datos = self._archivo.read(cuantos * largo)
            if not datos:
                break
            reales = len(datos) // largo
            for i in range(reales):
                base = i * largo
                marca = datos[base]
                if marca == MARCA_BORRADO and not incluir_borrados:
                    continue
                if marca == 0x1A:
                    return
                yield tuple(
                    convertir(datos[base + inicio: base + fin])
                    for inicio, fin, convertir in conversores
                )
            leidos += reales
            if reales < cuantos:
                break

    def _resolver_seleccion(self, campos: Sequence[str] | None) -> list[Campo]:
        if campos is None:
            return list(self.campos)
        return [self.campo(nombre) for nombre in campos]

    # -- conversion de tipos --------------------------------------------

    def _conversor(self, campo: Campo) -> Callable[[bytes], Any]:
        tipo = campo.tipo
        codepage = self.codepage
        decimales = campo.decimales

        if tipo in ("C",):
            def convertir_texto(bruto: bytes) -> str:
                # rstrip de espacios y de nulos: VFP rellena con espacios,
                # pero campos tocados por otras herramientas traen \x00.
                return bruto.decode(codepage, "replace").rstrip("\x00 ")
            return convertir_texto

        if tipo in ("N", "F"):
            if decimales == 0:
                def convertir_entero(bruto: bytes) -> Any:
                    texto = bruto.strip()
                    if not texto or texto == b"." * len(texto):
                        return None
                    try:
                        return int(texto)
                    except ValueError:
                        try:
                            return float(texto.replace(b"*", b""))
                        except ValueError:
                            return None
                return convertir_entero

            def convertir_decimal(bruto: bytes) -> Any:
                texto = bruto.strip()
                if not texto:
                    return None
                try:
                    return float(texto)
                except ValueError:
                    # VFP escribe '*' cuando el numero no entra en el ancho
                    limpio = texto.replace(b"*", b"").strip()
                    try:
                        return float(limpio) if limpio else None
                    except ValueError:
                        return None
            return convertir_decimal

        if tipo == "D":
            def convertir_fecha(bruto: bytes) -> datetime.date | None:
                texto = bruto.strip()
                if len(texto) != 8 or not texto.isdigit():
                    return None
                try:
                    return datetime.date(
                        int(texto[0:4]), int(texto[4:6]), int(texto[6:8])
                    )
                except ValueError:
                    return None
            return convertir_fecha

        if tipo == "L":
            def convertir_logico(bruto: bytes) -> bool | None:
                caracter = bruto[:1].upper()
                if caracter in (b"T", b"Y"):
                    return True
                if caracter in (b"F", b"N"):
                    return False
                return None
            return convertir_logico

        if tipo == "I":  # Integer de VFP, 4 bytes
            return lambda bruto: struct.unpack("<i", bruto[:4])[0] if len(bruto) >= 4 else None

        if tipo == "B":  # Double de VFP, 8 bytes
            return lambda bruto: struct.unpack("<d", bruto[:8])[0] if len(bruto) >= 8 else None

        if tipo == "Y":  # Currency: entero de 8 bytes escalado por 10.000
            def convertir_moneda(bruto: bytes) -> float | None:
                if len(bruto) < 8:
                    return None
                return struct.unpack("<q", bruto[:8])[0] / 10000.0
            return convertir_moneda

        if tipo == "T":  # DateTime: dia juliano + milisegundos
            def convertir_marca(bruto: bytes) -> datetime.datetime | None:
                if len(bruto) < 8:
                    return None
                juliano, mseg = struct.unpack("<ii", bruto[:8])
                if juliano == 0:
                    return None
                try:
                    fecha = datetime.date.fromordinal(juliano - 1721425)
                except (ValueError, OverflowError):
                    return None
                return datetime.datetime.combine(
                    fecha, datetime.time()
                ) + datetime.timedelta(milliseconds=mseg)
            return convertir_marca

        if tipo in ("V", "Q"):  # Varchar / Varbinary de VFP9
            def convertir_varchar(bruto: bytes) -> str:
                return bruto.decode(codepage, "replace").rstrip("\x00 ")
            return convertir_varchar

        if tipo in ("M", "G", "P"):  # Memo / General / Picture
            memo = self._memo
            largo_ref = campo.largo

            def convertir_memo(bruto: bytes) -> Any:
                return memo.leer(bruto, largo_ref, tipo == "M")
            return convertir_memo

        if tipo == "0":  # _NullFlags interno de VFP
            return lambda bruto: None

        # Tipo desconocido: se devuelve crudo en vez de romper la corrida.
        return lambda bruto: bruto.decode(codepage, "replace").rstrip("\x00 ")

    # -- ciclo de vida ---------------------------------------------------

    def cerrar(self) -> None:
        if getattr(self, "_archivo", None) and not self._archivo.closed:
            self._archivo.close()
        if getattr(self, "_memo", None):
            self._memo.cerrar()

    def __enter__(self) -> "TablaDBF":
        return self

    def __exit__(self, *_excepcion: Any) -> None:
        self.cerrar()

    def __len__(self) -> int:
        return self.cantidad_registros

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<TablaDBF {self.ruta.name} registros={self.cantidad_registros} "
            f"campos={len(self.campos)} codepage={self.codepage}>"
        )


class _AbridorMemo:
    """Lectura perezosa del .FPT asociado. Solo se abre si alguna columna
    memo se pide de verdad."""

    def __init__(self, ruta_dbf: Path, codepage: str):
        self._ruta = ruta_dbf.with_suffix(".fpt")
        self._codepage = codepage
        self._archivo = None
        self._tam_bloque = 64
        self._intentado = False

    def _asegurar(self) -> bool:
        if self._intentado:
            return self._archivo is not None
        self._intentado = True
        ruta = self._ruta
        if not ruta.is_file():
            for alternativa in (
                ruta.with_suffix(".FPT"),
                ruta.with_suffix(".dbt"),
                ruta.with_suffix(".DBT"),
            ):
                if alternativa.is_file():
                    ruta = alternativa
                    break
            else:
                return False
        try:
            self._archivo = open(ruta, "rb")
            cabecera = self._archivo.read(8)
            if len(cabecera) >= 8:
                self._tam_bloque = struct.unpack(">H", cabecera[6:8])[0] or 64
        except OSError:
            self._archivo = None
        return self._archivo is not None

    def leer(self, bruto: bytes, largo_ref: int, como_texto: bool) -> Any:
        if not self._asegurar():
            return ""
        if largo_ref == 4:
            bloque = struct.unpack("<I", bruto[:4])[0]
        else:
            texto = bruto.strip()
            if not texto.isdigit():
                return ""
            bloque = int(texto)
        if bloque == 0:
            return ""
        try:
            self._archivo.seek(bloque * self._tam_bloque)
            cabecera = self._archivo.read(8)
            if len(cabecera) < 8:
                return ""
            _tipo, largo = struct.unpack(">II", cabecera)
            datos = self._archivo.read(largo)
        except OSError:
            return ""
        if como_texto:
            return datos.decode(self._codepage, "replace").rstrip("\x00 ")
        return datos

    def cerrar(self) -> None:
        if self._archivo and not self._archivo.closed:
            self._archivo.close()


# ---------------------------------------------------------------------------

def leer_tabla(
    ruta: str | Path,
    campos: Sequence[str] | None = None,
    codepage: str | None = None,
) -> list[dict[str, Any]]:
    """Atajo: devuelve la tabla entera como lista de diccionarios."""
    with TablaDBF(ruta, codepage=codepage) as tabla:
        return list(tabla.filas(campos))


def describir(ruta: str | Path) -> str:
    """Descripcion legible de la estructura. Sirve para diagnosticar cuando
    los nombres de campo no son los esperados."""
    with TablaDBF(ruta) as tabla:
        lineas = [
            f"Tabla:      {tabla.ruta}",
            f"Registros:  {tabla.cantidad_registros:,}",
            f"Codepage:   {tabla.codepage}  ({tabla.codepage_origen})",
            f"Version:    0x{tabla.version:02X}",
            "Campos:",
        ]
        for campo in tabla.campos:
            lineas.append(
                f"   {campo.nombre:<12} {campo.tipo}  "
                f"{campo.largo:>3}.{campo.decimales}"
            )
        return "\n".join(lineas)
