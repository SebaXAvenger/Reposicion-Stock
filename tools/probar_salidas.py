"""Genera las tres salidas (Excel, PDF, informe) con datos de prueba."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.calculo import MODO_ROTACION, MotorReposicion  # noqa: E402
from app.config import Parametros  # noqa: E402
from app.datos import RepositorioERP  # noqa: E402
from app.salidas.excel import exportar_pedido  # noqa: E402
from app.salidas.informe import generar_informe  # noqa: E402
from app.salidas.pdf import exportar_pedido_pdf  # noqa: E402


def main() -> int:
    parametros = Parametros(
        carpeta_datos=sys.argv[1] if len(sys.argv) > 1 else "/home/claude/prueba/DATOS",
        carpeta_datos2=sys.argv[2] if len(sys.argv) > 2 else "/home/claude/prueba/DATOS2",
        sucursal="1",
        consolidar_sucursales=True,
    )
    catalogo = RepositorioERP(parametros).cargar(con_remoto=True)
    resultado = MotorReposicion(parametros, catalogo).calcular(MODO_ROTACION, True)

    if not resultado.ok:
        print("Sin resultado:", resultado.mensaje)
        return 1

    proveedor = resultado.proveedores[0]
    lineas = [l for l in resultado.lineas_de(proveedor.codigo) if l.cant_pedir > 0]

    print("Excel  ->", exportar_pedido(lineas, proveedor, parametros, MODO_ROTACION))
    print("PDF    ->", exportar_pedido_pdf(lineas, proveedor, parametros, MODO_ROTACION))
    print("Informe->", generar_informe(resultado, parametros, catalogo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
