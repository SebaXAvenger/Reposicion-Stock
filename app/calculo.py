"""
Port de la logica de calculo del formulario.

Equivale a Form.CandidatosRotacion, Form.CandidatosManual y a la parte de
Form.CargarQuiebres que agrupa por proveedor. Las formulas, los umbrales y
el ORDEN de los filtros se conservan exactamente: cualquier cambio aca
mueve numeros que el usuario ya conoce y no los va a poder explicar.

El instrumental de diagnostico del original (cinco contadores, hasta cinco
ejemplos por motivo de descarte y la foto de parametros de la corrida) se
mantiene: es lo que alimenta el informe de analisis.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any

from .config import Parametros
from .datos import (
    Catalogo, buscar_demanda, nombre_proveedor, normalizar_proveedor,
)
from .vfp import vfp_ceiling, vfp_round

MODO_MANUAL = 1
MODO_ROTACION = 2

# Codigos cortos y fijos, como en el original. El texto legible lo pone el
# informe, asi que la clasificacion no depende de una cadena larga.
MOTIVOS = {
    "SINVTA": "Sin ventas registradas en la ventana analizada",
    "SINDEM": "Vendio, pero no en el universo elegido",
    "ESPORA": "Esporadico: movimiento en un solo mes",
    "STOCKOK": "Todavia le alcanza el stock",
    "CUBIER": "La cobertura objetivo ya esta cubierta",
    "NEGATI": "Sugerido, pero con stock negativo",
    "SINOBJ": "Sin minimo ni maximo cargados: no hay objetivo",
    "STOCKMIN": "Stock por encima del minimo",
}

# ---------------------------------------------------------------------------
# Estacionalidad
# ---------------------------------------------------------------------------
# La demanda mensual (promedio o mediana de la ventana) es un numero PAREJO
# para todo el anio. El indice estacional la corrige segun lo que se vendio
# historicamente en los meses que va a cubrir la compra:
#
#     indice = venta de los proximos `cobertura` dias segun el perfil
#              / venta mensual promedio del anio
#
#     1,00 = mes normal     1,80 = se vende 80% mas     0,50 = la mitad
#
# De donde sale el perfil, en este orden:
#   1. Del propio articulo, si tiene 12+ meses de historia y vende lo
#      suficiente como para que el perfil no sea ruido.
#   2. De su RUBRO (suma de los articulos del rubro con historia completa).
#   3. Si no hay ninguno de los dos, indice 1: calcula igual que siempre.

# Meses de historia para que esten todos los meses del anio en el perfil
ESTAC_HISTORIA_MINIMA = 12
# Perfil propio: unidades por anio y meses con venta minimos
ESTAC_MIN_UNIDADES_ANIO = 24
ESTAC_MIN_MESES_CON_VENTA = 6
# Perfil de rubro: cantidad de articulos y unidades por anio minimas
ESTAC_RUBRO_MIN_ARTICULOS = 5
ESTAC_RUBRO_MIN_UNIDADES_ANIO = 60
# Topes del indice: un pico raro (una obra, un quiebre largo) no puede
# multiplicar ni anular la compra.
ESTAC_TOPE_MINIMO = 0.3
ESTAC_TOPE_MAXIMO = 3.0


@dataclass
class Linea:
    """Una fila de curQuiebre."""

    __slots__ = (
        "clave", "sucursal", "codigo", "cod_prov_articulo", "descripcion",
        "unidad", "minimo", "maximo", "stock_local", "stock_remoto",
        "stock_total", "vta_mes", "vta_mes_local", "vta_mes_remoto",
        "dias_stock", "cant_pedir", "pedir_local", "pedir_remoto",
        "prop_local", "costo", "subtotal", "ultima_venta", "cod_proveedor",
        "sugerido_original", "marca", "ubicacion", "indice_estacional",
        "fuente_estacional",
    )

    clave: str
    sucursal: str
    codigo: str
    cod_prov_articulo: str
    descripcion: str
    unidad: str
    minimo: float
    maximo: float
    stock_local: float
    stock_remoto: float
    stock_total: float
    vta_mes: float
    vta_mes_local: float
    vta_mes_remoto: float
    dias_stock: float
    cant_pedir: float
    pedir_local: float
    pedir_remoto: float
    prop_local: float
    costo: float
    subtotal: float
    ultima_venta: Any
    cod_proveedor: str
    sugerido_original: float
    marca: str
    ubicacion: str
    # Factor por temporada aplicado a la venta mensual (1 = sin ajuste) y
    # de donde salio: "articulo", "rubro" o "" (no se ajusto).
    indice_estacional: float
    fuente_estacional: str

    def fijar_cantidad(self, cantidad: float) -> None:
        """Equivale a grdReposicion.Column8.Text1.Valid.

        El reparto entre depositos sigue a la cantidad editada, para que
        `Pedir aca` + `Pedir otra` sume SIEMPRE exactamente `A pedir`.
        """
        if cantidad < 0:          # no se aceptan cantidades negativas
            cantidad = 0.0
        self.cant_pedir = float(cantidad)
        self.pedir_local = vfp_round(self.cant_pedir * self.prop_local, 0)
        self.pedir_remoto = self.cant_pedir - self.pedir_local
        self.subtotal = self.cant_pedir * self.costo

    @property
    def modificada(self) -> bool:
        return abs(self.cant_pedir - self.sugerido_original) > 1e-9


@dataclass
class Proveedor:
    """Una fila de curProv."""

    codigo: str
    nombre: str
    items: int = 0
    criticos: int = 0
    unidades: float = 0.0
    monto: float = 0.0


@dataclass
class Ejemplo:
    """Fila de curEjem: un caso concreto de descarte, con los numeros que
    provocaron la decision."""

    motivo: str
    codigo: str
    descripcion: str
    vta_mes: float = 0.0
    vta_remota: float = 0.0
    stock: float = 0.0
    dias: float = 0.0
    meses_con_venta: int = 0
    necesidad: float = 0.0
    ultima_venta: Any = None


@dataclass
class Diagnostico:
    """Foto de la corrida: es curDiagRot.

    Se congelan los parametros ACA y no se releen al generar el informe.
    Si el usuario mueve un spinner despues de la corrida, leer los controles
    de nuevo haria que el informe describa parametros que no son los que
    produjeron esa lista.
    """

    fecha: datetime.date = field(default_factory=datetime.date.today)
    hora: str = ""
    sucursal: str = ""
    modo: int = MODO_ROTACION
    total_catalogo: int = 0
    analizados: int = 0
    sugeridos: int = 0
    negativos: int = 0
    desc_sin_venta: int = 0
    desc_sin_demanda: int = 0
    desc_esporadico: int = 0
    desc_stock_ok: int = 0
    desc_cubierto: int = 0
    desc_sin_objetivo: int = 0
    desc_sobre_minimo: int = 0
    punto_pedido: float = 0.0
    cobertura: float = 0.0
    mediana: bool = False
    excluir_esporadicos: bool = False
    catalogo_completo: bool = False
    negativo_como_cero: bool = False
    remoto: bool = False
    rotacion_fecha: Any = None
    rotacion_negro: bool = False
    venta_desde: Any = None
    venta_hasta: Any = None
    venta_meses: int = 0
    duracion: float = 0.0
    # Que forma de clave enganho contra ROTACION. Si la corta es la unica
    # que engancha, DCC_ARTICU guarda el codigo sin el prefijo de sucursal.
    enganche_clave_completa: int = 0
    enganche_clave_corta: int = 0
    # Estacionalidad: si estaba pedida, si ROTACION.DBF traia el perfil, y
    # de donde salio el indice de cada articulo que llego a esa etapa.
    estacionalidad: bool = False
    estacionalidad_disponible: bool = False
    estac_articulo: int = 0
    estac_rubro: int = 0
    estac_neutro: int = 0


@dataclass
class Resultado:
    lineas: list[Linea] = field(default_factory=list)
    proveedores: list[Proveedor] = field(default_factory=list)
    ejemplos: list[Ejemplo] = field(default_factory=list)
    diagnostico: Diagnostico = field(default_factory=Diagnostico)
    ok: bool = False
    mensaje: str = ""
    leyenda_rotacion: str = ""

    # -- totales -----------------------------------------------------

    def lineas_de(self, codigo_proveedor: str) -> list[Linea]:
        return [l for l in self.lineas if l.cod_proveedor == codigo_proveedor]

    def total_general(self) -> tuple[int, int, float]:
        """(proveedores, items, monto) de toda la corrida."""
        return (
            len(self.proveedores),
            sum(p.items for p in self.proveedores),
            sum(p.monto for p in self.proveedores),
        )

    def recalcular_proveedor(self, codigo: str) -> Proveedor | None:
        """Baja al cursor maestro el efecto de una cantidad editada a mano."""
        objetivo = next((p for p in self.proveedores if p.codigo == codigo), None)
        if objetivo is None:
            return None
        unidades = 0.0
        monto = 0.0
        for linea in self.lineas:
            if linea.cod_proveedor == codigo:
                unidades += linea.cant_pedir
                monto += linea.subtotal
        objetivo.unidades = unidades
        objetivo.monto = monto
        return objetivo


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

class MotorReposicion:
    def __init__(
        self,
        parametros: Parametros,
        catalogo: Catalogo,
        hoy: datetime.date | None = None,
    ):
        self.p = parametros
        self.catalogo = catalogo
        # Fecha desde la que se mide la cobertura para la estacionalidad.
        # Se puede fijar para las pruebas; en uso normal es hoy.
        self.hoy = hoy or datetime.date.today()

    def calcular(self, modo: int, remoto: bool) -> Resultado:
        import time

        inicio = time.perf_counter()
        remoto = bool(remoto and self.catalogo.remoto_disponible)

        if modo == MODO_ROTACION:
            resultado = self._rotacion(remoto)
        else:
            resultado = self._manual(remoto)

        resultado.diagnostico.duracion = time.perf_counter() - inicio

        if resultado.ok:
            self._agrupar_por_proveedor(resultado)
            if not resultado.proveedores:
                resultado.ok = False
                resultado.mensaje = "Sin resultados para los parametros actuales."
        return resultado

    # -- modo rotacion ---------------------------------------------------

    def _rotacion(self, remoto: bool) -> Resultado:
        p = self.p
        catalogo = self.catalogo
        resultado = Resultado()
        diag = resultado.diagnostico

        punto = float(p.punto_pedido)
        cobertura = float(p.cobertura)
        mediana = p.criterio_mediana
        excluir_esporadicos = p.excluir_esporadicos
        neg_cero = p.negativo_como_cero

        diag.hora = datetime.datetime.now().strftime("%H:%M:%S")
        diag.sucursal = p.sucursal
        diag.modo = MODO_ROTACION
        diag.punto_pedido = punto
        diag.cobertura = cobertura
        diag.mediana = mediana
        diag.excluir_esporadicos = excluir_esporadicos
        diag.catalogo_completo = p.catalogo_completo
        diag.negativo_como_cero = neg_cero
        diag.remoto = remoto
        diag.total_catalogo = catalogo.total_catalogo

        # --- guardas de parametros (identicas al original) --------------
        if cobertura <= 0:
            resultado.mensaje = "La cobertura objetivo tiene que ser mayor a cero."
            return resultado

        # Con punto de pedido en cero, el filtro `dias >= punto` da verdadero
        # para TODOS los articulos (0 >= 0) y la corrida descarta el catalogo
        # entero sin que se entienda por que.
        if punto <= 0:
            resultado.mensaje = (
                "El punto de pedido tiene que ser mayor a cero.\n\n"
                "Con cero, ningun articulo puede entrar en la lista."
            )
            return resultado

        if punto > cobertura:
            resultado.mensaje = (
                "El punto de pedido no puede ser mayor que la cobertura objetivo."
            )
            return resultado

        info = catalogo.info_rotacion
        if not info.disponible:
            resultado.mensaje = (
                info.mensaje
                or "Todavia no se calculo la rotacion de ventas."
            )
            resultado.leyenda_rotacion = resultado.mensaje
            return resultado

        diag.rotacion_fecha = info.fecha_calculo
        diag.rotacion_negro = info.incluye_negro
        diag.venta_desde = info.desde
        diag.venta_hasta = info.hasta
        diag.venta_meses = info.meses

        resultado.leyenda_rotacion = _leyenda_rotacion(
            info, remoto, p.estacionalidad
        )

        demanda = catalogo.demanda
        stock_remoto = catalogo.stock_remoto if remoto else {}
        ejemplos = resultado.ejemplos
        lineas = resultado.lineas


        contadores = {
            "SINVTA": 0, "SINDEM": 0, "ESPORA": 0, "STOCKOK": 0, "CUBIER": 0,
        }
        negativos = 0

        def ejemplo(motivo: str, **datos: Any) -> None:
            """Hasta 5 ejemplos por motivo, como en el original."""
            if contadores[motivo] <= 5:
                ejemplos.append(Ejemplo(motivo=motivo, **datos))

        diag.analizados = len(catalogo.articulos)

        # --- Estacionalidad: preparacion --------------------------------
        # Solo si esta activada Y la tabla trae el perfil. Con una
        # ROTACION.DBF vieja el calculo sigue exactamente como antes.
        usar_estacionalidad = bool(p.estacionalidad and info.con_perfil)
        diag.estacionalidad = bool(p.estacionalidad)
        diag.estacionalidad_disponible = bool(info.con_perfil)
        pesos = pesos_horizonte(self.hoy, int(cobertura))
        indices_rubro: dict[str, float] = {}

        if usar_estacionalidad:
            # Perfil de cada rubro = suma de los perfiles de sus articulos
            # con historia completa. Se suma en unidades, asi que pesan mas
            # los articulos que mas se venden, que son los mas confiables.
            suma_rubro: dict[str, list] = {}
            cuenta_rubro: dict[str, int] = {}
            for art in catalogo.articulos:
                if not art.rubro:
                    continue
                perfil = perfil_del_universo(buscar_demanda(art, demanda), remoto)
                if perfil is None:
                    continue
                acumulado = suma_rubro.get(art.rubro)
                if acumulado is None:
                    suma_rubro[art.rubro] = list(perfil)
                else:
                    for m in range(12):
                        acumulado[m] += perfil[m]
                cuenta_rubro[art.rubro] = cuenta_rubro.get(art.rubro, 0) + 1

            for rubro, perfil in suma_rubro.items():
                if (
                    cuenta_rubro[rubro] >= ESTAC_RUBRO_MIN_ARTICULOS
                    and sum(perfil) >= ESTAC_RUBRO_MIN_UNIDADES_ANIO
                ):
                    indice = indice_estacional(perfil, pesos)
                    if indice is not None:
                        indices_rubro[rubro] = indice

        estac_articulo = 0
        estac_rubro = 0
        estac_neutro = 0

        enganche_completo = 0
        enganche_corto = 0

        for art in catalogo.articulos:
            clave = art.clave

            # El cruce tolera las dos formas de clave posibles. Ver el
            # comentario de datos.buscar_demanda: si se elige mal, todo el
            # catalogo cae en "sin ventas registradas" sin ningun aviso.
            rot = demanda.get(clave)
            if rot is not None:
                enganche_completo += 1
            elif art.clave_corta != clave:
                rot = demanda.get(art.clave_corta)
                if rot is not None:
                    enganche_corto += 1

            # --- FILTRO 1: nunca vendio en la ventana -------------------
            if rot is None:
                contadores["SINVTA"] += 1
                ejemplo(
                    "SINVTA", codigo=clave, descripcion=art.descripcion[:45],
                    stock=art.stock_local,
                )
                continue

            # --- Demanda segun el universo elegido ----------------------
            mes_local = rot.mediana_local if mediana else rot.promedio_local
            mes_remoto_bruto = rot.mediana_remota if mediana else rot.promedio_remoto
            mes_remoto = mes_remoto_bruto if remoto else 0.0
            mes_total = mes_local + mes_remoto

            # --- FILTRO 2: vendio, pero no en este universo -------------
            if mes_total <= 0:
                contadores["SINDEM"] += 1
                ejemplo(
                    "SINDEM", codigo=clave, descripcion=art.descripcion[:45],
                    vta_mes=mes_local, vta_remota=mes_remoto_bruto,
                    stock=art.stock_local, ultima_venta=rot.ultima_venta,
                )
                continue

            meses_con = max(
                rot.meses_con_venta_local,
                rot.meses_con_venta_remoto if remoto else 0,
            )

            # --- FILTRO 3: esporadico (un solo mes con venta) -----------
            if excluir_esporadicos and meses_con <= 1:
                contadores["ESPORA"] += 1
                ejemplo(
                    "ESPORA", codigo=clave, descripcion=art.descripcion[:45],
                    vta_mes=mes_total, stock=art.stock_local,
                    meses_con_venta=meses_con, necesidad=rot.unidades_totales,
                    ultima_venta=rot.ultima_venta,
                )
                continue

            # --- Ajuste por temporada -----------------------------------
            # Se aplica DESPUES de los filtros de venta (1 a 3), que miran
            # la historia tal cual, y ANTES del punto de pedido y la
            # cobertura, que son los que tienen que anticipar la temporada.
            indice = 1.0
            fuente = ""
            if usar_estacionalidad:
                perfil = perfil_del_universo(rot, remoto)
                if (
                    perfil is not None
                    and sum(perfil) >= ESTAC_MIN_UNIDADES_ANIO
                    and meses_con >= ESTAC_MIN_MESES_CON_VENTA
                ):
                    propio = indice_estacional(perfil, pesos)
                    if propio is not None:
                        indice, fuente = propio, "articulo"
                if not fuente and art.rubro in indices_rubro:
                    indice, fuente = indices_rubro[art.rubro], "rubro"

                if fuente == "articulo":
                    estac_articulo += 1
                elif fuente == "rubro":
                    estac_rubro += 1
                else:
                    estac_neutro += 1

                # El mismo factor para las dos sucursales: la temporada es
                # la misma y asi no se altera el reparto entre depositos.
                mes_local *= indice
                mes_remoto *= indice
                mes_total = mes_local + mes_remoto

            # --- Stock ---------------------------------------------------
            rem = stock_remoto.get(clave, 0.0) if remoto else 0.0
            total = art.stock_local + rem

            # En la grilla se muestra el stock REAL (puede ser negativo y
            # queda en rojo). La cuenta se hace sobre el stock ACOTADO: un
            # negativo es un error de inventario, no mercaderia que falte.
            base_local = max(art.stock_local, 0.0) if neg_cero else art.stock_local
            base_remoto = max(rem, 0.0) if neg_cero else rem
            base_total = base_local + base_remoto

            # --- Punto de pedido ----------------------------------------
            dia_total = mes_total / 30.0
            dias = 0.0 if base_total <= 0 else base_total / dia_total

            # --- FILTRO 4: todavia le alcanza el stock ------------------
            if dias >= punto:
                contadores["STOCKOK"] += 1
                ejemplo(
                    "STOCKOK", codigo=clave, descripcion=art.descripcion[:45],
                    vta_mes=mes_total, stock=total, dias=min(dias, 9999),
                    meses_con_venta=meses_con, ultima_venta=rot.ultima_venta,
                )
                continue

            # --- Cuanto comprar (consolidado, compensando excedentes) ----
            necesidad_total = vfp_ceiling(dia_total * cobertura - base_total)

            # --- FILTRO 5: la cobertura ya esta cubierta ----------------
            if necesidad_total <= 0:
                contadores["CUBIER"] += 1
                ejemplo(
                    "CUBIER", codigo=clave, descripcion=art.descripcion[:45],
                    vta_mes=mes_total, stock=total, dias=min(dias, 9999),
                    necesidad=dia_total * cobertura - base_total,
                    ultima_venta=rot.ultima_venta,
                )
                continue

            # --- Reparto entre depositos, proporcional al faltante -------
            dia_local = mes_local / 30.0
            dia_remoto = mes_remoto / 30.0
            necesidad_local = max(dia_local * cobertura - base_local, 0.0)
            necesidad_remota = max(dia_remoto * cobertura - base_remoto, 0.0)

            if (necesidad_local + necesidad_remota) > 0:
                proporcion = necesidad_local / (necesidad_local + necesidad_remota)
            else:
                proporcion = 1.0
            pedir_local = vfp_round(necesidad_total * proporcion, 0)

            codigo_proveedor = normalizar_proveedor(art.cod_proveedor_bruto)

            lineas.append(
                Linea(
                    clave=clave,
                    sucursal=art.sucursal,
                    codigo=art.codigo,
                    cod_prov_articulo=art.cod_prov_articulo,
                    descripcion=art.descripcion,
                    unidad=art.unidad,
                    minimo=art.minimo,
                    maximo=art.maximo,
                    stock_local=art.stock_local,
                    stock_remoto=rem,
                    stock_total=total,
                    vta_mes=mes_total,
                    vta_mes_local=mes_local,
                    vta_mes_remoto=mes_remoto,
                    dias_stock=min(dias, 9999),
                    cant_pedir=necesidad_total,
                    pedir_local=pedir_local,
                    pedir_remoto=necesidad_total - pedir_local,
                    prop_local=proporcion,
                    costo=art.costo,
                    subtotal=necesidad_total * art.costo,
                    ultima_venta=rot.ultima_venta,
                    cod_proveedor=codigo_proveedor,
                    sugerido_original=necesidad_total,
                    marca=art.marca,
                    ubicacion=art.ubicacion,
                    indice_estacional=indice,
                    fuente_estacional=fuente,
                )
            )

            if total < 0:
                negativos += 1
                if negativos <= 5:
                    ejemplos.append(
                        Ejemplo(
                            motivo="NEGATI", codigo=clave,
                            descripcion=art.descripcion[:45],
                            vta_mes=mes_total, stock=total,
                            dias=min(dias, 9999), necesidad=necesidad_total,
                            ultima_venta=rot.ultima_venta,
                        )
                    )

        diag.estac_articulo = estac_articulo
        diag.estac_rubro = estac_rubro
        diag.estac_neutro = estac_neutro

        diag.enganche_clave_completa = enganche_completo
        diag.enganche_clave_corta = enganche_corto
        if enganche_corto and not enganche_completo:
            catalogo.diagnostico.append(
                "ROTACION.DBF se cruzo por el codigo de articulo solo "
                "(sin el prefijo de sucursal): "
                f"{enganche_corto:,} artículos enganchados."
            )

        diag.sugeridos = len(lineas)
        diag.negativos = negativos
        diag.desc_sin_venta = contadores["SINVTA"]
        diag.desc_sin_demanda = contadores["SINDEM"]
        diag.desc_esporadico = contadores["ESPORA"]
        diag.desc_stock_ok = contadores["STOCKOK"]
        diag.desc_cubierto = contadores["CUBIER"]

        resultado.ok = bool(lineas)
        if not lineas:
            resultado.mensaje = "Sin resultados para los parametros actuales."
        return resultado

    # -- modo manual (min/max) -------------------------------------------

    def _manual(self, remoto: bool) -> Resultado:
        p = self.p
        catalogo = self.catalogo
        resultado = Resultado()
        diag = resultado.diagnostico

        diag.hora = datetime.datetime.now().strftime("%H:%M:%S")
        diag.sucursal = p.sucursal
        diag.modo = MODO_MANUAL
        diag.total_catalogo = catalogo.total_catalogo
        diag.catalogo_completo = p.catalogo_completo
        diag.negativo_como_cero = p.negativo_como_cero
        diag.remoto = remoto

        sin_parametros = getattr(p, "manual_sin_parametros", False)
        neg_cero = p.negativo_como_cero
        stock_remoto = catalogo.stock_remoto if remoto else {}

        lineas = resultado.lineas
        ejemplos = resultado.ejemplos
        sin_objetivo = 0
        sobre_minimo = 0
        analizados = 0

        for art in catalogo.articulos:
            # AND AR_CANT <= AR_MINI AND (AR_MINI > 0 OR AR_MAXI > 0 OR sinParam)
            if art.stock_local > art.minimo:
                continue
            if not (art.minimo > 0 or art.maximo > 0 or sin_parametros):
                continue

            analizados += 1
            clave = art.clave
            rem = stock_remoto.get(clave, 0.0) if remoto else 0.0
            total = art.stock_local + rem
            base = max(total, 0.0) if neg_cero else total

            if base > art.minimo:
                # consolidado con la otra sucursal ya no es quiebre
                sobre_minimo += 1
                if sobre_minimo <= 5:
                    ejemplos.append(
                        Ejemplo(
                            motivo="STOCKMIN", codigo=clave,
                            descripcion=art.descripcion[:45], stock=total,
                            necesidad=art.minimo,
                        )
                    )
                continue

            objetivo = art.maximo if art.maximo > 0 else art.minimo
            sugerido = max(objetivo - base, 0.0)

            if sugerido <= 0:
                # Sin objetivo cargado no hay nada que sugerir: es ruido
                sin_objetivo += 1
                if sin_objetivo <= 5:
                    ejemplos.append(
                        Ejemplo(
                            motivo="SINOBJ", codigo=clave,
                            descripcion=art.descripcion[:45], stock=total,
                        )
                    )
                continue

            lineas.append(
                Linea(
                    clave=clave,
                    sucursal=art.sucursal,
                    codigo=art.codigo,
                    cod_prov_articulo=art.cod_prov_articulo,
                    descripcion=art.descripcion,
                    unidad=art.unidad,
                    minimo=art.minimo,
                    maximo=art.maximo,
                    stock_local=art.stock_local,
                    stock_remoto=rem,
                    stock_total=total,
                    vta_mes=0.0,
                    vta_mes_local=0.0,
                    vta_mes_remoto=0.0,
                    dias_stock=0.0,
                    cant_pedir=sugerido,
                    # En modo manual no hay datos de demanda para repartir:
                    # el pedido se asigna entero a la sucursal local.
                    pedir_local=sugerido,
                    pedir_remoto=0.0,
                    prop_local=1.0,
                    costo=art.costo,
                    subtotal=sugerido * art.costo,
                    ultima_venta=None,
                    cod_proveedor=normalizar_proveedor(art.cod_proveedor_bruto),
                    sugerido_original=sugerido,
                    marca=art.marca,
                    ubicacion=art.ubicacion,
                    # En modo min/max no hay demanda que ajustar
                    indice_estacional=1.0,
                    fuente_estacional="",
                )
            )

        diag.analizados = analizados
        diag.sugeridos = len(lineas)
        diag.desc_sin_objetivo = sin_objetivo
        diag.desc_sobre_minimo = sobre_minimo
        diag.negativos = sum(1 for l in lineas if l.stock_total < 0)

        resultado.ok = bool(lineas)
        if not lineas:
            resultado.mensaje = (
                "Sin resultados para los parametros actuales.\n\n"
                "El modo manual necesita que los articulos tengan minimo y "
                "maximo cargados en su ficha."
            )
        return resultado

    # -- agrupado por proveedor -------------------------------------------

    def _agrupar_por_proveedor(self, resultado: Resultado) -> None:
        """Equivale al SELECT ... GROUP BY cProvCod ORDER BY monto DESC.

        El nombre se resuelve una vez por proveedor, no una vez por articulo:
        con 1.500 lineas y 100 proveedores son 100 busquedas en vez de 1.500.
        """
        agrupado: dict[str, Proveedor] = {}

        for linea in resultado.lineas:
            proveedor = agrupado.get(linea.cod_proveedor)
            if proveedor is None:
                proveedor = Proveedor(codigo=linea.cod_proveedor, nombre="")
                agrupado[linea.cod_proveedor] = proveedor
            proveedor.items += 1
            if linea.stock_total <= 0:
                proveedor.criticos += 1
            proveedor.unidades += linea.cant_pedir
            proveedor.monto += linea.subtotal

        catalogo_proveedores = self.catalogo.proveedores
        respaldo = self.catalogo.proveedores_respaldo
        sin_nombre = 0
        for proveedor in agrupado.values():
            proveedor.nombre = nombre_proveedor(
                proveedor.codigo, catalogo_proveedores, respaldo
            )
            if "no esta en PROVEEDO" in proveedor.nombre:
                sin_nombre += 1

        if sin_nombre:
            self.catalogo.diagnostico.append(
                f"{sin_nombre} de {len(agrupado)} proveedores no se pudieron "
                "resolver, ni por PROVEEDO ni por DESC_PROV."
            )

        resultado.proveedores = sorted(
            agrupado.values(), key=lambda p: p.monto, reverse=True
        )

        # ORDER BY AR_DESC dentro de cada proveedor, igual que el indice
        # PROVIDX (cProvCod + AR_DESC) del original.
        resultado.lineas.sort(key=lambda l: (l.cod_proveedor, l.descripcion))


def pesos_horizonte(desde: datetime.date, dias: int) -> list[float]:
    """Que parte de la cobertura cae en cada mes calendario.

    Comprando el 20 de mayo para 45 dias: 12 dias de mayo, 30 de junio y 3
    de julio. Devuelve 12 pesos (enero..diciembre) que suman 1.
    """
    dias = max(int(dias), 1)
    pesos = [0.0] * 12
    for desplazamiento in range(dias):
        fecha = desde + datetime.timedelta(days=desplazamiento)
        pesos[fecha.month - 1] += 1.0
    return [peso / dias for peso in pesos]


def perfil_del_universo(rot: Any, remoto: bool) -> list | None:
    """Perfil de 12 meses del articulo en el universo elegido.

    Local: el perfil de esta sucursal. Toda la empresa: la suma de los dos.
    Devuelve None si el articulo no tiene fila en ROTACION, si la tabla no
    trae perfil, o si ALGUNA sucursal que vende el articulo tiene menos de
    12 meses de historia: sumar un perfil completo con uno a medias daria
    temporadas que no existen.
    """
    if rot is None:
        return None

    origenes = [(rot.perfil_local, rot.historia_local, rot.promedio_local)]
    if remoto:
        origenes.append(
            (rot.perfil_remoto, rot.historia_remota, rot.promedio_remoto)
        )

    total = None
    for perfil, historia, promedio in origenes:
        if perfil is None:
            if promedio > 0:
                return None     # vende, pero no hay perfil para esa sucursal
            continue            # esa sucursal no lo vende: no aporta
        if historia < ESTAC_HISTORIA_MINIMA:
            return None
        total = list(perfil) if total is None else [
            a + b for a, b in zip(total, perfil)
        ]
    return total


def indice_estacional(perfil: list, pesos: list[float]) -> float | None:
    """Factor por temporada para los dias que cubre la compra.

    1. Se suaviza el perfil con el mes anterior y el siguiente (1-2-1), para
       que un mes suelto con una venta grande no arme una "temporada" y para
       que la compra se anticipe un poco al arranque de la temporada.
    2. indice = venta esperada en el horizonte / promedio mensual del anio.
    3. Se acota entre ESTAC_TOPE_MINIMO y ESTAC_TOPE_MAXIMO.

    Devuelve None si el perfil no tiene venta.
    """
    suavizado = [
        (perfil[m - 1] + 2.0 * perfil[m] + perfil[(m + 1) % 12]) / 4.0
        for m in range(12)
    ]
    anual = sum(suavizado) / 12.0
    if anual <= 0:
        return None
    horizonte = sum(valor * peso for valor, peso in zip(suavizado, pesos))
    indice = horizonte / anual
    return min(max(indice, ESTAC_TOPE_MINIMO), ESTAC_TOPE_MAXIMO)


def _leyenda_rotacion(info: Any, remoto: bool, estacionalidad: bool = False) -> str:
    from .vfp import dtoc

    partes = ["Rotacion al " + (dtoc(info.fecha_calculo) or "?")]
    partes.append("(incluye Zip_Path_)" if info.incluye_negro else "(solo blanco)")
    partes.append(
        "demanda de ambas sucursales" if remoto else "demanda local"
    )
    if estacionalidad:
        partes.append(
            "con temporadas" if info.con_perfil
            else "temporadas: recalcular rotacion"
        )
    return "  -  ".join(partes)
