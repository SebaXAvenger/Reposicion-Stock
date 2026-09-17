"""
Corre el calculo sin interfaz y muestra el embudo de descartes.

    python3 tools/probar_calculo.py --data /ruta/DATOS --data2 /ruta/DATOS2 \
        --sucursal 1 [--modo 1|2] [--consolidar]

Sirve para verificar numeros contra el formulario original: los contadores
que imprime son los mismos cinco que instrumenta CandidatosRotacion.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.calculo import MODO_ROTACION, MotorReposicion  # noqa: E402
from app.config import Parametros  # noqa: E402
from app.datos import RepositorioERP  # noqa: E402
from app.vfp import transform_moneda  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--data2", default="")
    parser.add_argument("--sucursal", default="1")
    parser.add_argument("--modo", type=int, default=MODO_ROTACION)
    parser.add_argument("--punto", type=int, default=7)
    parser.add_argument("--cobertura", type=int, default=45)
    parser.add_argument("--consolidar", action="store_true")
    parser.add_argument("--mediana", action="store_true")
    parser.add_argument("--sin-excluir-esporadicos", action="store_true")
    parser.add_argument("--neg-cero", action="store_true")
    args = parser.parse_args()

    p = Parametros(
        carpeta_datos=args.data,
        carpeta_datos2=args.data2,
        sucursal=args.sucursal,
        punto_pedido=args.punto,
        cobertura=args.cobertura,
        criterio_mediana=args.mediana,
        excluir_esporadicos=not args.sin_excluir_esporadicos,
        negativo_como_cero=args.neg_cero,
        consolidar_sucursales=args.consolidar,
    )

    problemas = p.validar()
    if problemas:
        for problema in problemas:
            print("ERROR:", problema)
        return 1

    repo = RepositorioERP(p)
    catalogo = repo.cargar(con_remoto=args.consolidar, con_rotacion=True)

    print("=" * 78)
    for linea in catalogo.diagnostico:
        print("  ", linea)
    print("   tiempos:", {k: f"{v:.3f}s" for k, v in catalogo.tiempos.items()})
    print("=" * 78)

    motor = MotorReposicion(p, catalogo)
    resultado = motor.calcular(args.modo, args.consolidar)

    if not resultado.ok:
        print("SIN RESULTADO:", resultado.mensaje)
        return 2

    d = resultado.diagnostico
    print(resultado.leyenda_rotacion)
    print()
    print(f"Catalogo total ............ {d.total_catalogo:>8,}")
    print(f"Analizados (activos+suc) .. {d.analizados:>8,}")
    if args.modo == MODO_ROTACION:
        print(f"  - sin ventas ............ {d.desc_sin_venta:>8,}")
        print(f"  - sin demanda ........... {d.desc_sin_demanda:>8,}")
        print(f"  - esporadicos ........... {d.desc_esporadico:>8,}")
        print(f"  - stock suficiente ...... {d.desc_stock_ok:>8,}")
        print(f"  - cobertura cubierta .... {d.desc_cubierto:>8,}")
    else:
        print(f"  - por encima del minimo . {d.desc_sobre_minimo:>8,}")
        print(f"  - sin objetivo cargado .. {d.desc_sin_objetivo:>8,}")
    print(f"SUGERIDOS ................. {d.sugeridos:>8,}")
    print(f"  de los cuales negativos . {d.negativos:>8,}")
    print(f"Duracion .................. {d.duracion:>8.3f}s")
    print()

    proveedores, items, monto = resultado.total_general()
    print(
        f"{proveedores} proveedores  |  {items} articulos  |  "
        f"$ {transform_moneda(monto)}"
    )
    print()
    print(f"{'Proveedor':<40}{'Items':>7}{'Crit':>7}{'Monto':>18}")
    print("-" * 72)
    for prov in resultado.proveedores[:12]:
        print(
            f"{prov.nombre[:39]:<40}{prov.items:>7}{prov.criticos:>7}"
            f"{transform_moneda(prov.monto):>18}"
        )

    if resultado.proveedores:
        primero = resultado.proveedores[0]
        print()
        print(f"Detalle de {primero.nombre.strip()}:")
        print(
            f"{'Cod.Prov':<10}{'Descripcion':<44}{'Vta/mes':>9}"
            f"{'Dias':>7}{'Stock':>10}{'Pedir':>8}{'Subtotal':>16}"
        )
        print("-" * 104)
        for linea in resultado.lineas_de(primero.codigo)[:15]:
            print(
                f"{linea.cod_prov_articulo[:9]:<10}{linea.descripcion[:43]:<44}"
                f"{linea.vta_mes:>9.2f}{linea.dias_stock:>7.1f}"
                f"{linea.stock_total:>10.2f}{linea.cant_pedir:>8.0f}"
                f"{transform_moneda(linea.subtotal):>16}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
