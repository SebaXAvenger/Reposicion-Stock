"""
Port de calcular_rotacion.prg

Genera ROTACION.DBF con el consumo mensual por articulo Y POR ORIGEN, para
que el selector Local / Todas las Sucursales pueda gobernar el stock y la
demanda en forma coherente.

LEE (solo lectura):
    sis_path_\\DOCUM + DOCCUER   ->  origen "L"  (blanco de esta sucursal)
    sis_path2\\DOCUM + DOCCUER   ->  origen "R"  (blanco de la otra)
    zip_path_\\DOCUM + DOCCUER   ->  se reparte por DOC_SUCURS

ESCRIBE:  sis_path_\\ROTACION.DBF

La fecha SIEMPRE sale de DOCUM.DOC_FECEMI a traves de DCC_CLAVE_, porque
DCC_FECHA_ esta vacio en la enorme mayoria de los renglones.

--------------------------------------------------------------------------
TRES DECISIONES QUE NO SON MECANICAS. Ver el detalle mas abajo:

  1. Los remitos internos (RI). El PRG original define DOS VECES el
     procedimiento ProcesarFuente, con criterios opuestos, y VFP usa el
     primero. Ver `TIPOS_BASE` y `remitos_internos_son_venta`.

  2. El ancho de ROT_ARTIC. El PRG lo fija en C(7) a mano; aca se toma del
     dato real para no truncar claves en silencio.

  3. El perfil estacional (ROT_EST01..ROT_EST12 + ROT_ESTHIS). No existe en
     el PRG: es lo que permite que el calculo de compra tenga en cuenta las
     temporadas. Ver `_estadisticas`.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import datetime
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config import Parametros, resolver_archivo
from .dbf import ErrorDBF, TablaDBF
from .dbf_escritor import ErrorEscritura, TablaEnUso, escribir_tabla
from .vfp import alltrim, igual_exact_off, num

# --------------------------------------------------------------------------
# Comprobantes que cuentan como movimiento de mercaderia
# --------------------------------------------------------------------------
# FC/FE facturas, ND nota de debito, DE ¿debito especial?, y NC/CE que
# restan (notas de credito y devoluciones).
TIPOS_BASE = {"FC", "FE", "ND", "DE", "NC", "CE"}

# Los que restan del consumo en vez de sumar.
TIPOS_NEGATIVOS = {"NC", "CE"}

# --------------------------------------------------------------------------
# REMITOS INTERNOS: la decision que hay que tomar a conciencia
# --------------------------------------------------------------------------
# calcular_rotacion.prg declara ProcesarFuente dos veces en el mismo archivo,
# con el mismo nombre y criterios OPUESTOS:
#
#   linea 375 (la que usa VFP, por ser la primera):
#       INLIST(DOC_TIPDOC, "FC","FE","RI","ND","DE","NC","CE")   -> RI CUENTA
#
#   linea 521 (nunca se ejecuta):
#       INLIST(DOC_TIPDOC, "FC","FE","ND","DE","NC","CE")
#       OR (llRIesVenta AND DOC_TIPDOC = "RI")   con llRIesVenta = .F.
#
# La segunda version trae ademas este comentario, que explica por que la
# primera esta mal:
#
#   "Un remito interno mueve mercaderia de un deposito al otro: baja el
#    stock del que provee, pero NO es una venta. Contarlo como consumo
#    infla la demanda de la sucursal que abastece a la otra, y en modo
#    consolidado suma demanda que la empresa nunca tuvo. La entrada en
#    destino queda ademas fuera del filtro DOC_CLIPRO='C', asi que ni
#    siquiera se compensa."
#
# O sea: alguien detecto el problema, escribio la correccion, y la
# correccion quedo muerta porque VFP resuelve el nombre duplicado con la
# primera definicion.
#
# El programa deja la eleccion en manos del usuario, con el valor por
# defecto en la version corregida (RI NO es venta). Ojo: eso hace que los
# numeros NO coincidan con los que produce el ERP hoy.
TIPO_REMITO_INTERNO = "RI"

# Meses del principio de la ventana que se usan para saber si un articulo ya
# existia o es nuevo. No entran al perfil estacional: ver `_estadisticas`.
MESES_SONDEO = 3


@dataclass
class OpcionesRotacion:
    """Los parametros que el formulario pasaba en `DO calcular_rotacion`."""

    # El formulario llama con 24; el PRG documenta 12 como default y la
    # ayuda en pantalla habla de "los ultimos 12 meses completos".
    # Se respeta lo que hace el codigo, no lo que dice la ayuda.
    meses: int = 24
    incluir_pendrive: bool = True        # tlNegro
    incluir_remoto: bool = True          # tlRemoto
    remitos_internos_son_venta: bool = False
    # Fecha de referencia para la ventana. None = hoy. Se fija en las
    # pruebas para que no dependan del dia en que se corren.
    hoy: datetime.date | None = None

    def tipos_documento(self) -> set[str]:
        tipos = set(TIPOS_BASE)
        if self.remitos_internos_son_venta:
            tipos.add(TIPO_REMITO_INTERNO)
        return tipos


@dataclass
class FuenteLeida:
    """Resultado de recorrer un par DOCUM + DOCCUER."""

    rotulo: str
    ruta: Path
    disponible: bool = False
    comprobantes: int = 0
    renglones: int = 0
    claves_duplicadas: int = 0
    por_sucursal: dict[str, int] = field(default_factory=dict)
    # (articulo, sucursal, mes) -> [unidades, primera_venta, ultima_venta]
    acumulado: dict[tuple[str, str, str], list] = field(default_factory=dict)
    mensaje: str = ""


@dataclass
class ResultadoRotacion:
    ok: bool = False
    mensaje: str = ""
    ruta: Path | None = None
    filas: int = 0
    articulos_por_origen: dict[str, int] = field(default_factory=dict)
    unidades_por_origen: dict[str, float] = field(default_factory=dict)
    enganchan_con_articulo: int = 0
    unidades_sin_sucursal: float = 0.0
    desde: datetime.date | None = None
    hasta: datetime.date | None = None
    duracion: float = 0.0
    ancho_clave: int = 7
    informe: list[str] = field(default_factory=list)
    ruta_informe: Path | None = None

    def texto_informe(self) -> str:
        return "\n".join(self.informe)


Progreso = Callable[[str, int], None]


# ==========================================================================

class CalculadorRotacion:
    def __init__(
        self,
        parametros: Parametros,
        opciones: OpcionesRotacion | None = None,
        progreso: Progreso | None = None,
    ):
        self.p = parametros
        self.o = opciones or OpcionesRotacion()
        self._progreso = progreso or (lambda _texto, _pct: None)
        self._informe: list[str] = []

    # -- utilidades ------------------------------------------------------

    def _inf(self, texto: str = "") -> None:
        self._informe.append(texto)

    def _avisar(self, texto: str, porcentaje: int) -> None:
        self._progreso(texto, porcentaje)

    # -- ventana de analisis ---------------------------------------------

    def ventana(self, hoy: datetime.date | None = None) -> tuple[datetime.date, datetime.date]:
        """Solo meses COMPLETOS.

        El mes en curso esta a medias: incluirlo bajaria el promedio.

            hasta  = ultimo dia del mes anterior
            desde  = primer dia, `meses` - 1 meses antes de ese
        """
        hoy = hoy or datetime.date.today()
        hasta = hoy.replace(day=1) - datetime.timedelta(days=1)

        anio = hasta.year
        mes = hasta.month - (self.o.meses - 1)
        while mes <= 0:
            mes += 12
            anio -= 1
        desde = datetime.date(anio, mes, 1)
        return desde, hasta

    # -- corrida completa ------------------------------------------------

    def calcular(self) -> ResultadoRotacion:
        inicio = time.perf_counter()
        resultado = ResultadoRotacion()

        problemas = self._validar()
        if problemas:
            resultado.mensaje = "\n".join(problemas)
            return resultado

        desde, hasta = self.ventana(self.o.hoy)
        resultado.desde, resultado.hasta = desde, hasta
        sucursal = alltrim(self.p.sucursal)

        self._inf("=" * 68)
        self._inf(
            "CALCULO DE ROTACION - "
            + datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        )
        self._inf("=" * 68)
        self._inf(f"Sucursal local     : [{sucursal}]")
        self._inf(
            f"Ventana analizada  : {desde.strftime('%d/%m/%Y')} a "
            f"{hasta.strftime('%d/%m/%Y')}  ({self.o.meses} meses)"
        )
        self._inf(
            "Remitos internos   : "
            + ("INCLUIDOS como venta" if self.o.remitos_internos_son_venta
               else "excluidos (no son venta)")
        )
        self._inf()

        # --- 2. Fuentes -------------------------------------------------
        self._avisar("Leyendo el blanco local...", 5)
        local = self._leer_fuente(
            Path(self.p.carpeta_datos), "BLANCO LOCAL", desde, hasta, 5, 35
        )
        if not local.disponible:
            resultado.mensaje = (
                "No se encontraron DOCUM/DOCCUER en la carpeta de datos "
                f"principal:\n{self.p.carpeta_datos}\n\n"
                "Sin el blanco local no hay nada que calcular."
            )
            resultado.informe = self._informe
            return resultado

        remoto = FuenteLeida("BLANCO REMOTO", Path(self.p.carpeta_datos2 or ""))
        if self.o.incluir_remoto and self.p.carpeta_datos2:
            self._avisar("Leyendo el blanco de la otra sucursal...", 38)
            remoto = self._leer_fuente(
                Path(self.p.carpeta_datos2), "BLANCO REMOTO", desde, hasta, 38, 58
            )

        pendrive = FuenteLeida("PENDRIVE", Path(self.p.carpeta_zip or ""))
        if self.o.incluir_pendrive and self.p.carpeta_zip:
            self._avisar("Leyendo el pendrive...", 60)
            pendrive = self._leer_fuente(
                Path(self.p.carpeta_zip), "PENDRIVE", desde, hasta, 60, 78
            )

        # --- 3. Consolidar asignando origen -----------------------------
        self._avisar("Consolidando origenes...", 80)
        consolidado, unidades_sin_sucursal = self._consolidar(
            local, remoto, pendrive, sucursal
        )
        resultado.unidades_sin_sucursal = unidades_sin_sucursal

        if not consolidado:
            resultado.mensaje = (
                "No se obtuvo ningun movimiento de venta en la ventana analizada."
            )
            resultado.informe = self._informe
            return resultado

        # --- 4. Estadisticas por articulo y origen ----------------------
        self._avisar("Calculando rotacion...", 85)
        filas = self._estadisticas(consolidado, desde, hasta)

        if not filas:
            resultado.mensaje = (
                "No quedo ningun articulo con movimiento. No se genero la tabla."
            )
            resultado.informe = self._informe
            return resultado

        # --- 5. Volcar a ROTACION.DBF ------------------------------------
        self._avisar("Grabando ROTACION.DBF...", 92)
        ancho = max(7, max(len(f["ROT_ARTIC"]) for f in filas))
        resultado.ancho_clave = ancho
        if ancho > 7:
            self._inf(
                f"  NOTA: la clave de articulo mide {ancho} caracteres, no 7. "
                f"ROT_ARTIC se ensancha para no truncarla."
            )

        destino = Path(self.p.carpeta_datos) / "ROTACION.DBF"
        try:
            ruta, cantidad = escribir_tabla(
                destino, self._estructura(ancho), filas,
                codepage=self.p.codepage if self.p.codepage != "auto" else "cp1252",
            )
        except TablaEnUso as error:
            resultado.mensaje = str(error)
            resultado.informe = self._informe
            return resultado
        except ErrorEscritura as error:
            resultado.mensaje = str(error)
            resultado.informe = self._informe
            return resultado

        resultado.ruta = ruta
        resultado.filas = cantidad

        # --- 6. Validacion contra ARTICULO -------------------------------
        self._avisar("Validando claves contra ARTICULO...", 96)
        resultado.enganchan_con_articulo = self._validar_contra_articulo(filas)

        # --- 7. Informe ---------------------------------------------------
        self._resumen(resultado, filas, local, remoto, pendrive)
        resultado.ruta_informe = self._guardar_informe()

        resultado.informe = self._informe
        resultado.ok = True
        resultado.duracion = time.perf_counter() - inicio
        self._avisar("Listo.", 100)
        return resultado

    # -- validaciones ----------------------------------------------------

    def _validar(self) -> list[str]:
        problemas: list[str] = []

        if not self.p.carpeta_datos:
            problemas.append("Falta la carpeta de datos principal (sis_path_).")
        elif not Path(self.p.carpeta_datos).is_dir():
            problemas.append(f"No existe la carpeta {self.p.carpeta_datos}")

        if not alltrim(self.p.sucursal):
            problemas.append(
                "Falta el codigo de sucursal (sis_sucurs). Sin el no se puede "
                "repartir el pendrive entre sucursales."
            )

        if self.o.meses < 1 or self.o.meses > 120:
            problemas.append("La cantidad de meses tiene que estar entre 1 y 120.")

        if self.o.incluir_pendrive and not self.p.carpeta_zip:
            self._inf(
                "AVISO: se pidio incluir el pendrive pero zip_path_ no esta "
                "configurada. Se continua sin esa fuente."
            )
        if self.o.incluir_remoto and not self.p.carpeta_datos2:
            self._inf(
                "AVISO: se pidio incluir la otra sucursal pero sis_path2 no "
                "esta configurada. Se continua sin esa fuente."
            )

        return problemas

    # -- lectura de una fuente -------------------------------------------

    def _leer_fuente(
        self,
        carpeta: Path,
        rotulo: str,
        desde: datetime.date,
        hasta: datetime.date,
        pct_ini: int,
        pct_fin: int,
    ) -> FuenteLeida:
        fuente = FuenteLeida(rotulo, carpeta)

        ruta_docum = resolver_archivo(carpeta / "DOCUM.DBF")
        ruta_cuerpo = resolver_archivo(carpeta / "DOCCUER.DBF")

        if not ruta_docum.is_file() or not ruta_cuerpo.is_file():
            self._inf(f"--- {rotulo} ({carpeta}) : NO DISPONIBLE ---")
            fuente.mensaje = f"No se encontraron DOCUM/DOCCUER en {carpeta}"
            return fuente

        try:
            cabeceras, duplicadas, por_sucursal = self._leer_cabeceras(
                ruta_docum, desde, hasta
            )
        except ErrorDBF as error:
            self._inf(f"--- {rotulo} ({carpeta}) : ERROR ---")
            self._inf(f"  {error}")
            fuente.mensaje = str(error)
            return fuente

        fuente.disponible = True
        fuente.comprobantes = sum(
            len(v) if isinstance(v, list) else 1 for v in cabeceras.values()
        )
        fuente.claves_duplicadas = duplicadas
        fuente.por_sucursal = por_sucursal

        self._inf(f"--- {rotulo} ({carpeta}) ---")
        self._inf(
            "  Remitos internos (RI) : "
            + ("INCLUIDOS" if self.o.remitos_internos_son_venta else "excluidos")
        )
        self._inf(f"  Comprobantes en la ventana : {fuente.comprobantes:,}")
        for sucursal, cuantos in sorted(por_sucursal.items()):
            self._inf(f"    DOC_SUCURS [{sucursal}] : {cuantos:,}")
        if duplicadas:
            self._inf(f"    ATENCION: {duplicadas:,} DOC_CLAVE_ duplicadas")

        if not cabeceras:
            self._inf("  Renglones agrupados : 0")
            return fuente

        self._avisar(f"Leyendo renglones de {rotulo.lower()}...", (pct_ini + pct_fin) // 2)
        fuente.acumulado, fuente.renglones = self._leer_renglones(
            ruta_cuerpo, cabeceras
        )
        self._inf(f"  Renglones agrupados : {len(fuente.acumulado):,}")
        self._inf(f"  Renglones leidos    : {fuente.renglones:,}")
        self._inf()
        return fuente

    def _leer_cabeceras(
        self, ruta: Path, desde: datetime.date, hasta: datetime.date
    ) -> tuple[dict[str, Any], int, dict[str, int]]:
        """DOCUM filtrado: clientes, no anuladas, en ventana, tipo que cuenta.

        Devuelve clave -> (mes, signo, sucursal, fecha), o una LISTA de esas
        tuplas cuando la clave aparece repetida.

        POR QUE UNA LISTA PARA LAS REPETIDAS:
          El PRG hace un INNER JOIN. Si DOC_CLAVE_ esta duplicada, el join
          emite un renglon por cada cabecera que matchea, o sea que las
          cantidades se multiplican. Guardar solo la ultima daria numeros
          distintos a los del ERP. Se reproduce el comportamiento del join,
          y la cantidad de duplicadas se informa aparte, como hacia el PRG.
        """
        tipos = self.o.tipos_documento()
        campos = [
            "DOC_CLAVE_", "DOC_FECEMI", "DOC_TIPDOC", "DOC_SUCURS",
            "DOC_CLIPRO", "DOC_ANULED",
        ]

        cabeceras: dict[str, Any] = {}
        duplicadas = 0
        por_sucursal: dict[str, int] = {}

        with TablaDBF(ruta, codepage=self.p.codepage) as tabla:
            faltantes = [c for c in campos if not tabla.tiene(c)]
            if faltantes:
                raise ErrorDBF(
                    f"{ruta.name} no tiene los campos que necesita el calculo: "
                    + ", ".join(faltantes)
                    + f"\nCampos disponibles: {', '.join(tabla.nombres)}"
                )

            for clave, fecha, tipo, sucursal, clipro, anulada in tabla.tuplas(campos):
                # WHERE DOC_CLIPRO = "C"  (bajo SET EXACT OFF)
                if not igual_exact_off(clipro, "C"):
                    continue
                if anulada:                     # AND NOT DOC_ANULED
                    continue
                if not fecha or fecha < desde or fecha > hasta:
                    continue
                if alltrim(tipo).upper() not in tipos:
                    continue

                llave = alltrim(clave)
                if not llave:
                    continue

                signo = -1.0 if alltrim(tipo).upper() in TIPOS_NEGATIVOS else 1.0
                dato = (
                    f"{fecha.year:04d}{fecha.month:02d}",
                    signo,
                    (sucursal or ""),
                    fecha,
                )

                existente = cabeceras.get(llave)
                if existente is None:
                    cabeceras[llave] = dato
                elif isinstance(existente, list):
                    existente.append(dato)
                else:
                    duplicadas += 1
                    cabeceras[llave] = [existente, dato]

                etiqueta = alltrim(sucursal) or "(vacio)"
                por_sucursal[etiqueta] = por_sucursal.get(etiqueta, 0) + 1

        return cabeceras, duplicadas, por_sucursal

    def _leer_renglones(
        self, ruta: Path, cabeceras: dict[str, Any]
    ) -> tuple[dict[tuple[str, str, str], list], int]:
        """DOCCUER cruzado contra las cabeceras que pasaron el filtro."""
        campos = ["DCC_CLAVE_", "DCC_ARTICU", "DCC_CANTID"]
        acumulado: dict[tuple[str, str, str], list] = {}
        leidos = 0

        with TablaDBF(ruta, codepage=self.p.codepage) as tabla:
            faltantes = [c for c in campos if not tabla.tiene(c)]
            if faltantes:
                raise ErrorDBF(
                    f"{ruta.name} no tiene: " + ", ".join(faltantes)
                    + f"\nCampos disponibles: {', '.join(tabla.nombres)}"
                )

            obtener = cabeceras.get
            for clave, articulo, cantidad in tabla.tuplas(campos):
                leidos += 1
                articulo = alltrim(articulo)
                if not articulo:                 # WHERE NOT EMPTY(DCC_ARTICU)
                    continue

                cabecera = obtener(alltrim(clave))
                if cabecera is None:
                    continue

                unidades = num(cantidad)
                grupo = cabecera if isinstance(cabecera, list) else (cabecera,)
                for mes, signo, sucursal, fecha in grupo:
                    llave = (articulo, sucursal, mes)
                    entrada = acumulado.get(llave)
                    if entrada is None:
                        acumulado[llave] = [unidades * signo, fecha, fecha]
                    else:
                        entrada[0] += unidades * signo
                        if fecha < entrada[1]:
                            entrada[1] = fecha
                        if fecha > entrada[2]:
                            entrada[2] = fecha

        return acumulado, leidos

    # -- consolidacion ----------------------------------------------------

    def _consolidar(
        self,
        local: FuenteLeida,
        remoto: FuenteLeida,
        pendrive: FuenteLeida,
        sucursal: str,
    ) -> tuple[dict[tuple[str, str, str], list], float]:
        """Asigna origen L / R a cada movimiento.

        - Blanco local:  todo es de esta sucursal, sin importar DOC_SUCURS.
        - Blanco remoto: todo es de la otra.
        - Pendrive:      se reparte por DOC_SUCURS. Los comprobantes con
                         DOC_SUCURS vacio van a la sucursal local, que es el
                         criterio conservador del PRG, y se informa cuantas
                         unidades fueron.
        """
        consolidado: dict[tuple[str, str, str], list] = {}

        def sumar(clave_articulo: str, origen: str, mes: str, datos: list) -> None:
            llave = (clave_articulo, origen, mes)
            entrada = consolidado.get(llave)
            if entrada is None:
                consolidado[llave] = [datos[0], datos[1], datos[2]]
            else:
                entrada[0] += datos[0]
                if datos[1] and (not entrada[1] or datos[1] < entrada[1]):
                    entrada[1] = datos[1]
                if datos[2] and (not entrada[2] or datos[2] > entrada[2]):
                    entrada[2] = datos[2]

        for (articulo, _suc, mes), datos in local.acumulado.items():
            sumar(articulo, "L", mes, datos)

        for (articulo, _suc, mes), datos in remoto.acumulado.items():
            sumar(articulo, "R", mes, datos)

        unidades_sin_sucursal = 0.0
        for (articulo, suc, mes), datos in pendrive.acumulado.items():
            vacia = not alltrim(suc)
            if vacia:
                unidades_sin_sucursal += datos[0]
            # IIF(EMPTY(cSuc) OR cSuc = lcMine, "L", "R"), con `=` de EXACT OFF
            origen = "L" if (vacia or igual_exact_off(suc, sucursal)) else "R"
            sumar(articulo, origen, mes, datos)

        return consolidado, unidades_sin_sucursal

    # -- estadisticas ------------------------------------------------------

    def _estadisticas(
        self,
        consolidado: dict[tuple[str, str, str], list],
        desde: datetime.date,
        hasta: datetime.date,
    ) -> list[dict[str, Any]]:
        """Una fila por (articulo, origen), con el detalle mensual resumido."""
        meses = self.o.meses
        anio_ini, mes_ini = desde.year, desde.month
        hoy = datetime.date.today()
        negro = bool(self.o.incluir_pendrive and self.p.carpeta_zip)

        # (articulo, origen) -> [buckets, primera, ultima]
        grupos: dict[tuple[str, str], list] = {}

        for (articulo, origen, mes), datos in consolidado.items():
            indice = (
                (int(mes[:4]) - anio_ini) * 12 + int(mes[4:6]) - mes_ini
            )
            if indice < 0 or indice >= meses:
                continue

            grupo = grupos.get((articulo, origen))
            if grupo is None:
                grupo = [[0.0] * meses, None, None]
                grupos[(articulo, origen)] = grupo

            grupo[0][indice] += datos[0]
            if datos[1] and (grupo[1] is None or datos[1] < grupo[1]):
                grupo[1] = datos[1]
            if datos[2] and (grupo[2] is None or datos[2] > grupo[2]):
                grupo[2] = datos[2]

        filas: list[dict[str, Any]] = []
        for (articulo, origen), (baldes, primera, ultima) in grupos.items():
            # Una devolucion mayor a la venta del mes daria negativo:
            # se acota en 0, igual que GrabarArticulo.
            acotados = [balde if balde > 0 else 0.0 for balde in baldes]
            total = sum(acotados)
            if total <= 0:
                continue

            con_venta = sum(1 for balde in acotados if balde > 0)
            promedio = total / meses

            # La mediana se calcula sobre TODOS los meses, incluidos los de
            # venta cero. Por eso es mas conservadora: un articulo que
            # vendio mucho un solo mes tiene mediana 0 y no se sugiere.
            ordenados = sorted(acotados)
            maximo = ordenados[-1]
            if meses % 2 == 1:
                mediana = ordenados[(meses - 1) // 2]
            else:
                mediana = (ordenados[meses // 2 - 1] + ordenados[meses // 2]) / 2

            # --- Perfil estacional ------------------------------------
            # Venta PROMEDIO de cada mes calendario (enero..diciembre), para
            # que el calculo de compra sepa que meses vienen fuertes y cuales
            # flojos.
            #
            # DESDE CUANDO se cuenta:
            #   Los primeros MESES_SONDEO meses de la ventana se usan SOLO
            #   para decidir si el articulo ya existia, y NO entran al
            #   perfil:
            #   - Vendio en alguno de ellos: ya existia. El perfil arranca
            #     despues del sondeo y los meses en cero son temporada baja
            #     de verdad.
            #   - No vendio: es nuevo. Los meses anteriores no son
            #     "temporada baja", son meses en los que no existia. El
            #     perfil arranca el mes SIGUIENTE a la primera venta.
            #
            #   POR QUE NO SE USA EL MES QUE DECIDE: ese mes tiene venta por
            #   definicion. Si entrara al perfil, en los articulos de poca
            #   venta ese mes del anio saldria inflado y apareceria una
            #   "temporada" que no existe. Se comprobo con datos de venta
            #   pareja: incluyendolo, septiembre a noviembre daban el doble.
            #
            # ROT_ESTHIS guarda cuantos meses de historia tiene el perfil.
            # Con menos de 12 no estan todos los meses del anio y el calculo
            # de compra no usa el perfil propio del articulo (cae al rubro).
            # Por eso la estacionalidad necesita recalcular con 15 meses o
            # mas (el valor por defecto es 24).
            primer_mes = next(i for i, balde in enumerate(acotados) if balde > 0)
            if primer_mes < MESES_SONDEO:
                inicio = MESES_SONDEO
            else:
                inicio = primer_mes + 1
            historia = max(meses - inicio, 0)
            suma_mes = [0.0] * 12
            veces_mes = [0] * 12
            for indice in range(inicio, meses):
                calendario = (mes_ini - 1 + indice) % 12     # 0 = enero
                suma_mes[calendario] += acotados[indice]
                veces_mes[calendario] += 1
            perfil = [
                suma_mes[m] / veces_mes[m] if veces_mes[m] else 0.0
                for m in range(12)
            ]

            fila = {
                "ROT_ARTIC": articulo,
                "ROT_ORIGE": origen,
                "ROT_DESDE": desde,
                "ROT_HASTA": hasta,
                "ROT_MESES": meses,
                "ROT_UNIDS": total,
                "ROT_PROME": promedio,
                "ROT_MEDIA": mediana,
                "ROT_MAXMES": maximo,
                "ROT_MESCON": con_venta,
                "ROT_PRIVTA": primera,
                "ROT_ULTVTA": ultima,
                "ROT_NEGRO": negro,
                "ROT_FECCAL": hoy,
                "ROT_ESTHIS": historia,
            }
            for m in range(12):
                fila[f"ROT_EST{m + 1:02d}"] = perfil[m]
            filas.append(fila)

        # Mismo orden que dejaba el INDEX ON ROT_ARTIC + ROT_ORIGE
        filas.sort(key=lambda f: (f["ROT_ARTIC"], f["ROT_ORIGE"]))
        return filas

    # -- estructura de salida ----------------------------------------------

    @staticmethod
    def _estructura(ancho_clave: int) -> list[tuple[str, str, int, int]]:
        """La misma que armaba el CREATE CURSOR curRot del PRG."""
        return [
            ("ROT_ARTIC", "C", ancho_clave, 0),
            ("ROT_ORIGE", "C", 1, 0),
            ("ROT_DESDE", "D", 8, 0),
            ("ROT_HASTA", "D", 8, 0),
            ("ROT_MESES", "N", 4, 0),
            ("ROT_UNIDS", "N", 14, 3),
            ("ROT_PROME", "N", 12, 3),
            ("ROT_MEDIA", "N", 12, 3),
            ("ROT_MAXMES", "N", 12, 3),
            ("ROT_MESCON", "N", 4, 0),
            ("ROT_PRIVTA", "D", 8, 0),
            ("ROT_ULTVTA", "D", 8, 0),
            ("ROT_NEGRO", "L", 1, 0),
            ("ROT_FECCAL", "D", 8, 0),
            # Perfil estacional: meses de historia + venta promedio de cada
            # mes calendario (01 = enero ... 12 = diciembre). Van al final
            # para no mover ninguna columna que ya existia.
            ("ROT_ESTHIS", "N", 4, 0),
        ] + [(f"ROT_EST{m:02d}", "N", 12, 3) for m in range(1, 13)]

    # -- validacion contra ARTICULO ----------------------------------------

    def _validar_contra_articulo(self, filas: list[dict[str, Any]]) -> int:
        """Cuantas claves de ROTACION existen en ARTICULO.

        El PRG hacia SEEK contra el tag AR_CODI. Aca se arma un conjunto con
        las dos formas posibles de la clave (el codigo solo y la sucursal
        pegada adelante) porque no esta claro cual de las dos guarda
        DCC_ARTICU. Si el porcentaje de enganche sale bajo, el informe lo
        muestra y es la senial de que la clave no es la que se penso.
        """
        ruta = resolver_archivo(Path(self.p.carpeta_datos) / "ARTICULO.DBF")
        if not ruta.is_file():
            return 0

        claves: set[str] = set()
        try:
            with TablaDBF(ruta, codepage=self.p.codepage) as tabla:
                campos = [c for c in ("AR_SUCU", "AR_CODI") if tabla.tiene(c)]
                if "AR_CODI" not in campos:
                    return 0
                for fila in tabla.tuplas(campos):
                    if len(fila) == 2:
                        sucursal, codigo = fila
                        claves.add(alltrim(codigo))
                        claves.add(f"{sucursal or ''}{codigo or ''}".replace(" ", ""))
                    else:
                        claves.add(alltrim(fila[0]))
        except ErrorDBF:
            return 0

        return sum(
            1 for f in filas
            if f["ROT_ARTIC"] in claves or f["ROT_ARTIC"].replace(" ", "") in claves
        )

    # -- informe ------------------------------------------------------------

    def _resumen(
        self,
        resultado: ResultadoRotacion,
        filas: list[dict[str, Any]],
        *fuentes: FuenteLeida,
    ) -> None:
        for fila in filas:
            origen = fila["ROT_ORIGE"]
            resultado.articulos_por_origen[origen] = (
                resultado.articulos_por_origen.get(origen, 0) + 1
            )
            resultado.unidades_por_origen[origen] = (
                resultado.unidades_por_origen.get(origen, 0.0) + fila["ROT_UNIDS"]
            )

        self._inf()
        self._inf("--- RESULTADO ---")
        for origen in sorted(resultado.articulos_por_origen):
            self._inf(
                f"  Origen [{origen}] : "
                f"{resultado.articulos_por_origen[origen]:>7,} articulos, "
                f"{resultado.unidades_por_origen[origen]:>18,.3f} unidades"
            )

        # Cuantas filas tienen perfil estacional completo (12+ meses de
        # historia). Las demas usan el perfil de su rubro al calcular la compra.
        con_perfil = sum(1 for fila in filas if fila["ROT_ESTHIS"] >= 12)

        self._inf()
        self._inf(f"  Filas totales en ROTACION.DBF : {resultado.filas:,}")
        self._inf(
            f"  Con perfil estacional propio (12+ meses de historia) : "
            f"{con_perfil:,}"
        )
        if self.o.meses < 12 + MESES_SONDEO:
            self._inf(
                f"    ATENCION: con menos de {12 + MESES_SONDEO} meses de "
                "ventana ningun articulo puede tener perfil estacional propio. "
                "Conviene recalcular con 24."
            )
        porcentaje = (
            resultado.enganchan_con_articulo / resultado.filas * 100
            if resultado.filas else 0.0
        )
        self._inf(
            f"  Claves que enganchan con ARTICULO : "
            f"{resultado.enganchan_con_articulo:,}  ({porcentaje:.1f}%)"
        )
        if porcentaje < 90:
            self._inf(
                "    ATENCION: un enganche bajo suele significar que "
                "DCC_ARTICU no guarda la misma clave que ARTICULO."
            )

        duplicadas = " / ".join(
            f"{f.claves_duplicadas:,} {f.rotulo.split()[-1].lower()}"
            for f in fuentes if f.disponible
        )
        self._inf(f"  DOC_CLAVE_ duplicadas : {duplicadas or 'ninguna'}")
        self._inf(
            f"  Unidades del pendrive con DOC_SUCURS vacio : "
            f"{resultado.unidades_sin_sucursal:,.3f}   "
            f"(asignadas a [{alltrim(self.p.sucursal)}])"
        )
        self._inf()
        self._inf(f"  Tabla generada : {resultado.ruta}")

    def _guardar_informe(self) -> Path | None:
        from .salidas.comun import carpeta_salida

        nombre = "rotacion_" + datetime.date.today().strftime("%Y%m%d") + ".txt"
        for carpeta in (carpeta_salida(), Path.cwd()):
            try:
                ruta = carpeta / nombre
                ruta.write_text("\n".join(self._informe), encoding="utf-8")
                return ruta
            except OSError:
                continue
        return None


# ==========================================================================

def calcular_rotacion(
    parametros: Parametros,
    opciones: OpcionesRotacion | None = None,
    progreso: Progreso | None = None,
) -> ResultadoRotacion:
    return CalculadorRotacion(parametros, opciones, progreso).calcular()
