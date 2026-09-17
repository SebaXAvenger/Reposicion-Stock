"""
Genera reposicion.ico y version.txt para el empaquetado con PyInstaller.

    python3 tools/generar_icono.py

Los dos archivos van a la raiz del proyecto, que es donde los busca el
.spec. Se pueden regenerar cuando cambie la version.

El icono se dibuja por codigo a proposito: asi no hay que arrastrar un
binario en el repositorio y se puede ajustar el color desde la paleta de la
aplicacion sin abrir un editor de imagenes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RAIZ = Path(__file__).resolve().parent.parent

VERSION = (1, 0, 0, 0)
NOMBRE = "Centro de control de quiebres de stock"
EMPRESA = ""
DESCRIPCION = "Analisis de reposicion de stock"


# ---------------------------------------------------------------------------
# Icono
# ---------------------------------------------------------------------------

def generar_icono(destino: Path) -> Path:
    """Un cajon de deposito con una flecha de reposicion, sobre el azul de
    la aplicacion. Se generan todos los tamanios que pide Windows."""
    from PIL import Image, ImageDraw

    FONDO = (26, 30, 38)        # el fondo de los paneles
    ACENTO = (47, 127, 216)     # el azul de ACTUALIZAR
    CLARO = (230, 235, 244)
    VERDE = (110, 214, 148)

    lado = 256
    imagen = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(imagen)

    # Fondo redondeado
    dibujo.rounded_rectangle([0, 0, lado - 1, lado - 1], radius=52, fill=FONDO)
    dibujo.rounded_rectangle(
        [0, 0, lado - 1, lado - 1], radius=52, outline=ACENTO, width=6
    )

    # Tres barras: el stock de cada articulo, una baja (la que hay que pedir)
    base = 196
    ancho = 38
    separacion = 22
    izquierda = 44
    alturas = [96, 58, 128]
    colores = [CLARO, ACENTO, CLARO]

    for indice, (alto, color) in enumerate(zip(alturas, colores)):
        x = izquierda + indice * (ancho + separacion)
        dibujo.rounded_rectangle(
            [x, base - alto, x + ancho, base], radius=8, fill=color
        )

    # La linea del punto de pedido
    dibujo.line([32, 132, lado - 32, 132], fill=VERDE, width=5)

    # Piso
    dibujo.rounded_rectangle([32, base + 8, lado - 32, base + 18], radius=5,
                             fill=(60, 70, 88))

    tamanios = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    imagen.save(destino, format="ICO", sizes=tamanios)
    return destino


# ---------------------------------------------------------------------------
# Recurso de version de Windows
# ---------------------------------------------------------------------------

PLANTILLA_VERSION = '''# Recurso de version de Windows, generado por tools/generar_icono.py
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version},
    prodvers={version},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '0c0a04b0',
        [StringStruct('CompanyName', {empresa!r}),
         StringStruct('FileDescription', {descripcion!r}),
         StringStruct('FileVersion', {version_texto!r}),
         StringStruct('InternalName', 'reposicion'),
         StringStruct('OriginalFilename', 'reposicion.exe'),
         StringStruct('ProductName', {nombre!r}),
         StringStruct('ProductVersion', {version_texto!r})])
    ]),
    VarFileInfo([VarStruct('Translation', [3082, 1200])])
  ]
)
'''


def generar_version(destino: Path) -> Path:
    destino.write_text(
        PLANTILLA_VERSION.format(
            version=VERSION,
            version_texto=".".join(str(n) for n in VERSION),
            nombre=NOMBRE,
            empresa=EMPRESA,
            descripcion=DESCRIPCION,
        ),
        encoding="utf-8",
    )
    return destino


if __name__ == "__main__":
    try:
        ruta_icono = generar_icono(RAIZ / "reposicion.ico")
        print(f"icono   -> {ruta_icono}")
    except ImportError:
        print("Sin Pillow instalado: no se genero el icono (no es obligatorio).")
        print("  pip install pillow")

    print(f"version -> {generar_version(RAIZ / 'version.txt')}")
