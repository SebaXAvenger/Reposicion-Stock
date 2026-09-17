"""Controles propios: tarjeta de indicador, interruptor y control segmentado."""

from __future__ import annotations

from PySide6.QtCore import (
    Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from . import estilo


class TarjetaKPI(QFrame):
    """Reemplaza a las tarjetas del encabezado que el original dibujaba con
    shapes y editbox deshabilitados."""

    def __init__(self, icono: str, rotulo: str, valor: str = "-", parent=None):
        super().__init__(parent)
        self.setObjectName("tarjetaKpi")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        fila = QHBoxLayout(self)
        fila.setContentsMargins(14, 9, 16, 9)
        fila.setSpacing(11)

        self._icono = QLabel(icono)
        self._icono.setObjectName("kpiIcono")
        self._icono.setFixedWidth(20)
        self._icono.setAlignment(Qt.AlignCenter)
        fila.addWidget(self._icono)

        columna = QVBoxLayout()
        columna.setSpacing(1)
        columna.setContentsMargins(0, 0, 0, 0)

        self._rotulo = QLabel(rotulo.upper())
        self._rotulo.setObjectName("kpiRotulo")
        self._valor = QLabel(valor)
        self._valor.setObjectName("kpiValor")

        columna.addWidget(self._rotulo)
        columna.addWidget(self._valor)
        fila.addLayout(columna, 1)

    def fijar_valor(self, texto: str) -> None:
        self._valor.setText(texto)

    def fijar_color(self, color: str) -> None:
        self._valor.setStyleSheet(f"color: {color};")


class Interruptor(QWidget):
    """Switch estilo moderno. Sustituye al checkbox de 'Excluir articulos
    vendidos en un solo mes', que en el mockup aparece como toggle."""

    alternado = Signal(bool)

    def __init__(self, activo: bool = False, parent=None):
        super().__init__(parent)
        self._activo = activo
        self._posicion = 1.0 if activo else 0.0
        self.setFixedSize(QSize(38, 20))
        self.setCursor(Qt.PointingHandCursor)

        self._animacion = QPropertyAnimation(self, b"posicion", self)
        self._animacion.setDuration(140)
        self._animacion.setEasingCurve(QEasingCurve.InOutCubic)

    # -- propiedad animada ---------------------------------------------
    def _leer_posicion(self) -> float:
        return self._posicion

    def _fijar_posicion(self, valor: float) -> None:
        self._posicion = valor
        self.update()

    posicion = Property(float, _leer_posicion, _fijar_posicion)

    # -- estado ----------------------------------------------------------
    def isChecked(self) -> bool:
        return self._activo

    def setChecked(self, valor: bool, avisar: bool = False) -> None:
        if valor == self._activo:
            return
        self._activo = valor
        self._animacion.stop()
        self._animacion.setStartValue(self._posicion)
        self._animacion.setEndValue(1.0 if valor else 0.0)
        self._animacion.start()
        if avisar:
            self.alternado.emit(valor)

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.LeftButton:
            self.setChecked(not self._activo, avisar=True)
        super().mousePressEvent(evento)

    def paintEvent(self, _evento) -> None:
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing)

        apagado = QColor(estilo.FONDO_CAMPO)
        encendido = QColor(estilo.ACENTO)
        fondo = _mezclar(apagado, encendido, self._posicion)

        alto = self.height()
        radio = alto / 2.0
        pintor.setBrush(fondo)
        borde = QColor(estilo.BORDE) if self._posicion < 0.5 else encendido
        pintor.setPen(QPen(borde, 1))
        pintor.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, alto - 1), radio, radio)

        diametro = alto - 6
        izquierda = 3 + self._posicion * (self.width() - diametro - 6)
        pintor.setPen(Qt.NoPen)
        pintor.setBrush(QColor("#e8edf5") if self._posicion > 0.5 else QColor("#7b8698"))
        pintor.drawEllipse(QRectF(izquierda, 3, diametro, diametro))


class ControlSegmentado(QWidget):
    """Dos o mas opciones excluyentes en una sola pastilla. Reemplaza al
    optiongroup 'Promedio mensual / Mediana mensual'."""

    cambiado = Signal(int)

    def __init__(self, opciones: list[str], seleccion: int = 0, parent=None):
        super().__init__(parent)
        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)

        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(0)

        for indice, texto in enumerate(opciones):
            boton = QPushButton(texto)
            boton.setCheckable(True)
            boton.setCursor(Qt.PointingHandCursor)
            boton.setChecked(indice == seleccion)
            redondeo = ""
            if indice == 0:
                redondeo = "border-top-right-radius:0; border-bottom-right-radius:0;"
            elif indice == len(opciones) - 1:
                redondeo = (
                    "border-top-left-radius:0; border-bottom-left-radius:0;"
                    "border-left:none;"
                )
            else:
                redondeo = "border-radius:0; border-left:none;"
            boton.setStyleSheet(
                f"""
                QPushButton {{
                    padding: 5px 13px; font-size: 12px; {redondeo}
                    background-color: {estilo.FONDO_CAMPO};
                    color: {estilo.TEXTO_TENUE};
                    border: 1px solid {estilo.BORDE};
                }}
                QPushButton:checked {{
                    background-color: {estilo.ACENTO};
                    color: #ffffff; font-weight: 600;
                    border-color: {estilo.ACENTO};
                }}
                QPushButton:hover:!checked {{ color: {estilo.TEXTO}; }}
                """
            )
            # Sin este minimo, el texto de la opcion elegida se corta cuando
            # pasa a negrita: el ancho lo calcula Qt con la fuente normal.
            metrica = boton.fontMetrics().horizontalAdvance(texto)
            boton.setMinimumWidth(int(metrica * 1.14) + 34)
            self._grupo.addButton(boton, indice)
            fila.addWidget(boton)

        self._grupo.idClicked.connect(self.cambiado.emit)

    def seleccion(self) -> int:
        return self._grupo.checkedId()

    def fijar_seleccion(self, indice: int) -> None:
        boton = self._grupo.button(indice)
        if boton:
            boton.setChecked(True)


class Panel(QFrame):
    """Contenedor con titulo, equivalente a los recuadros del mockup."""

    def __init__(self, titulo: str, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.contenido = QVBoxLayout(self)
        self.contenido.setContentsMargins(12, 10, 12, 12)
        self.contenido.setSpacing(8)

        self.encabezado = QHBoxLayout()
        self.encabezado.setContentsMargins(0, 0, 0, 0)
        self.encabezado.setSpacing(8)

        self.titulo = QLabel(titulo)
        self.titulo.setObjectName("tituloPanel")
        self.encabezado.addWidget(self.titulo)
        self.encabezado.addStretch(1)
        self.contenido.addLayout(self.encabezado)

    def agregar(self, widget: QWidget, estirar: int = 0) -> None:
        self.contenido.addWidget(widget, estirar)

    def agregar_al_encabezado(self, widget: QWidget) -> None:
        """Control alineado a la derecha del titulo del panel."""
        self.encabezado.addWidget(widget)


def _mezclar(a: QColor, b: QColor, proporcion: float) -> QColor:
    proporcion = max(0.0, min(1.0, proporcion))
    return QColor(
        int(a.red() + (b.red() - a.red()) * proporcion),
        int(a.green() + (b.green() - a.green()) * proporcion),
        int(a.blue() + (b.blue() - a.blue()) * proporcion),
    )
