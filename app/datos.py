"""
Acceso a las tablas del ERP.

Reemplaza al bloque Load del formulario original (USE ... IN 0 SHARED) y a
los SEEK contra los tags del CDX. Como el catalogo entra comodo en memoria,
los indices se reemplazan por diccionarios: mismo resultado, sin depender de
que los tags del CDX existan ni esten sanos.

Nada de este modulo escribe sobre los datos del ERP.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .config import Parametros, resolver_archivo
from .dbf import ErrorDBF, TablaDBF
from .vfp import alltrim, igual_exact_off, num, padr

# Campos que el programa realmente usa. Pedir solo estos es lo que hace que
# recorrer 33.000 articulos cueste decimas de segundo y no varios segundos.
CAMPOS_ARTICULO = [
    "AR_SUCU", "AR_CODI", "AR_PLU_", "AR_DESC", "AR_TIPO", "AR_PROV",
    "AR_MINI", "AR_MAXI", "AR_CANT", "AR_COST", "AR_ACTIVO",
    # DESC_PROV trae el nombre del proveedor denormalizado dentro de
    # ARTICULO. Es el respaldo cuando la busqueda en PROVEEDO no engancha.
    "DESC_PROV",
    # Informativos: se muestran en el detalle del articulo y salen en el
    # Excel. AR_UBICACI es donde esta fisicamente la mercaderia.
    "AR_MARCA", "AR_UBICACI",
]

CAMPOS_ROTACION = [
    "ROT_ARTIC", "ROT_ORIGE", "ROT_PROME", "ROT_MEDIA", "ROT_MESCON",
    "ROT_UNIDS", "ROT_ULTVTA", "ROT_FECCAL", "ROT_NEGRO",
    "ROT_DESDE", "ROT_HASTA", "ROT_MESES",
]

# Nombres posibles del campo codigo en PROVEEDO. El formulario original nunca
# lo nombraba: hacia SEEK contra el tag COD_ALFA del CDX y leia PR_NOMBRE.
# Sin CDX hay que encontrar la columna, asi que se prueban los candidatos
# habituales antes de rendirse.
CANDIDATOS_CODIGO_PROV = [
    "PR_CODI", "PR_CODIGO", "PR_COD", "PR_ALFA", "PR_CODALFA",
    "CODIGO", "COD_ALFA", "CODALFA", "PR_NUMERO",
]

CANDIDATOS_NOMBRE_PROV = [
    "PR_NOMBRE", "PR_NOMB", "PR_RAZON", "PR_RSOCIAL", "NOMBRE", "RAZON",
]

# La clave de 7 caracteres se arma con la sucursal ADELANTE del codigo.
CANDIDATOS_SUCURSAL_PROV = ["PR_SUCURS", "PR_SUCU", "SUCURSAL"]

# Nombre de fantasia: respaldo si PR_NOMBRE viniera vacio.
CANDIDATOS_FANTASIA_PROV = ["PR_FANTAS", "PR_FANTASIA", "FANTASIA"]


@dataclass
class Articulo:
    """Una fila del catalogo, ya normalizada."""

    __slots__ = (
        "sucursal", "codigo", "clave", "clave_corta", "cod_prov_articulo",
        "descripcion", "unidad", "cod_proveedor_bruto", "desc_proveedor",
        "minimo", "maximo", "stock_local", "costo", "marca", "ubicacion",
    )

    sucursal: str
    codigo: str
    clave: str
    # Clave alternativa: el codigo solo, sin el prefijo de sucursal.
    # Ver el comentario de `buscar_demanda` mas abajo.
    clave_corta: str
    cod_prov_articulo: str
    descripcion: str
    unidad: str
    cod_proveedor_bruto: str
    desc_proveedor: str
    minimo: float
    maximo: float
    stock_local: float
    costo: float
    marca: str
    ubicacion: str


@dataclass
class DemandaArticulo:
    """Fila de ROTACION ya agrupada por articulo, con los dos origenes
    separados. El formulario los separa a proposito: los necesita por
    separado para repartir el pedido entre los dos depositos."""

    __slots__ = (
        "promedio_local", "promedio_remoto", "mediana_local", "mediana_remota",
        "meses_con_venta_local", "meses_con_venta_remoto", "unidades_totales",
        "ultima_venta",
    )

    promedio_local: float
    promedio_remoto: float
    mediana_local: float
    mediana_remota: float
    meses_con_venta_local: int
    meses_con_venta_remoto: int
    unidades_totales: float
    ultima_venta: Any


@dataclass
class InfoRotacion:
    """Encabezado informativo de ROTACION.DBF."""

    fecha_calculo: Any = None
    incluye_negro: bool = False
    desde: Any = None
    hasta: Any = None
    meses: int = 0
    disponible: bool = False
    mensaje: str = ""


@dataclass
class Catalogo:
    """Todo lo que se lee del disco, listo para el calculo."""

    articulos: list[Articulo] = field(default_factory=list)
    total_catalogo: int = 0
    proveedores: dict[str, str] = field(default_factory=dict)
    # Respaldo armado con DESC_PROV de ARTICULO, por si PROVEEDO no engancha
    proveedores_respaldo: dict[str, str] = field(default_factory=dict)
    demanda: dict[str, DemandaArticulo] = field(default_factory=dict)
    info_rotacion: InfoRotacion = field(default_factory=InfoRotacion)
    stock_remoto: dict[str, float] = field(default_factory=dict)
    remoto_disponible: bool = False
    codepage: str = ""
    diagnostico: list[str] = field(default_factory=list)
    tiempos: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------

class RepositorioERP:
    """Lee las tablas del ERP y arma el Catalogo."""

    def __init__(self, parametros: Parametros):
        self.p = parametros

    # -- catalogo local --------------------------------------------------

    def cargar(self, con_remoto: bool = False, con_rotacion: bool = True) -> Catalogo:
        catalogo = Catalogo()
        reloj = time.perf_counter

        inicio = reloj()
        self._cargar_articulos(catalogo)
        catalogo.tiempos["articulos"] = reloj() - inicio

        inicio = reloj()
        self._cargar_proveedores(catalogo)
        catalogo.tiempos["proveedores"] = reloj() - inicio

        if con_rotacion:
            inicio = reloj()
            self._cargar_rotacion(catalogo)
            catalogo.tiempos["rotacion"] = reloj() - inicio

        if con_remoto:
            inicio = reloj()
            self._cargar_stock_remoto(catalogo)
            catalogo.tiempos["stock_remoto"] = reloj() - inicio

        return catalogo

    def _cargar_articulos(self, catalogo: Catalogo) -> None:
        ruta = resolver_archivo(self.p.ruta_articulo)
        sucursal = alltrim(self.p.sucursal)
        todo_catalogo = self.p.catalogo_completo
        comparar = igual_exact_off if self.p.exact_off else _igual_estricto

        with TablaDBF(ruta, codepage=self.p.codepage) as tabla:
            catalogo.codepage = tabla.codepage
            catalogo.diagnostico.append(
                f"ARTICULO.DBF: {tabla.cantidad_registros:,} registros, "
                f"codepage {tabla.codepage} ({tabla.codepage_origen})"
            )
            campos = [c for c in CAMPOS_ARTICULO if tabla.tiene(c)]
            faltantes = [c for c in CAMPOS_ARTICULO if not tabla.tiene(c)]
            if faltantes:
                catalogo.diagnostico.append(
                    "ARTICULO.DBF no tiene estos campos y se asumen vacios: "
                    + ", ".join(faltantes)
                )

            total = 0
            articulos = catalogo.articulos
            for fila in tabla.filas(campos):
                total += 1

                # WHERE UPPER(AR_ACTIVO) = "S"
                if alltrim(fila.get("AR_ACTIVO", "")).upper()[:1] != "S":
                    continue

                # AND (llTodoCat OR AR_SUCU = lcSucu)
                # OJO: con SET EXACT OFF el `=` es "empieza con", no "es igual".
                suc = fila.get("AR_SUCU", "") or ""
                if not todo_catalogo and not comparar(suc, sucursal):
                    continue

                codigo = fila.get("AR_CODI", "") or ""
                articulos.append(
                    Articulo(
                        sucursal=suc,
                        codigo=codigo,
                        clave=clave_articulo(suc, codigo),
                        clave_corta=normalizar_clave(codigo),
                        # PADR(ALLTRIM(AR_PLU_), 20): el campo se graba con los
                        # espacios ADELANTE y sin esto el codigo del proveedor
                        # aparece corrido contra el borde derecho de la celda.
                        cod_prov_articulo=alltrim(fila.get("AR_PLU_", "")),
                        descripcion=alltrim(fila.get("AR_DESC", "")),
                        unidad=alltrim(fila.get("AR_TIPO", "")),
                        cod_proveedor_bruto=fila.get("AR_PROV", "") or "",
                        desc_proveedor=alltrim(fila.get("DESC_PROV", "")),
                        minimo=num(fila.get("AR_MINI")),
                        maximo=num(fila.get("AR_MAXI")),
                        stock_local=num(fila.get("AR_CANT")),
                        costo=num(fila.get("AR_COST")),
                        marca=alltrim(fila.get("AR_MARCA", "")),
                        ubicacion=alltrim(fila.get("AR_UBICACI", "")),
                    )
                )

                # Se va armando el respaldo de nombres con DESC_PROV: el
                # primero no vacio por cada codigo de proveedor.
                articulo = articulos[-1]
                if articulo.desc_proveedor:
                    codigo_proveedor = normalizar_proveedor(
                        articulo.cod_proveedor_bruto
                    )
                    catalogo.proveedores_respaldo.setdefault(
                        codigo_proveedor, articulo.desc_proveedor
                    )

            catalogo.total_catalogo = total

    def _cargar_proveedores(self, catalogo: Catalogo) -> None:
        ruta = resolver_archivo(self.p.ruta_proveedo)
        try:
            tabla = TablaDBF(ruta, codepage=self.p.codepage)
        except ErrorDBF as error:
            catalogo.diagnostico.append(f"PROVEEDO.DBF: {error}")
            return

        with tabla:
            campo_codigo = _primer_campo(tabla, CANDIDATOS_CODIGO_PROV)
            campo_nombre = _primer_campo(tabla, CANDIDATOS_NOMBRE_PROV)
            campo_sucursal = _primer_campo(tabla, CANDIDATOS_SUCURSAL_PROV)
            campo_fantasia = _primer_campo(tabla, CANDIDATOS_FANTASIA_PROV)

            if not campo_nombre:
                campo_nombre = _primer_texto_largo(tabla)
            if not campo_codigo:
                campo_codigo = _primer_texto_corto(tabla, excluir=campo_nombre)

            if not campo_codigo or not campo_nombre:
                catalogo.diagnostico.append(
                    "PROVEEDO.DBF: no se pudo identificar el par codigo/nombre. "
                    f"Campos: {', '.join(tabla.nombres)}"
                )
                return

            catalogo.diagnostico.append(
                f"PROVEEDO.DBF: {tabla.cantidad_registros:,} registros, "
                f"clave = {campo_sucursal or '(sin sucursal)'} + {campo_codigo}, "
                f"nombre = {campo_nombre}"
            )

            campos = [campo_codigo, campo_nombre]
            if campo_sucursal:
                campos.append(campo_sucursal)
            if campo_fantasia:
                campos.append(campo_fantasia)

            for fila in tabla.filas(campos):
                codigo = fila.get(campo_codigo)
                nombre = alltrim(fila.get(campo_nombre))
                if not nombre and campo_fantasia:
                    nombre = alltrim(fila.get(campo_fantasia))
                if not nombre:
                    continue

                sucursal = fila.get(campo_sucursal, "") if campo_sucursal else ""
                # Se indexa por la clave de 7 caracteres tal cual la arma
                # NormalizarProv, y ademas por la version pelada, que es el
                # fallback que hacia NombreProveedor.
                catalogo.proveedores.setdefault(
                    clave_proveedor(sucursal, codigo), nombre
                )
                catalogo.proveedores.setdefault(_texto_codigo(codigo), nombre)

    def _cargar_rotacion(self, catalogo: Catalogo) -> None:
        ruta = resolver_archivo(self.p.ruta_rotacion)
        info = catalogo.info_rotacion

        if not ruta.is_file():
            info.mensaje = "ROTACION.DBF no existe todavia."
            return

        try:
            tabla = TablaDBF(ruta, codepage=self.p.codepage)
        except ErrorDBF as error:
            info.mensaje = str(error)
            return

        with tabla:
            # Guarda de version, igual que el original: esta pantalla necesita
            # ROT_DESDE/ROT_HASTA/ROT_MESES para poder informar sobre que
            # periodo se midio la demanda. Una tabla vieja pasaria un chequeo
            # de ROT_ORIGE solo y reventaria mas adelante.
            requeridos = ["ROT_ARTIC", "ROT_ORIGE", "ROT_DESDE", "ROT_HASTA", "ROT_MESES"]
            faltantes = [c for c in requeridos if not tabla.tiene(c)]
            if faltantes:
                info.mensaje = (
                    "ROTACION.DBF fue generada con una version anterior del "
                    "calculo. Le faltan: " + ", ".join(faltantes)
                )
                return

            campos = [c for c in CAMPOS_ROTACION if tabla.tiene(c)]
            demanda = catalogo.demanda
            fecha_calculo = None
            desde = None
            hasta = None
            meses = 0
            incluye_negro = False

            for fila in tabla.filas(campos):
                clave = normalizar_clave(fila.get("ROT_ARTIC"))
                if not clave:
                    continue

                origen = alltrim(fila.get("ROT_ORIGE", "")).upper()[:1]
                promedio = num(fila.get("ROT_PROME"))
                mediana = num(fila.get("ROT_MEDIA"))
                meses_con = int(num(fila.get("ROT_MESCON")))
                unidades = num(fila.get("ROT_UNIDS"))
                ultima = fila.get("ROT_ULTVTA")

                registro = demanda.get(clave)
                if registro is None:
                    registro = DemandaArticulo(0.0, 0.0, 0.0, 0.0, 0, 0, 0.0, None)
                    demanda[clave] = registro

                # SUM(IIF(ROT_ORIGE="L", ...)) / MAX(...) agrupado por articulo
                if origen == "R":
                    registro.promedio_remoto += promedio
                    registro.mediana_remota += mediana
                    if meses_con > registro.meses_con_venta_remoto:
                        registro.meses_con_venta_remoto = meses_con
                else:
                    registro.promedio_local += promedio
                    registro.mediana_local += mediana
                    if meses_con > registro.meses_con_venta_local:
                        registro.meses_con_venta_local = meses_con

                registro.unidades_totales += unidades
                if ultima and (registro.ultima_venta is None or ultima > registro.ultima_venta):
                    registro.ultima_venta = ultima

                feccal = fila.get("ROT_FECCAL")
                if feccal and (fecha_calculo is None or feccal > fecha_calculo):
                    fecha_calculo = feccal
                if fila.get("ROT_NEGRO"):
                    incluye_negro = True
                fdesde = fila.get("ROT_DESDE")
                if fdesde and (desde is None or fdesde < desde):
                    desde = fdesde
                fhasta = fila.get("ROT_HASTA")
                if fhasta and (hasta is None or fhasta > hasta):
                    hasta = fhasta
                nmeses = int(num(fila.get("ROT_MESES")))
                if nmeses > meses:
                    meses = nmeses

            if not demanda:
                info.mensaje = "ROTACION.DBF no tiene articulos con movimiento."
                return

            info.disponible = True
            info.fecha_calculo = fecha_calculo
            info.incluye_negro = incluye_negro
            info.desde = desde
            info.hasta = hasta
            info.meses = meses
            catalogo.diagnostico.append(
                f"ROTACION.DBF: {tabla.cantidad_registros:,} filas, "
                f"{len(demanda):,} articulos con movimiento"
            )

    def _cargar_stock_remoto(self, catalogo: Catalogo) -> None:
        """Arma el equivalente de curRem.

        X:\\ARTICULO es una copia GEMELA del mismo maestro con su propio
        stock, por eso la clave es LA MISMA (AR_SUCU + AR_CODI) y no se
        invierte el prefijo. Este comentario viene del original y conviene
        conservarlo: es contraintuitivo y ya confundio a alguien una vez.
        """
        if not self.p.carpeta_datos2:
            catalogo.diagnostico.append(
                "No se configuro la carpeta de la otra sucursal: se analiza "
                "solo el stock local."
            )
            return

        ruta = resolver_archivo(self.p.ruta_articulo_remoto)
        if not ruta.is_file():
            catalogo.diagnostico.append(f"No se encontro: {ruta}")
            return

        try:
            tabla = TablaDBF(ruta, codepage=self.p.codepage)
        except ErrorDBF as error:
            catalogo.diagnostico.append(f"Stock remoto: {error}")
            return

        with tabla:
            acumulado: dict[str, float] = {}
            for fila in tabla.filas(["AR_SUCU", "AR_CODI", "AR_CANT"]):
                clave = clave_articulo(fila.get("AR_SUCU"), fila.get("AR_CODI"))
                acumulado[clave] = acumulado.get(clave, 0.0) + num(fila.get("AR_CANT"))

            if not acumulado:
                catalogo.diagnostico.append(
                    "La tabla de la otra sucursal no devolvio articulos."
                )
                return

            catalogo.stock_remoto = acumulado
            catalogo.remoto_disponible = True
            catalogo.diagnostico.append(
                f"Stock de la otra sucursal: {len(acumulado):,} claves leidas de {ruta}"
            )


# ---------------------------------------------------------------------------

def buscar_demanda(articulo: Articulo, demanda: dict[str, Any]) -> Any:
    """Cruza un articulo contra ROTACION tolerando las dos formas de clave.

    POR QUE HACE FALTA:
      El formulario buscaba con `AR_SUCU + AR_CODI` contra el tag de
      ROT_ARTIC, pero calcular_rotacion.prg declara `ROT_ARTIC C(7)` y lo
      llena con DCC_ARTICU, y despues valida con SEEK contra el tag AR_CODI
      (o sea, contra el codigo solo).

      Las dos cosas solo pueden ser ciertas a la vez si AR_SUCU + AR_CODI
      miden 7 en total. Como no se puede saber sin ver la estructura real
      de las tablas, se prueban las dos formas: primero la clave completa,
      despues el codigo solo.

      Esto no es una red por las dudas: si se elige mal, el cruce falla en
      silencio para TODO el catalogo y cada articulo termina descartado por
      "sin ventas registradas", con la lista de compra vacia y sin ningun
      mensaje de error. El informe reporta cual de las dos enganho.
    """
    registro = demanda.get(articulo.clave)
    if registro is not None:
        return registro
    if articulo.clave_corta != articulo.clave:
        return demanda.get(articulo.clave_corta)
    return None


def normalizar_clave(valor: Any) -> str:
    """Clave de articulo canonica: sin espacios de relleno.

    En VFP la clave se armaba concatenando los campos crudos (AR_SUCU +
    AR_CODI) y el SEEK contra el CDX matcheaba por prefijo, asi que el
    relleno con espacios no molestaba. Un diccionario de Python compara
    la cadena completa: "1ABC12" y "1ABC12  " serian dos claves distintas
    y el cruce contra ROTACION fallaria en silencio, mandando articulos con
    ventas al descarte por "sin ventas registradas".

    Sacar TODOS los espacios deja las dos puntas del cruce en la misma
    forma, vengan como vengan de cada tabla.
    """
    if valor is None:
        return ""
    return str(valor).replace(" ", "")


def clave_articulo(sucursal: Any, codigo: Any) -> str:
    return normalizar_clave(f"{sucursal or ''}{codigo or ''}")


def _igual_estricto(izquierda: Any, derecha: Any) -> bool:
    return str(izquierda or "").rstrip() == str(derecha or "").rstrip()


def _primer_campo(tabla: TablaDBF, candidatos: list[str]) -> str | None:
    for nombre in candidatos:
        if tabla.tiene(nombre):
            return nombre.upper()
    return None


def _primer_texto_largo(tabla: TablaDBF) -> str | None:
    """Heuristica de ultimo recurso para el nombre: el campo C mas ancho."""
    mejor = None
    for campo in tabla.campos:
        if campo.tipo == "C" and campo.largo >= 15:
            if mejor is None or campo.largo > mejor.largo:
                mejor = campo
    return mejor.nombre if mejor else None


def _primer_texto_corto(tabla: TablaDBF, excluir: str | None) -> str | None:
    """Heuristica de ultimo recurso para el codigo: primer campo C angosto."""
    for campo in tabla.campos:
        if campo.tipo == "C" and campo.largo <= 10 and campo.nombre != excluir:
            return campo.nombre
    return None


def _texto_codigo(codigo: Any) -> str:
    """El codigo como cadena, venga como venga de la tabla.

    PR_CODIGO es un campo NUMERICO, asi que el lector lo devuelve como int.
    Sin esta conversion, 232 se convertiria en "232" por str() pero
    232.0 en "232.0", que no engancharia con nada.
    """
    if codigo is None:
        return ""
    if isinstance(codigo, float):
        if codigo == int(codigo):
            return str(int(codigo))
        return str(codigo)
    if isinstance(codigo, int):
        return str(codigo)
    return alltrim(codigo)


def clave_proveedor(sucursal: Any, codigo: Any) -> str:
    """Arma la clave de 7 caracteres con la que AR_PROV referencia a PROVEEDO.

    ESTE ES EL PUNTO MAS SUTIL DEL CRUCE, y estuvo mal hasta que aparecio la
    estructura real de la tabla.

    PROVEEDO no guarda el codigo como texto:

        PR_SUCURS  Character(1)
        PR_CODIGO  Numeric(6)     <-- NUMERICO

    y ARTICULO.AR_PROV es Character(7). El puente entre los dos es la misma
    regla que aplica Form.NormalizarProv del formulario original:

        IF LEN(lcCod) <> 7
            lcCod = "1" + PADL(lcCod, 6)
        ENDIF

    O sea, la clave es la sucursal pegada adelante del codigo justificado a
    la derecha en 6 lugares CON ESPACIOS. El proveedor 232 de la sucursal 1
    es "1   232", no "232" ni "1000232".

    Es lo mismo que hace STR(PR_CODIGO, 6) en el tag COD_ALFA del CDX, que
    es contra lo que el formulario hacia SEEK sin nombrar nunca el campo.

    Armar la clave como "232    " (que es lo que sale de un PADR ingenuo)
    hace que NINGUN proveedor enganche, y la lista entera sale con el nombre
    "[codigo] no esta en PROVEEDO".
    """
    texto = _texto_codigo(codigo)
    if not texto:
        return "*SINPRO"

    # Un codigo que ya mide 7 o mas viene con la clave completa adentro
    if len(texto) >= 7:
        return padr(texto, 7)

    prefijo = alltrim(sucursal) or "1"    # NormalizarProv hardcodea el "1"
    return padr(prefijo[:1] + texto.rjust(6), 7)


def normalizar_proveedor(codigo: Any) -> str:
    """Port literal de Form.NormalizarProv.

    Regla del formulario original: un codigo que no mide 7 caracteres se
    reescribe como "1" + PADL(codigo, 6). O sea "232" -> "1   232".
    Los articulos sin proveedor se agrupan bajo la clave *SINPRO.
    """
    limpio = alltrim(codigo)
    if not limpio:
        return "*SINPRO"
    if len(limpio) != 7:
        limpio = "1" + limpio.rjust(6)
    return padr(limpio, 7)


def nombre_proveedor(
    codigo_normalizado: str,
    proveedores: dict[str, str],
    respaldo: dict[str, str] | None = None,
) -> str:
    """Port de Form.NombreProveedor, con un respaldo que el original no tenia.

    Si la clave normalizada no aparece, el original reintenta sacandole el
    primer caracter al codigo sin espacios ("1232" -> "232"), por si AR_PROV
    guarda el codigo sin normalizar.

    EL RESPALDO NUEVO:
      ARTICULO trae DESC_PROV, el nombre del proveedor denormalizado en la
      propia ficha del articulo. El formulario original nunca lo usaba
      porque siempre tenia PROVEEDO abierta con su CDX.

      Aca sirve de red: la columna que guarda el codigo en PROVEEDO se
      detecta por heuristica (el formulario hacia SEEK contra un tag y nunca
      nombraba el campo), asi que si esa deteccion falla, en vez de mostrar
      una lista entera de "[codigo] no esta en PROVEEDO" se cae al nombre
      que ya viene en el articulo.
    """
    if codigo_normalizado == "*SINPRO":
        return "(sin proveedor asignado)"

    nombre = proveedores.get(codigo_normalizado)
    if nombre:
        return nombre

    nombre = proveedores.get(alltrim(codigo_normalizado))
    if nombre:
        return nombre

    crudo = alltrim(codigo_normalizado).replace(" ", "")
    if len(crudo) > 1:
        nombre = proveedores.get(crudo[1:])
        if nombre:
            return nombre

    if respaldo:
        nombre = respaldo.get(codigo_normalizado)
        if nombre:
            return nombre

    return f"[{alltrim(codigo_normalizado)}] no esta en PROVEEDO"
