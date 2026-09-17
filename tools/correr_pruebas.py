"""Corre todas las pruebas. python3 tools/correr_pruebas.py"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def main() -> int:
    fallos = 0
    for archivo in sorted((RAIZ / "tests").glob("test_*.py")):
        print(f"\n== {archivo.name} " + "=" * (56 - len(archivo.name)))
        resultado = subprocess.run(
            [sys.executable, str(archivo)], cwd=str(RAIZ)
        )
        fallos += resultado.returncode != 0

    print("\n" + "=" * 60)
    print("TODO OK" if not fallos else f"{fallos} archivo(s) con fallos")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
