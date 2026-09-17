# -*- mode: python ; coding: utf-8 -*-
"""
Empaquetado con PyInstaller.

    pip install pyinstaller
    pyinstaller reposicion.spec

Deja reposicion.exe en dist\\. Es un unico archivo: se copia a la carpeta del
sistema y no hace falta instalar Python en las maquinas donde corre.

NOTAS SOBRE EL RESULTADO:

  - Tamanio: entre 45 y 70 MB. Casi todo es Qt. Se puede bajar bastante
    excluyendo los modulos de Qt que no se usan (ver `excludes`).

  - Arranque: 2 o 3 segundos la primera vez, porque el ejecutable se
    descomprime en una carpeta temporal. Si eso molesta, cambiar
    `onefile` por una carpeta (`COLLECT`), que arranca casi al instante
    a cambio de repartir una carpeta en vez de un archivo suelto.

  - Antivirus: los ejecutables de PyInstaller a veces disparan falsos
    positivos. Firmar el .exe con un certificado de code signing lo
    resuelve; agregarlo a las excepciones del antivirus corporativo
    tambien.

  - 32 vs 64 bits: no importa. El programa lee los DBF por su cuenta, no
    usa el driver OLE DB de Visual FoxPro (que solo existe en 32 bits).
    Se puede compilar en 64 bits sin problemas.
"""

import os
import sys

bloque_cifrado = None

# --------------------------------------------------------------------------
# Adornos OPCIONALES: icono y recurso de version de Windows.
#
# PyInstaller no avisa que faltan: revienta con un FileNotFoundError despues
# de haber hecho todo el analisis, o sea despues de medio minuto de trabajo
# tirado. Por eso se comprueba que existan en vez de nombrarlos a ciegas.
#
# Para generarlos:   python tools/generar_icono.py
# Sin ellos el .exe sale igual, solo que con el icono generico de Windows.
# --------------------------------------------------------------------------
# SPEC lo inyecta PyInstaller; el getcwd es por si el .spec se ejecuta suelto
AQUI = os.path.dirname(os.path.abspath(globals().get("SPEC", os.getcwd())))

def _si_existe(nombre):
    ruta = os.path.join(AQUI, nombre)
    if os.path.isfile(ruta):
        return ruta
    print(f"AVISO: no se encontro {nombre}, se compila sin eso. "
          f"Para generarlo: python tools/generar_icono.py")
    return None

ICONO = _si_existe("reposicion.ico") if sys.platform == "win32" else None
VERSION = _si_existe("version.txt") if sys.platform == "win32" else None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "app.salidas.excel",
        "app.salidas.pdf",
        "app.salidas.informe",
        "app.ui.ayuda",
        "app.ui.ajustes",
        "app.ui.dialogo_rotacion",
        "app.rotacion",
        "app.dbf_escritor",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Qt trae mucho mas de lo que esta aplicacion usa.
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick", "PySide6.QtQuick", "PySide6.QtQml",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
        "PySide6.QtDataVisualization", "PySide6.QtBluetooth",
        "PySide6.QtPositioning", "PySide6.QtNetworkAuth",
        "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtTest",
        "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtSql",
        # Cientificos que arrastran dependencias enormes y no se usan
        "matplotlib", "numpy", "scipy", "pandas", "tkinter",
        "IPython", "notebook", "pytest",
        #
        # OJO: Pillow (PIL) NO se puede excluir, aunque este programa no
        # maneje imagenes. reportlab.lib.utils hace `from PIL import Image`
        # en el nivel del modulo, sin try/except, asi que sacarlo hace que
        # el .exe compile igual y reviente recien cuando el usuario aprieta
        # "Imprimir / Exportar PDF". Son unos MB que hay que pagar.
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=bloque_cifrado)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="reposicion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX dispara mas falsos positivos de antivirus
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # sin ventana negra de consola detras
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICONO,
    version=VERSION,
)
