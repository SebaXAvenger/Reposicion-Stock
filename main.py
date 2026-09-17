"""
Centro de control de quiebres de stock.

Punto de entrada. Resuelve los parametros que antes venian del entorno del
ERP, valida que las tablas existan y levanta la ventana.

    reposicion.exe --data "X:\\SISTEMA\\DATOS\\" --data2 "Y:\\SUC2\\DATOS\\" \\
                   --sucursal "01"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtGui import QFont                                 # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox         # noqa: E402

from app.config import cargar_parametros                        # noqa: E402
from app.ui import estilo                                       # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parametros, argumentos = cargar_parametros(argv)

    aplicacion = QApplication(sys.argv[:1])
    aplicacion.setApplicationName("Reposicion")
    aplicacion.setOrganizationName("Reposicion")
    aplicacion.setStyle("Fusion")
    aplicacion.setStyleSheet(estilo.hoja_de_estilos())

    fuente = QFont("Segoe UI", 9)
    fuente.setStyleStrategy(QFont.PreferAntialias)
    aplicacion.setFont(fuente)

    from app.ui.ajustes import DialogoAjustes
    from app.ui.ventana import VentanaPrincipal

    # --- Modo diagnostico: revisa el entorno y sale, sin abrir la app ----
    if getattr(argumentos, "diagnostico", False):
        return _diagnosticar(parametros)

    # Ultima capa de la cascada: si despues de la linea de comandos, el
    # archivo de traspaso y los JSON guardados sigue faltando algo, se le
    # pregunta al usuario en vez de morir con un mensaje de error.
    problemas = parametros.validar()
    if problemas or argumentos.ajustes:
        dialogo = DialogoAjustes(parametros, primera_vez=bool(problemas))
        if dialogo.exec() != DialogoAjustes.Accepted:
            return 1

    problemas = parametros.validar()
    if problemas:
        QMessageBox.critical(
            None, "Error de entorno",
            "No se puede arrancar:\n\n• " + "\n• ".join(problemas),
        )
        return 1

    ventana = VentanaPrincipal(parametros)
    ventana.show()
    return aplicacion.exec()


def _diagnosticar(parametros) -> int:
    """Revisa el entorno, muestra el informe y sale.

    Devuelve 0 si no hay problemas bloqueantes y 1 si los hay, para que un
    .BAT o el propio ERP puedan encadenar sobre el resultado.
    """
    from app.diagnostico import correr_diagnostico
    from app.salidas.comun import carpeta_salida
    from app.ui.dialogo_diagnostico import DialogoDiagnostico

    informe, problemas = correr_diagnostico(parametros)

    ruta = None
    import datetime

    nombre = "diagnostico_reposicion_" + datetime.datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    ) + ".txt"
    for carpeta in (carpeta_salida(), Path.cwd()):
        try:
            ruta = carpeta / nombre
            ruta.write_text(informe, encoding="utf-8")
            break
        except OSError:
            ruta = None

    DialogoDiagnostico(informe, problemas, ruta).exec()
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
