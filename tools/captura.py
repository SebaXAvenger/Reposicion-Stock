"""
Captura la ventana a PNG sin necesidad de una pantalla real.

    QT_QPA_PLATFORM=offscreen python3 tools/captura.py salida.png

Sirve para revisar el aspecto de la interfaz desde un entorno sin escritorio.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import Parametros  # noqa: E402
from app.ui import estilo  # noqa: E402
from app.ui.ventana import VentanaPrincipal  # noqa: E402


def main() -> int:
    salida = Path(sys.argv[1] if len(sys.argv) > 1 else "captura.png")
    datos = sys.argv[2] if len(sys.argv) > 2 else "/home/claude/prueba/DATOS"
    datos2 = sys.argv[3] if len(sys.argv) > 3 else "/home/claude/prueba/DATOS2"
    ayuda = "--ayuda" in sys.argv
    ajustes = "--ajustes" in sys.argv
    manual = "--manual" in sys.argv
    rotacion = "--rotacion" in sys.argv

    aplicacion = QApplication(sys.argv[:1])
    aplicacion.setStyle("Fusion")
    aplicacion.setStyleSheet(estilo.hoja_de_estilos())
    aplicacion.setFont(QFont("DejaVu Sans", 9))

    parametros = Parametros(
        carpeta_datos=datos,
        carpeta_zip=str(Path(datos).parent / "ZIP"),
        carpeta_datos2=datos2,
        sucursal="1",
        consolidar_sucursales=True,
        modo=1 if manual else 2,
        manual_sin_parametros=manual,
    )

    if ajustes:
        from app.ui.ajustes import DialogoAjustes

        dialogo = DialogoAjustes(parametros)
        dialogo.show()
        aplicacion.processEvents()
        dialogo.grab().save(str(salida))
        print(f"Captura guardada en {salida}")
        return 0

    ventana = VentanaPrincipal(parametros)
    ventana.resize(1560, 880)
    ventana.show()

    def capturar() -> None:
        if ventana._trabajador is not None and ventana._trabajador.isRunning():
            QTimer.singleShot(200, capturar)
            return
        objetivo = ventana
        if rotacion:
            from app.ui.dialogo_rotacion import DialogoRotacion

            dialogo = DialogoRotacion(parametros, ventana)
            dialogo.show()
            aplicacion.processEvents()
            objetivo = dialogo
        elif ayuda:
            from app.ui.ayuda import DialogoAyuda

            dialogo = DialogoAyuda(ventana)
            dialogo.resize(1120, 760)
            dialogo.show()
            aplicacion.processEvents()
            objetivo = dialogo
        aplicacion.processEvents()
        objetivo.grab().save(str(salida))
        print(f"Captura guardada en {salida}")
        aplicacion.quit()

    QTimer.singleShot(900, capturar)
    return aplicacion.exec()


if __name__ == "__main__":
    raise SystemExit(main())
