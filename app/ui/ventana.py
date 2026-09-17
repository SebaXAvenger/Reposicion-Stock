"""Ventana principal: port de reposicion.scx."""

from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox, QPushButton,
    QSizePolicy, QSpinBox, QSplitter, QTabWidget, QTableView, QVBoxLayout,
    QWidget,
)

from ..calculo import MODO_MANUAL, MODO_ROTACION, MotorReposicion, Resultado
from ..config import Parametros
from ..datos import Catalogo, RepositorioERP
from ..vfp import transform_moneda
from . import estilo
from .modelos import ModeloDetalle, ModeloProveedores
from .widgets import ControlSegmentado, Interruptor, Panel, TarjetaKPI


class Trabajador(QThread):
    """Corre la lectura de tablas y el calculo fuera del hilo de la interfaz.

    En VFP esto era un WAIT WINDOW "Analizando stock..." con la pantalla
    congelada. Aca la ventana sigue respondiendo mientras se recorren los
    33.000 articulos.
    """

    terminado = Signal(object, object)   # Resultado, Catalogo
    fallo = Signal(str)
    progreso = Signal(str)

    def __init__(self, parametros: Parametros, modo: int, remoto: bool,
                 catalogo: Catalogo | None):
        super().__init__()
        self.parametros = parametros
        self.modo = modo
        self.remoto = remoto
        self.catalogo = catalogo

    def run(self) -> None:
        try:
            catalogo = self.catalogo
            if catalogo is None:
                self.progreso.emit("Leyendo el catalogo de articulos...")
                repositorio = RepositorioERP(self.parametros)
                catalogo = repositorio.cargar(
                    con_remoto=self.remoto,
                    con_rotacion=self.modo == MODO_ROTACION,
                )
            self.progreso.emit("Analizando stock...")
            motor = MotorReposicion(self.parametros, catalogo)
            resultado = motor.calcular(self.modo, self.remoto)
            self.terminado.emit(resultado, catalogo)
        except Exception:
            self.fallo.emit(traceback.format_exc())


