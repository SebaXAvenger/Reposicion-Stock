"""
Ventana del diagnostico del entorno.

El .exe se compila con `console=False` para que no aparezca la ventana
negra detras de la aplicacion. Eso tiene una consecuencia: no hay stdout
donde imprimir. Por eso el informe se muestra en una ventana y se guarda
en un archivo, en vez de escribirse en la consola.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from . import estilo


class DialogoDiagnostico(QDialog):
    def __init__(self, informe: str, problemas: int, ruta: Path | None = None,
                 parent=None):
        super().__init__(parent)
        self.informe = informe
        self.ruta = ruta

        self.setWindowTitle("Diagnostico del entorno")
        self.resize(940, 780)
        self.setStyleSheet(estilo.hoja_de_estilos())

        capa = QVBoxLayout(self)
        capa.setContentsMargins(18, 16, 18, 16)
        capa.setSpacing(11)

        if problemas:
            titulo, color = (
                f"{problemas} problema(s) que resolver antes de usarlo",
                estilo.ROJO,
            )
        else:
            titulo, color = ("El entorno esta listo", estilo.VERDE)

        etiqueta = QLabel(titulo)
        etiqueta.setStyleSheet(
            f"color: {color}; font-size: 16px; font-weight: 700;"
        )
        capa.addWidget(etiqueta)

        subtitulo = QLabel(
            "Este modo no modifica nada: solo revisa que el entorno este "
            "completo y que las claves enganchen."
            + (f"\nCopia guardada en: {ruta}" if ruta else "")
        )
        subtitulo.setObjectName("leyenda")
        subtitulo.setWordWrap(True)
        capa.addWidget(subtitulo)

        self.texto = QPlainTextEdit()
        self.texto.setReadOnly(True)
        self.texto.setPlainText(informe)
        self.texto.setLineWrapMode(QPlainTextEdit.NoWrap)
        fuente = QFont("Consolas")
        fuente.setStyleHint(QFont.Monospace)
        fuente.setPointSize(9)
        self.texto.setFont(fuente)
        self.texto.setStyleSheet(
            f"background-color: {estilo.FONDO_CAMPO}; color: {estilo.TEXTO_SUAVE}; "
            f"border: 1px solid {estilo.BORDE}; border-radius: 6px;"
        )
        capa.addWidget(self.texto, 1)

        pie = QHBoxLayout()
        copiar = QPushButton("COPIAR AL PORTAPAPELES")
        copiar.clicked.connect(self._copiar)
        pie.addWidget(copiar)

        self.aviso_copia = QLabel("")
        self.aviso_copia.setObjectName("leyenda")
        pie.addWidget(self.aviso_copia)

        pie.addStretch(1)
        cerrar = QPushButton("CERRAR")
        cerrar.setObjectName("primario")
        cerrar.setMinimumWidth(110)
        cerrar.clicked.connect(self.accept)
        pie.addWidget(cerrar)
        capa.addLayout(pie)

    def _copiar(self) -> None:
        QGuiApplication.clipboard().setText(self.informe)
        self.aviso_copia.setStyleSheet(f"color: {estilo.VERDE};")
        self.aviso_copia.setText("Copiado.")
