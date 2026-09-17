"""
Pantalla de configuracion / asistente de primera ejecucion.

Es la ultima capa de la cascada de parametros: cuando el programa NO fue
lanzado por el ERP y no hay un JSON guardado, hay que preguntarle al usuario
donde estan las tablas. Tambien sirve para corregir una configuracion vieja
sin tener que editar el JSON a mano.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from ..config import Parametros
from . import estilo


class DialogoAjustes(QDialog):
    def __init__(self, parametros: Parametros, primera_vez: bool = False, parent=None):
        super().__init__(parent)
        self.p = parametros
        self.setWindowTitle(
            "Configuracion inicial" if primera_vez else "Configuracion"
        )
        self.setMinimumWidth(640)
        self.setStyleSheet(estilo.hoja_de_estilos())

        capa = QVBoxLayout(self)
        capa.setContentsMargins(20, 18, 20, 18)
        capa.setSpacing(14)

        titulo = QLabel(
            "Donde estan las tablas del sistema"
            if primera_vez
            else "Configuracion del entorno"
        )
        titulo.setStyleSheet(
            f"color: {estilo.TEXTO}; font-size: 16px; font-weight: 700;"
        )
        capa.addWidget(titulo)

        explicacion = QLabel(
            "Adentro del ERP estos valores venian de las variables publicas "
            "sis_path_, sis_path2 y sis_sucurs. Como este programa corre por "
            "fuera, hay que indicarselos una vez.\n\n"
            "Si el ERP lo abre pasandole los parametros por linea de comandos, "
            "esos valores tienen prioridad sobre lo que se guarde aca."
        )
        explicacion.setWordWrap(True)
        explicacion.setObjectName("leyenda")
        capa.addWidget(explicacion)

        formulario = QFormLayout()
        formulario.setSpacing(9)
        formulario.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.txt_datos, fila_datos = self._selector(
            self.p.carpeta_datos,
            "Carpeta con ARTICULO.DBF, PROVEEDO.DBF y ROTACION.DBF",
        )
        formulario.addRow(self._rotulo("Carpeta de datos", "sis_path_"), fila_datos)

        self.txt_datos2, fila_datos2 = self._selector(
            self.p.carpeta_datos2,
            "Carpeta de la otra sucursal. Opcional: sin esto solo se analiza "
            "el stock local.",
        )
        formulario.addRow(self._rotulo("Otra sucursal", "sis_path2"), fila_datos2)

        self.txt_sucursal = QLineEdit(self.p.sucursal)
        self.txt_sucursal.setMaximumWidth(110)
        self.txt_sucursal.setPlaceholderText("1")
        formulario.addRow(self._rotulo("Codigo de sucursal", "sis_sucurs"),
                          self.txt_sucursal)

        self.txt_zip, fila_zip = self._selector(
            self.p.carpeta_zip,
            "Segunda base del sistema. Solo se usa para recalcular la rotacion.",
        )
        formulario.addRow(self._rotulo("Segunda base", "zip_path_"), fila_zip)

        self.cmb_codepage = QComboBox()
        for opcion in ("auto", "cp1252", "cp850", "cp437", "cp1250"):
            self.cmb_codepage.addItem(opcion)
        self.cmb_codepage.setCurrentText(self.p.codepage)
        self.cmb_codepage.setMaximumWidth(140)
        self.cmb_codepage.setToolTip(
            "Como estan codificados los acentos y la enie en los DBF.\n"
            "'auto' lee el byte de idioma del encabezado. Si las "
            "descripciones salen con caracteres raros, probar cp850."
        )
        formulario.addRow(self._rotulo("Codificacion", "codepage"), self.cmb_codepage)

        capa.addLayout(formulario)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setObjectName("leyenda")
        capa.addWidget(self.lbl_estado)

        capa.addWidget(self._origenes())

        pie = QHBoxLayout()
        detectar = QPushButton("DETECTAR DEL SISTEMA")
        detectar.setToolTip(
            "Busca el CONFIG.DBF del ERP y toma de ahi las rutas y la "
            "sucursal, igual que hace el sistema al arrancar."
        )
        detectar.clicked.connect(self._detectar)
        pie.addWidget(detectar)

        verificar = QPushButton("VERIFICAR")
        verificar.clicked.connect(self._verificar)
        pie.addWidget(verificar)
        pie.addStretch(1)

        if not primera_vez:
            cancelar = QPushButton("CANCELAR")
            cancelar.clicked.connect(self.reject)
            pie.addWidget(cancelar)

        aceptar = QPushButton("GUARDAR Y CONTINUAR")
        aceptar.setObjectName("primario")
        aceptar.clicked.connect(self._aceptar)
        pie.addWidget(aceptar)
        capa.addLayout(pie)

    # ------------------------------------------------------------------

    def _rotulo(self, texto: str, original: str) -> QWidget:
        contenedor = QWidget()
        capa = QVBoxLayout(contenedor)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)
        principal = QLabel(texto)
        principal.setStyleSheet(f"color: {estilo.TEXTO};")
        secundario = QLabel(original)
        secundario.setStyleSheet(
            f"color: {estilo.TEXTO_TENUE}; font-family: {estilo.FUENTE_MONO}; "
            f"font-size: 10px;"
        )
        capa.addWidget(principal)
        capa.addWidget(secundario)
        return contenedor

    def _selector(self, valor: str, ayuda: str):
        contenedor = QWidget()
        capa = QVBoxLayout(contenedor)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(2)

        fila = QHBoxLayout()
        fila.setSpacing(6)
        campo = QLineEdit(valor)
        fila.addWidget(campo, 1)
        boton = QPushButton("Buscar...")
        boton.setMaximumWidth(90)
        boton.clicked.connect(lambda: self._elegir(campo))
        fila.addWidget(boton)
        capa.addLayout(fila)

        nota = QLabel(ayuda)
        nota.setObjectName("leyenda")
        nota.setWordWrap(True)
        capa.addWidget(nota)
        return campo, contenedor

    def _elegir(self, campo: QLineEdit) -> None:
        carpeta = QFileDialog.getExistingDirectory(
            self, "Elegi la carpeta", campo.text() or str(Path.home())
        )
        if carpeta:
            campo.setText(carpeta)

    def _origenes(self) -> QWidget:
        marco = QFrame()
        marco.setObjectName("panel")
        capa = QVBoxLayout(marco)
        capa.setContentsMargins(12, 9, 12, 10)
        capa.setSpacing(2)

        titulo = QLabel("DE DONDE SALIO CADA VALOR")
        titulo.setObjectName("tituloPanel")
        capa.addWidget(titulo)

        if not self.p.origen:
            vacio = QLabel("Sin configuracion previa.")
            vacio.setObjectName("leyenda")
            capa.addWidget(vacio)
        else:
            for campo, procedencia in self.p.origen.items():
                fila = QLabel(f"{campo}: {procedencia}")
                fila.setObjectName("leyenda")
                capa.addWidget(fila)
        return marco

    # ------------------------------------------------------------------

    def _volcar(self) -> None:
        self.p.carpeta_datos = self.txt_datos.text().strip()
        self.p.carpeta_datos2 = self.txt_datos2.text().strip()
        self.p.sucursal = self.txt_sucursal.text().strip()
        self.p.carpeta_zip = self.txt_zip.text().strip()
        self.p.codepage = self.cmb_codepage.currentText()

    def _detectar(self) -> None:
        """Vuelve a tomar el entorno del CONFIG.DBF del ERP.

        Aca si se pisan los valores actuales: el usuario lo pidio
        explicitamente. La autodeteccion del arranque, en cambio, solo
        rellena lo que este vacio.
        """
        from ..config import completar_desde_erp

        self._volcar()
        entorno = completar_desde_erp(
            self.p, self.txt_datos.text().strip() or None, forzar=True
        )

        if entorno is None:
            self.lbl_estado.setStyleSheet(f"color: {estilo.AMBAR};")
            self.lbl_estado.setText(
                "No se encontro el CONFIG.DBF del sistema.\n"
                "Se busco en la carpeta de este programa y en la de datos. "
                "Si el ERP esta en otro lado, indicalo a mano."
            )
            return

        self.txt_datos.setText(self.p.carpeta_datos)
        self.txt_datos2.setText(self.p.carpeta_datos2)
        self.txt_zip.setText(self.p.carpeta_zip)
        self.txt_sucursal.setText(self.p.sucursal)

        self.lbl_estado.setStyleSheet(f"color: {estilo.VERDE};")
        self.lbl_estado.setText("Tomado de " + entorno.descripcion())
        self._verificar()

    def _verificar(self) -> None:
        self._volcar()
        problemas = self.p.validar()
        avisos = self.p.avisos()

        if problemas:
            self.lbl_estado.setStyleSheet(f"color: {estilo.ROJO};")
            self.lbl_estado.setText("• " + "\n• ".join(problemas))
            return

        mensaje = ["Las tablas se encontraron correctamente."]
        try:
            from ..dbf import TablaDBF
            from ..config import resolver_archivo

            with TablaDBF(
                resolver_archivo(self.p.ruta_articulo), codepage=self.p.codepage
            ) as tabla:
                mensaje.append(
                    f"ARTICULO.DBF: {tabla.cantidad_registros:,} registros, "
                    f"codepage {tabla.codepage} ({tabla.codepage_origen})."
                )
                faltantes = [
                    c for c in ("AR_SUCU", "AR_CODI", "AR_CANT", "AR_COST", "AR_PROV")
                    if not tabla.tiene(c)
                ]
                if faltantes:
                    mensaje.append(
                        "OJO: faltan campos esperados: " + ", ".join(faltantes)
                    )
        except Exception as error:
            self.lbl_estado.setStyleSheet(f"color: {estilo.ROJO};")
            self.lbl_estado.setText(f"No se pudo leer ARTICULO.DBF: {error}")
            return

        color = estilo.AMBAR if avisos else estilo.VERDE
        self.lbl_estado.setStyleSheet(f"color: {color};")
        self.lbl_estado.setText("\n".join(mensaje + avisos))

    def _aceptar(self) -> None:
        self._volcar()
        problemas = self.p.validar()
        if problemas:
            QMessageBox.warning(
                self, "Falta configurar", "• " + "\n• ".join(problemas)
            )
            return
        try:
            self.p.guardar()
        except OSError as error:
            QMessageBox.warning(
                self, "No se pudo guardar",
                f"La configuracion no se pudo guardar en disco:\n{error}\n\n"
                "El programa igual va a arrancar con estos valores.",
            )
        self.accept()