class VentanaPrincipal(QMainWindow):
    def __init__(self, parametros: Parametros):
        super().__init__()
        self.p = parametros
        self.resultado: Resultado | None = None
        self._catalogo: Catalogo | None = None
        self._firma_catalogo: tuple | None = None
        self._trabajador: Trabajador | None = None
        self._proveedor_actual = ""
        self._cargando = False
        self._iniciado = False

        self.setWindowTitle("Centro de control de quiebres de stock")
        self.resize(1560, 880)
        self.setMinimumSize(1180, 700)

        self._construir()
        self._atajos()

    # ------------------------------------------------------------------
    # Construccion
    # ------------------------------------------------------------------

    def _construir(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        raiz.addWidget(self._barra_titulo())

        cuerpo = QWidget()
        capa = QVBoxLayout(cuerpo)
        capa.setContentsMargins(14, 12, 14, 12)
        capa.setSpacing(11)
        raiz.addWidget(cuerpo, 1)

        capa.addLayout(self._fila_indicadores())
        capa.addWidget(self._bloque_parametros())
        capa.addWidget(self._bloque_grillas(), 1)
        capa.addWidget(self._bloque_pie())

    def _barra_titulo(self) -> QWidget:
        barra = QFrame()
        barra.setObjectName("barraTitulo")
        barra.setFixedHeight(42)
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(16, 0, 14, 0)
        fila.setSpacing(10)

        icono = QLabel("◉")
        icono.setStyleSheet(f"color: {estilo.ACENTO}; font-size: 15px;")
        fila.addWidget(icono)

        titulo = QLabel("CENTRO DE CONTROL DE QUIEBRES DE STOCK")
        titulo.setObjectName("tituloApp")
        fila.addWidget(titulo)
        fila.addStretch(1)

        self.lbl_entorno = QLabel("")
        self.lbl_entorno.setObjectName("leyenda")
        fila.addWidget(self.lbl_entorno)

        boton_ayuda = QPushButton("?")
        boton_ayuda.setObjectName("ayuda")
        boton_ayuda.setToolTip("Como funciona esta pantalla")
        boton_ayuda.clicked.connect(self.mostrar_ayuda)
        fila.addWidget(boton_ayuda)

        return barra

    def _fila_indicadores(self) -> QHBoxLayout:
        fila = QHBoxLayout()
        fila.setSpacing(10)

        self.kpi_proveedores = TarjetaKPI("\U0001F465", "Proveedores a comprar", "-")
        self.kpi_articulos = TarjetaKPI("\U0001F4CB", "Articulos a pedir", "-")
        self.kpi_monto = TarjetaKPI("\U0001F4B0", "Inversion estimada total", "-")
        self.kpi_monto.fijar_color(estilo.VERDE)

        fila.addWidget(self.kpi_proveedores, 3)
        fila.addWidget(self.kpi_articulos, 3)
        fila.addWidget(self.kpi_monto, 4)

        columna = QVBoxLayout()
        columna.setSpacing(6)

        self.btn_actualizar = QPushButton("↻  ACTUALIZAR (F5)")
        self.btn_actualizar.setObjectName("primario")
        self.btn_actualizar.setMinimumHeight(30)
        self.btn_actualizar.clicked.connect(lambda: self.cargar_quiebres(forzar=True))
        columna.addWidget(self.btn_actualizar)

        self.cmb_sucursal = QComboBox()
        self.cmb_sucursal.addItem("Filtro: Solo esta sucursal", False)
        self.cmb_sucursal.addItem("Filtro: Todas las Sucursales", True)
        self.cmb_sucursal.setCurrentIndex(1 if self.p.consolidar_sucursales else 0)
        self.cmb_sucursal.currentIndexChanged.connect(self._cambio_sucursal)
        if not self.p.puede_consolidar():
            self.cmb_sucursal.setItemData(
                1, "No se configuro la carpeta de la otra sucursal", Qt.ToolTipRole
            )
        columna.addWidget(self.cmb_sucursal)

        fila.addLayout(columna, 3)
        return fila

    def _bloque_parametros(self) -> QWidget:
        contenedor = QWidget()
        capa = QVBoxLayout(contenedor)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(6)

        titulo = QLabel("PARAMETROS DE CALCULO Y FILTROS")
        titulo.setObjectName("seccion")
        capa.addWidget(titulo)

        self.solapas = QTabWidget()
        self.solapas.addTab(self._solapa_manual(), "Manual (Min/Max)")
        self.solapas.addTab(self._solapa_rotacion(), "Inteligente (Rotacion)")
        self.solapas.setCurrentIndex(1 if self.p.modo == MODO_ROTACION else 0)
        self.solapas.currentChanged.connect(self._cambio_modo)
        capa.addWidget(self.solapas)

        return contenedor

    def _solapa_manual(self) -> QWidget:
        pagina = QWidget()
        capa = QHBoxLayout(pagina)
        capa.setContentsMargins(14, 12, 14, 12)
        capa.setSpacing(14)

        self.chk_sin_parametros = QCheckBox(
            "Incluir articulos sin minimo ni maximo cargados"
        )
        self.chk_sin_parametros.setChecked(self.p.manual_sin_parametros)
        self.chk_sin_parametros.toggled.connect(self._cambio_parametro)
        capa.addWidget(self.chk_sin_parametros)

        aviso = QLabel(
            "Esta solapa usa el minimo y el maximo cargados en la ficha de cada "
            "articulo. Si casi ninguno los tiene, va a verse practicamente vacia."
        )
        aviso.setObjectName("leyenda")
        aviso.setWordWrap(True)
        capa.addWidget(aviso, 1)

        return pagina

    def _solapa_rotacion(self) -> QWidget:
        pagina = QWidget()
        capa = QVBoxLayout(pagina)
        capa.setContentsMargins(14, 11, 14, 11)
        capa.setSpacing(9)

        # --- primera fila --------------------------------------------
        fila1 = QHBoxLayout()
        fila1.setSpacing(8)

        fila1.addWidget(QLabel("Pedir cuando queden menos de"))
        self.spn_punto = QSpinBox()
        self.spn_punto.setRange(1, 365)
        self.spn_punto.setValue(self.p.punto_pedido)
        self.spn_punto.setFixedWidth(66)
        self.spn_punto.valueChanged.connect(self._cambio_parametro)
        fila1.addWidget(self.spn_punto)
        fila1.addWidget(QLabel("dias"))

        fila1.addSpacing(18)
        fila1.addWidget(QLabel("Comprar stock para"))
        self.spn_cobertura = QSpinBox()
        self.spn_cobertura.setRange(1, 730)
        self.spn_cobertura.setValue(self.p.cobertura)
        self.spn_cobertura.setFixedWidth(66)
        self.spn_cobertura.valueChanged.connect(self._cambio_parametro)
        fila1.addWidget(self.spn_cobertura)
        fila1.addWidget(QLabel("dias"))

        fila1.addSpacing(18)
        self.swt_esporadicos = Interruptor(self.p.excluir_esporadicos)
        self.swt_esporadicos.alternado.connect(self._cambio_parametro)
        fila1.addWidget(self.swt_esporadicos)
        etiqueta = QLabel("Excluir articulos vendidos en un solo mes")
        etiqueta.setStyleSheet(f"color: {estilo.TEXTO_SUAVE};")
        fila1.addWidget(etiqueta)

        fila1.addStretch(1)

        self.chk_neg_cero = QCheckBox("Tratar stock negativo como cero")
        self.chk_neg_cero.setChecked(self.p.negativo_como_cero)
        self.chk_neg_cero.setToolTip(
            "Un stock negativo es imposible en la realidad: casi siempre es "
            "mercaderia recibida y nunca cargada.\nCon esta opcion el calculo "
            "lo trata como cero en vez de sumarlo al faltante."
        )
        self.chk_neg_cero.toggled.connect(self._cambio_parametro)
        fila1.addWidget(self.chk_neg_cero)

        capa.addLayout(fila1)

        # --- segunda fila --------------------------------------------
        fila2 = QHBoxLayout()
        fila2.setSpacing(8)

        fila2.addWidget(QLabel("Criterio:"))
        self.seg_criterio = ControlSegmentado(
            ["Promedio mensual", "Mediana mensual"],
            1 if self.p.criterio_mediana else 0,
        )
        self.seg_criterio.cambiado.connect(self._cambio_parametro)
        fila2.addWidget(self.seg_criterio)

        # Estacionalidad: ajusta la venta mensual segun la temporada que va a
        # cubrir la compra. Se recalcula al instante, sin releer tablas.
        fila2.addSpacing(16)
        self.swt_estacionalidad = Interruptor(self.p.estacionalidad)
        self.swt_estacionalidad.alternado.connect(self._cambio_parametro)
        fila2.addWidget(self.swt_estacionalidad)
        etiqueta_estac = QLabel("Considerar temporadas")
        etiqueta_estac.setStyleSheet(f"color: {estilo.TEXTO_SUAVE};")
        texto_estac = (
            "Ajusta la venta mensual segun lo que se vendio historicamente en "
            "los meses que va a cubrir la compra.\n"
            "Usa el historial del articulo; si tiene poca venta o menos de "
            "12 meses, el de su rubro; si tampoco hay, no ajusta.\n"
            "Necesita que la rotacion se haya recalculado con esta version."
        )
        etiqueta_estac.setToolTip(texto_estac)
        self.swt_estacionalidad.setToolTip(texto_estac)
        fila2.addWidget(etiqueta_estac)

        fila2.addSpacing(16)
        self.btn_recalcular = QPushButton("RECALCULAR ROTACION...")
        self.btn_recalcular.clicked.connect(self.recalcular_rotacion)
        fila2.addWidget(self.btn_recalcular)

        fila2.addSpacing(12)
        self.lbl_rotacion = QLabel("")
        self.lbl_rotacion.setObjectName("leyenda")
        fila2.addWidget(self.lbl_rotacion)

        fila2.addStretch(1)

        self.chk_catalogo = QCheckBox("Analizar todas las series")
        self.chk_catalogo.setChecked(self.p.catalogo_completo)
        self.chk_catalogo.setToolTip(
            "Ignora el filtro de sucursal sobre el catalogo y analiza todas "
            "las series de articulos."
        )
        self.chk_catalogo.toggled.connect(self._cambio_catalogo)
        fila2.addWidget(self.chk_catalogo)

        capa.addLayout(fila2)
        return pagina

    def _bloque_grillas(self) -> QWidget:
        divisor = QSplitter(Qt.Horizontal)
        divisor.setChildrenCollapsible(False)
        divisor.setHandleWidth(8)

        # --- proveedores ---------------------------------------------
        panel_izq = Panel("RANKING DE PROVEEDORES")
        self.tbl_proveedores = QTableView()
        self.modelo_proveedores = ModeloProveedores(self)
        self.tbl_proveedores.setModel(self.modelo_proveedores)
        _preparar_tabla(self.tbl_proveedores)
        self.tbl_proveedores.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_proveedores.selectionModel().currentRowChanged.connect(
            self._cambio_proveedor
        )
        panel_izq.agregar(self.tbl_proveedores, 1)
        divisor.addWidget(panel_izq)

        # --- detalle --------------------------------------------------
        panel_der = Panel("DETALLE DE ARTICULOS (SELECCIONADO)")

        self.chk_reparto = QCheckBox("Mostrar reparto entre depositos")
        self.chk_reparto.setToolTip(
            "Divide la cantidad a pedir entre esta sucursal y la otra, en "
            "proporcion al faltante de cada deposito.\n"
            "Solo tiene sentido comprando para toda la empresa."
        )
        self.chk_reparto.toggled.connect(self._alternar_reparto)
        panel_der.agregar_al_encabezado(self.chk_reparto)

        self.tbl_detalle = QTableView()
        self.modelo_detalle = ModeloDetalle(self)
        self.tbl_detalle.setModel(self.modelo_detalle)
        _preparar_tabla(self.tbl_detalle)
        self.tbl_detalle.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.modelo_detalle.cantidad_editada.connect(self._cantidad_editada)
        panel_der.agregar(self.tbl_detalle, 1)
        divisor.addWidget(panel_der)

        divisor.setStretchFactor(0, 34)
        divisor.setStretchFactor(1, 66)
        divisor.setSizes([520, 1010])
        return divisor

    def _bloque_pie(self) -> QWidget:
        contenedor = QWidget()
        fila = QHBoxLayout(contenedor)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(9)

        self.btn_pdf = QPushButton("IMPRIMIR / EXPORTAR PDF")
        self.btn_pdf.clicked.connect(self.exportar_pdf)
        fila.addWidget(self.btn_pdf)

        self.btn_excel = QPushButton("EXPORTAR A EXCEL")
        self.btn_excel.clicked.connect(self.exportar_excel)
        fila.addWidget(self.btn_excel)

        self.btn_informe = QPushButton("VER INFORME DEL ANALISIS")
        self.btn_informe.clicked.connect(self.ver_informe)
        fila.addWidget(self.btn_informe)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setObjectName("leyenda")
        fila.addWidget(self.lbl_estado)

        fila.addStretch(1)

        totales = QFrame()
        totales.setObjectName("panelTotales")
        capa_totales = QVBoxLayout(totales)
        capa_totales.setContentsMargins(16, 7, 16, 7)
        capa_totales.setSpacing(2)

        rotulo = QLabel("METRICAS DE SELECCION (PROVEEDOR)")
        rotulo.setObjectName("rotuloTotal")
        capa_totales.addWidget(rotulo)

        fila_unidades = QHBoxLayout()
        fila_unidades.setSpacing(8)
        etiqueta_u = QLabel("Unidades a pedir:")
        etiqueta_u.setObjectName("rotuloTotal")
        fila_unidades.addWidget(etiqueta_u)
        fila_unidades.addStretch(1)
        self.lbl_unidades = QLabel("0")
        self.lbl_unidades.setObjectName("valorTotal")
        fila_unidades.addWidget(self.lbl_unidades)
        capa_totales.addLayout(fila_unidades)

        fila_monto = QHBoxLayout()
        fila_monto.setSpacing(8)
        etiqueta_m = QLabel("Monto estimado:")
        etiqueta_m.setObjectName("rotuloTotal")
        fila_monto.addWidget(etiqueta_m)
        fila_monto.addStretch(1)
        self.lbl_monto = QLabel("$ 0,00")
        self.lbl_monto.setObjectName("valorTotalMonto")
        fila_monto.addWidget(self.lbl_monto)
        capa_totales.addLayout(fila_monto)

        totales.setMinimumWidth(280)
        fila.addWidget(totales)

        self.btn_salir = QPushButton("SALIR")
        self.btn_salir.setObjectName("salir")
        self.btn_salir.setMinimumWidth(90)
        self.btn_salir.clicked.connect(self.close)
        fila.addWidget(self.btn_salir)

        return contenedor

    def _atajos(self) -> None:
        QShortcut(QKeySequence("F5"), self, lambda: self.cargar_quiebres(forzar=True))
        QShortcut(QKeySequence("Esc"), self, self.close)
        QShortcut(QKeySequence("F1"), self, self.mostrar_ayuda)
        QShortcut(QKeySequence("Ctrl+E"), self, self.exportar_excel)
        QShortcut(QKeySequence("Ctrl+P"), self, self.exportar_pdf)

    # ------------------------------------------------------------------
    # Eventos de parametros
    # ------------------------------------------------------------------

    def _cambio_parametro(self, *_args) -> None:
        """Cada cambio de parametro recalcula solo, igual que el original.

        A diferencia del formulario VFP, NO se vuelven a leer las tablas:
        el catalogo ya esta en memoria y solo cambian las cuentas. Por eso
        mover un spinner responde al instante en vez de tardar lo que tarde
        recorrer ARTICULO.DBF de nuevo.
        """
        if self._cargando or not self._iniciado:
            return
        self._volcar_controles()
        self.cargar_quiebres()

    def _cambio_catalogo(self, *_args) -> None:
        """'Analizar todas las series' cambia QUE articulos se leen, asi que
        obliga a releer el catalogo."""
        if self._cargando or not self._iniciado:
            return
        self._volcar_controles()
        self.cargar_quiebres(forzar=True)

    def _cambio_sucursal(self, *_args) -> None:
        if self._cargando or not self._iniciado:
            return
        consolidar = bool(self.cmb_sucursal.currentData())
        if consolidar and not self.p.puede_consolidar():
            self._cargando = True
            self.cmb_sucursal.setCurrentIndex(0)
            self._cargando = False
            QMessageBox.warning(
                self, "Otra sucursal",
                "No se configuro la carpeta de la otra sucursal (sis_path2), "
                "asi que solo se puede analizar el stock local.",
            )
            return
        self._volcar_controles()
        self.cargar_quiebres(forzar=True)

    def _cambio_modo(self, indice: int) -> None:
        if self._cargando or not self._iniciado:
            return
        self._volcar_controles()
        self.cargar_quiebres()

    def _volcar_controles(self) -> None:
        self.p.punto_pedido = self.spn_punto.value()
        self.p.cobertura = self.spn_cobertura.value()
        self.p.criterio_mediana = self.seg_criterio.seleccion() == 1
        self.p.excluir_esporadicos = self.swt_esporadicos.isChecked()
        self.p.estacionalidad = self.swt_estacionalidad.isChecked()
        self.p.negativo_como_cero = self.chk_neg_cero.isChecked()
        self.p.catalogo_completo = self.chk_catalogo.isChecked()
        self.p.manual_sin_parametros = self.chk_sin_parametros.isChecked()
        self.p.consolidar_sucursales = bool(self.cmb_sucursal.currentData())
        self.p.modo = (
            MODO_ROTACION if self.solapas.currentIndex() == 1 else MODO_MANUAL
        )

    # ------------------------------------------------------------------
    # Corrida
    # ------------------------------------------------------------------

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        if not self._iniciado:
            self._iniciado = True
            self.lbl_entorno.setText(
                f"Sucursal {self.p.sucursal}  ·  {self.p.carpeta_datos}"
            )
            self.cargar_quiebres(forzar=True)

    def cargar_quiebres(self, forzar: bool = False) -> None:
        if self._trabajador is not None and self._trabajador.isRunning():
            return

        self._volcar_controles()
        modo = self.p.modo
        remoto = self.p.consolidar_sucursales and self.p.puede_consolidar()

        firma = (remoto, self.p.catalogo_completo, self.p.sucursal, self.p.codepage)
        catalogo = None
        if not forzar and self._catalogo is not None and firma == self._firma_catalogo:
            catalogo = self._catalogo
            if modo == MODO_ROTACION and not catalogo.info_rotacion.disponible:
                catalogo = None  # falta ROTACION: hay que intentar leerla

        self._cargando = True
        self.btn_actualizar.setEnabled(False)
        self.lbl_estado.setText("Analizando stock...")
        QApplication.setOverrideCursor(Qt.BusyCursor)

        self._firma_catalogo = firma
        self._trabajador = Trabajador(self.p, modo, remoto, catalogo)
        self._trabajador.terminado.connect(self._corrida_lista)
        self._trabajador.fallo.connect(self._corrida_fallida)
        self._trabajador.progreso.connect(self.lbl_estado.setText)
        self._trabajador.start()

    def _corrida_lista(self, resultado: Resultado, catalogo: Catalogo) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_actualizar.setEnabled(True)
        self._catalogo = catalogo
        self.resultado = resultado

        self.lbl_rotacion.setText(resultado.leyenda_rotacion)
        self.lbl_rotacion.setObjectName(
            "leyenda" if catalogo.info_rotacion.disponible else "leyendaAviso"
        )
        self.lbl_rotacion.setStyleSheet(
            f"color: {estilo.TEXTO_TENUE};"
            if catalogo.info_rotacion.disponible
            else f"color: {estilo.AMBAR};"
        )

        if not resultado.ok:
            self.modelo_proveedores.fijar_datos([])
            self.modelo_detalle.fijar_datos([], self.p.modo, False)
            self._actualizar_indicadores()
            self.lbl_estado.setText(resultado.mensaje.split("\n")[0])
            self._cargando = False
            if resultado.mensaje and "Sin resultados" not in resultado.mensaje:
                QMessageBox.information(self, "Parametros", resultado.mensaje)
            return

        self.modelo_proveedores.fijar_datos(resultado.proveedores)
        self._aplicar_anchos_proveedores()
        self._actualizar_indicadores()

        self._cargando = False
        if resultado.proveedores:
            self.tbl_proveedores.selectRow(0)
            self._mostrar_detalle(resultado.proveedores[0].codigo)

        duracion = resultado.diagnostico.duracion
        tiempo_lectura = sum(catalogo.tiempos.values())
        self.lbl_estado.setText(
            f"{resultado.diagnostico.sugeridos:,} articulos sugeridos  ·  "
            f"lectura {tiempo_lectura:.2f}s  ·  calculo {duracion:.2f}s".replace(",", ".")
        )

    def _corrida_fallida(self, detalle: str) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_actualizar.setEnabled(True)
        self._cargando = False
        self.lbl_estado.setText("La corrida fallo.")
        dialogo = QMessageBox(self)
        dialogo.setIcon(QMessageBox.Critical)
        dialogo.setWindowTitle("Error")
        dialogo.setText("No se pudo completar el analisis.")
        dialogo.setDetailedText(detalle)
        dialogo.exec()

    # ------------------------------------------------------------------
    # Maestro - detalle
    # ------------------------------------------------------------------

    def _cambio_proveedor(self, actual, _anterior) -> None:
        if self._cargando or not actual.isValid():
            return
        proveedor = self.modelo_proveedores.proveedor(actual.row())
        if proveedor and proveedor.codigo != self._proveedor_actual:
            self._mostrar_detalle(proveedor.codigo)

    def _mostrar_detalle(self, codigo: str) -> None:
        if self.resultado is None:
            return
        self._proveedor_actual = codigo
        lineas = self.resultado.lineas_de(codigo)
        self.modelo_detalle.fijar_datos(
            lineas, self.p.modo, self.p.consolidar_sucursales,
            self.chk_reparto.isChecked(),
        )
        self.chk_reparto.setVisible(
            self.p.consolidar_sucursales and self.p.modo == MODO_ROTACION
        )
        self._aplicar_anchos_detalle()
        self._actualizar_totales_proveedor()

    def _alternar_reparto(self, _activo: bool) -> None:
        if self._proveedor_actual:
            self._mostrar_detalle(self._proveedor_actual)

    def _aplicar_anchos_proveedores(self) -> None:
        encabezado = self.tbl_proveedores.horizontalHeader()
        for columna, ancho in enumerate(ModeloProveedores.ANCHOS):
            if ancho is None:
                encabezado.setSectionResizeMode(columna, QHeaderView.Stretch)
            else:
                encabezado.setSectionResizeMode(columna, QHeaderView.Interactive)
                self.tbl_proveedores.setColumnWidth(columna, ancho)

    def _aplicar_anchos_detalle(self) -> None:
        encabezado = self.tbl_detalle.horizontalHeader()
        ocultas = set(self.modelo_detalle.columnas_ocultas())
        for columna, ancho in enumerate(ModeloDetalle.ANCHOS):
            if columna in ocultas:
                self.tbl_detalle.setColumnHidden(columna, True)
                continue
            self.tbl_detalle.setColumnHidden(columna, False)
            if columna == ModeloDetalle.COL_DESC:
                encabezado.setSectionResizeMode(columna, QHeaderView.Stretch)
            else:
                encabezado.setSectionResizeMode(columna, QHeaderView.Interactive)
                self.tbl_detalle.setColumnWidth(columna, ancho)

    def _cantidad_editada(self, _linea) -> None:
        if self.resultado is None:
            return
        self.resultado.recalcular_proveedor(self._proveedor_actual)
        fila = self.modelo_proveedores.fila_de(self._proveedor_actual)
        if fila >= 0:
            self.modelo_proveedores.refrescar_fila(fila)
        self._actualizar_totales_proveedor()
        self._actualizar_indicadores()

    def _actualizar_totales_proveedor(self) -> None:
        unidades = sum(l.cant_pedir for l in self.modelo_detalle.lineas)
        monto = sum(l.subtotal for l in self.modelo_detalle.lineas)
        self.lbl_unidades.setText(f"{unidades:,.2f}".replace(",", "."))
        self.lbl_monto.setText("$ " + transform_moneda(monto))

    def _actualizar_indicadores(self) -> None:
        if self.resultado is None or not self.resultado.ok:
            self.kpi_proveedores.fijar_valor("0")
            self.kpi_articulos.fijar_valor("0")
            self.kpi_monto.fijar_valor("$ 0,00")
            return
        proveedores, items, monto = self.resultado.total_general()
        self.kpi_proveedores.fijar_valor(f"{proveedores:,}".replace(",", "."))
        self.kpi_articulos.fijar_valor(f"{items:,}".replace(",", "."))
        self.kpi_monto.fijar_valor("$ " + transform_moneda(monto))

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def _hay_pedido(self) -> bool:
        if self.resultado is None or not self.resultado.ok:
            QMessageBox.information(
                self, "Atencion", "Todavia no hay un analisis cargado."
            )
            return False
        if not self._proveedor_actual:
            QMessageBox.information(
                self, "Atencion", "Elegi un proveedor del panel izquierdo."
            )
            return False
        return True

    def _proveedor_seleccionado(self):
        for proveedor in self.resultado.proveedores:
            if proveedor.codigo == self._proveedor_actual:
                return proveedor
        return None

    def exportar_excel(self) -> None:
        if not self._hay_pedido():
            return
        from ..salidas.excel import exportar_pedido

        proveedor = self._proveedor_seleccionado()
        lineas = [l for l in self.modelo_detalle.lineas if l.cant_pedir > 0]
        if not lineas:
            QMessageBox.information(
                self, "Atencion",
                "No hay cantidades a pedir cargadas para este proveedor.",
            )
            return
        try:
            ruta = exportar_pedido(lineas, proveedor, self.p, self.p.modo)
        except Exception as error:
            QMessageBox.critical(self, "Excel", f"No se pudo generar:\n{error}")
            return
        self._abrir(ruta, "La planilla")

    def exportar_pdf(self) -> None:
        if not self._hay_pedido():
            return
        from ..salidas.pdf import exportar_pedido_pdf

        proveedor = self._proveedor_seleccionado()
        lineas = [l for l in self.modelo_detalle.lineas if l.cant_pedir > 0]
        if not lineas:
            QMessageBox.information(
                self, "Atencion",
                "No hay cantidades a pedir cargadas para este proveedor.",
            )
            return
        try:
            ruta = exportar_pedido_pdf(lineas, proveedor, self.p, self.p.modo)
        except Exception as error:
            QMessageBox.critical(self, "PDF", f"No se pudo generar:\n{error}")
            return
        self._abrir(ruta, "El pedido")

    def ver_informe(self) -> None:
        if self.resultado is None or not self.resultado.ok:
            QMessageBox.information(
                self, "Atencion", "Todavia no hay un analisis cargado."
            )
            return
        from ..salidas.informe import generar_informe

        try:
            ruta = generar_informe(self.resultado, self.p, self._catalogo)
        except Exception as error:
            QMessageBox.critical(self, "Informe", f"No se pudo generar:\n{error}")
            return
        self._abrir(ruta, "El informe")

    def recalcular_rotacion(self) -> None:
        from .dialogo_rotacion import DialogoRotacion

        if self._trabajador is not None and self._trabajador.isRunning():
            return

        # La tabla que se va a reemplazar es la misma que este programa tiene
        # leida. Se sueltan los datos antes de recalcular para no quedarse
        # despues con la rotacion vieja en memoria.
        dialogo = DialogoRotacion(self.p, self)
        if dialogo.exec() != DialogoRotacion.Accepted:
            return

        self._catalogo = None
        self._firma_catalogo = None
        self.cargar_quiebres(forzar=True)

        resultado = dialogo.resultado
        if resultado is not None and resultado.ruta_informe:
            self.lbl_estado.setText(
                f"Rotacion regenerada: {resultado.filas:,} filas. "
                f"Informe en {resultado.ruta_informe}".replace(",", ".")
            )

    def mostrar_ayuda(self) -> None:
        from .ayuda import DialogoAyuda

        DialogoAyuda(self).exec()

    def _abrir(self, ruta: Path, que: str) -> None:
        import subprocess
        import sys

        self.lbl_estado.setText(f"{que} se guardo en {ruta}")
        try:
            if sys.platform.startswith("win"):
                import os

                os.startfile(str(ruta))       # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(ruta)])
            else:
                subprocess.Popen(["xdg-open", str(ruta)])
        except Exception:
            QMessageBox.information(
                self, "Listo", f"{que} se guardo en:\n{ruta}"
            )

    def closeEvent(self, evento) -> None:
        self._volcar_controles()
        try:
            self.p.guardar()
        except OSError:
            pass
        if self._trabajador is not None and self._trabajador.isRunning():
            self._trabajador.wait(2000)
        super().closeEvent(evento)


def _preparar_tabla(tabla: QTableView) -> None:
    tabla.setAlternatingRowColors(False)
    tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
    tabla.setSelectionMode(QAbstractItemView.SingleSelection)
    tabla.setShowGrid(True)
    tabla.setWordWrap(False)
    tabla.verticalHeader().setVisible(False)
    tabla.verticalHeader().setDefaultSectionSize(23)
    tabla.horizontalHeader().setHighlightSections(False)
    tabla.horizontalHeader().setStretchLastSection(False)
    tabla.setCornerButtonEnabled(False)
    tabla.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    tabla.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    tabla.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
