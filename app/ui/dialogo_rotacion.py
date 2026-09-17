"""
Pantalla del recalculo de rotacion.

Reemplaza al MESSAGEBOX de confirmacion + WAIT WINDOW del formulario
original. El PRG dejaba al usuario mirando una ventanita que decia
"Leyendo el pendrive..." sin saber cuanto faltaba; aca hay barra de
progreso y el informe se ve en la misma pantalla en vez de en un MESSAGEBOX
gigante.
"""

from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..config import Parametros
from ..rotacion import OpcionesRotacion, ResultadoRotacion, calcular_rotacion
from . import estilo


class TrabajadorRotacion(QThread):
    terminado = Signal(object)
    fallo = Signal(str)
    progreso = Signal(str, int)

    def __init__(self, parametros: Parametros, opciones: OpcionesRotacion):
        super().__init__()
        self.parametros = parametros
        self.opciones = opciones

    def run(self) -> None:
        try:
            resultado = calcular_rotacion(
                self.parametros,
                self.opciones,
                lambda texto, pct: self.progreso.emit(texto, pct),
            )
            self.terminado.emit(resultado)
        except Exception:
            self.fallo.emit(traceback.format_exc())


class DialogoRotacion(QDialog):
    """Devuelve Accepted solo si la tabla se regenero, para que la ventana
    principal sepa que tiene que releer."""

    def __init__(self, parametros: Parametros, parent=None):
        super().__init__(parent)
        self.p = parametros
        self.resultado: ResultadoRotacion | None = None
        self._trabajador: TrabajadorRotacion | None = None

        self.setWindowTitle("Recalcular rotacion")
        self.setMinimumWidth(680)
        self.setStyleSheet(estilo.hoja_de_estilos())

        capa = QVBoxLayout(self)
        capa.setContentsMargins(20, 18, 20, 18)
        capa.setSpacing(13)

        titulo = QLabel("Recalcular el analisis de ventas")
        titulo.setStyleSheet(
            f"color: {estilo.TEXTO}; font-size: 16px; font-weight: 700;"
        )
        capa.addWidget(titulo)

        explicacion = QLabel(
            "Lee todo el historial de comprobantes de las tres bases y vuelve "
            "a generar ROTACION.DBF, que es la tabla de la que sale la "
            "columna Vta/mes.\n\n"
            "Alcanza con hacerlo una vez por semana. Mientras corre, conviene "
            "que nadie mas tenga esta pantalla abierta: si otro puesto tiene "
            "la tabla tomada, el reemplazo no se puede hacer y la tabla vieja "
            "queda intacta."
        )
        explicacion.setWordWrap(True)
        explicacion.setObjectName("leyenda")
        capa.addWidget(explicacion)

        capa.addWidget(self._opciones())
        capa.addWidget(self._aviso_remitos())

        self.barra = QProgressBar()
        self.barra.setRange(0, 100)
        self.barra.setValue(0)
        self.barra.setVisible(False)
        capa.addWidget(self.barra)

        self.lbl_paso = QLabel("")
        self.lbl_paso.setObjectName("leyenda")
        capa.addWidget(self.lbl_paso)

        self.txt_informe = QPlainTextEdit()
        self.txt_informe.setReadOnly(True)
        self.txt_informe.setVisible(False)
        self.txt_informe.setMinimumHeight(240)
        self.txt_informe.setStyleSheet(
            f"font-family: {estilo.FUENTE_MONO}; font-size: 11px; "
            f"background-color: {estilo.FONDO_CAMPO}; color: {estilo.TEXTO_SUAVE}; "
            f"border: 1px solid {estilo.BORDE}; border-radius: 6px;"
        )
        capa.addWidget(self.txt_informe, 1)

        pie = QHBoxLayout()
        pie.addStretch(1)
        self.btn_cerrar = QPushButton("CANCELAR")
        self.btn_cerrar.clicked.connect(self.reject)
        pie.addWidget(self.btn_cerrar)

        self.btn_calcular = QPushButton("CALCULAR")
        self.btn_calcular.setObjectName("primario")
        self.btn_calcular.setMinimumWidth(130)
        self.btn_calcular.clicked.connect(self._arrancar)
        pie.addWidget(self.btn_calcular)
        capa.addLayout(pie)

    # ------------------------------------------------------------------

    def _opciones(self) -> QWidget:
        marco = QFrame()
        marco.setObjectName("panel")
        capa = QVBoxLayout(marco)
        capa.setContentsMargins(14, 11, 14, 12)
        capa.setSpacing(9)

        fila = QHBoxLayout()
        fila.setSpacing(8)
        fila.addWidget(QLabel("Analizar los ultimos"))
        self.spn_meses = QSpinBox()
        self.spn_meses.setRange(1, 120)
        self.spn_meses.setValue(24)
        self.spn_meses.setFixedWidth(70)
        self.spn_meses.setToolTip(
            "Meses completos hacia atras. El mes en curso queda afuera a "
            "proposito: al estar a la mitad, bajaria el promedio."
        )
        fila.addWidget(self.spn_meses)
        fila.addWidget(QLabel("meses completos"))
        fila.addStretch(1)
        capa.addLayout(fila)

        self.chk_remoto = QCheckBox("Incluir los comprobantes de la otra sucursal")
        self.chk_remoto.setChecked(bool(self.p.carpeta_datos2))
        self.chk_remoto.setEnabled(bool(self.p.carpeta_datos2))
        if not self.p.carpeta_datos2:
            self.chk_remoto.setText(
                "Incluir la otra sucursal  (sis_path2 no esta configurada)"
            )
        capa.addWidget(self.chk_remoto)

        self.chk_pendrive = QCheckBox("Incluir los comprobantes del pendrive")
        self.chk_pendrive.setChecked(bool(self.p.carpeta_zip))
        self.chk_pendrive.setEnabled(bool(self.p.carpeta_zip))
        if not self.p.carpeta_zip:
            self.chk_pendrive.setText(
                "Incluir el pendrive  (zip_path_ no esta configurada)"
            )
        capa.addWidget(self.chk_pendrive)

        return marco

    def _aviso_remitos(self) -> QWidget:
        marco = QFrame()
        marco.setStyleSheet(
            f"""
            QFrame {{
                background-color: #2a2416;
                border: 1px solid {estilo.BORDE};
                border-left: 3px solid {estilo.AMBAR};
                border-radius: 8px;
            }}
            QLabel {{ background: transparent; border: none; }}
            QCheckBox {{ background: transparent; border: none; }}
            """
        )
        capa = QVBoxLayout(marco)
        capa.setContentsMargins(14, 11, 14, 12)
        capa.setSpacing(7)

        self.chk_remitos = QCheckBox(
            "Contar los remitos internos (RI) como venta"
        )
        self.chk_remitos.setChecked(False)
        capa.addWidget(self.chk_remitos)

        nota = QLabel(
            "Un remito interno mueve mercaderia de un deposito al otro: baja "
            "el stock del que provee, pero no es una venta. Contarlo infla la "
            "demanda de la sucursal que abastece a la otra.\n\n"
            "El PRG del sistema los cuenta como venta. Si se deja destildado, "
            "los numeros de esta corrida NO van a coincidir con los que "
            "genera el ERP."
        )
        nota.setWordWrap(True)
        nota.setStyleSheet(f"color: {estilo.TEXTO_SUAVE}; font-size: 11px;")
        capa.addWidget(nota)

        return marco

    # ------------------------------------------------------------------

    def _arrancar(self) -> None:
        opciones = OpcionesRotacion(
            meses=self.spn_meses.value(),
            incluir_pendrive=self.chk_pendrive.isChecked(),
            incluir_remoto=self.chk_remoto.isChecked(),
            remitos_internos_son_venta=self.chk_remitos.isChecked(),
        )

        self.btn_calcular.setEnabled(False)
        self.btn_cerrar.setEnabled(False)
        self.spn_meses.setEnabled(False)
        self.chk_remoto.setEnabled(False)
        self.chk_pendrive.setEnabled(False)
        self.chk_remitos.setEnabled(False)
        self.barra.setVisible(True)
        self.txt_informe.setVisible(True)
        self.txt_informe.setPlainText("")
        # El informe aparece recien ahora: sin esto la ventana se queda del
        # alto que tenia y los botones terminan encima del texto.
        self.resize(self.width(), max(self.height(), 760))

        self._trabajador = TrabajadorRotacion(self.p, opciones)
        self._trabajador.progreso.connect(self._avanzar)
        self._trabajador.terminado.connect(self._listo)
        self._trabajador.fallo.connect(self._fallo)
        self._trabajador.start()

    def _avanzar(self, texto: str, porcentaje: int) -> None:
        self.lbl_paso.setText(texto)
        self.barra.setValue(porcentaje)

    def _listo(self, resultado: ResultadoRotacion) -> None:
        self.resultado = resultado
        self.btn_cerrar.setEnabled(True)
        self.txt_informe.setPlainText(resultado.texto_informe())

        if not resultado.ok:
            self.barra.setValue(0)
            self.lbl_paso.setText("No se genero la tabla.")
            self.lbl_paso.setStyleSheet(f"color: {estilo.ROJO};")
            self.btn_calcular.setEnabled(True)
            self.spn_meses.setEnabled(True)
            self.chk_remitos.setEnabled(True)
            self.chk_remoto.setEnabled(bool(self.p.carpeta_datos2))
            self.chk_pendrive.setEnabled(bool(self.p.carpeta_zip))
            self.btn_cerrar.setText("CERRAR")
            QMessageBox.warning(self, "Recalcular rotacion", resultado.mensaje)
            return

        self.barra.setValue(100)
        self.lbl_paso.setStyleSheet(f"color: {estilo.VERDE};")
        self.lbl_paso.setText(
            f"Listo: {resultado.filas:,} filas en {resultado.duracion:.1f} s"
            .replace(",", ".")
        )
        self.btn_cerrar.setText("CERRAR Y ACTUALIZAR")
        self.btn_cerrar.setObjectName("primario")
        self.btn_cerrar.setStyleSheet("")
        self.btn_cerrar.clicked.disconnect()
        self.btn_cerrar.clicked.connect(self.accept)
        self.btn_calcular.setVisible(False)

    def _fallo(self, detalle: str) -> None:
        self.btn_cerrar.setEnabled(True)
        self.btn_cerrar.setText("CERRAR")
        self.btn_calcular.setEnabled(True)
        self.barra.setValue(0)
        self.lbl_paso.setText("El calculo fallo.")
        self.lbl_paso.setStyleSheet(f"color: {estilo.ROJO};")
        self.txt_informe.setPlainText(detalle)

    def closeEvent(self, evento) -> None:
        if self._trabajador is not None and self._trabajador.isRunning():
            evento.ignore()
            QMessageBox.information(
                self, "Recalculando",
                "El calculo esta en curso. Espera a que termine.",
            )
            return
        super().closeEvent(evento)
