"""Utilidades compartidas por las tres salidas."""

from __future__ import annotations

import datetime
import os
import re
from pathlib import Path


def carpeta_salida() -> Path:
    """El Escritorio del usuario, igual que el original.

    En VFP esto era WScript.Shell + SpecialFolders("Desktop") con SYS(2023)
    como respaldo. Aca se prueban las variantes de Windows, se cae al
    escritorio de Linux/macOS y, si nada existe, a la carpeta temporal.
    """
    candidatos: list[Path] = []

    perfil = os.environ.get("USERPROFILE")
    if perfil:
        candidatos.append(Path(perfil) / "Desktop")
        candidatos.append(Path(perfil) / "Escritorio")
        candidatos.append(Path(perfil) / "OneDrive" / "Desktop")
        candidatos.append(Path(perfil) / "OneDrive" / "Escritorio")

    casa = Path.home()
    candidatos.append(casa / "Desktop")
    candidatos.append(casa / "Escritorio")

    for candidato in candidatos:
        if candidato.is_dir():
            return candidato

    return Path(os.environ.get("TEMP") or "/tmp")


def nombre_archivo(prefijo: str, etiqueta: str, extension: str) -> Path:
    """Nombre unico y sin caracteres prohibidos.

    CHRTRAN(nombre, " /\\:*?|<>\"", "_________") en el original.
    """
    limpio = re.sub(r'[\\/:*?"<>|\s]+', "_", etiqueta.strip()) or "SIN_NOMBRE"
    limpio = limpio.strip("_")[:60]
    marca = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return carpeta_salida() / f"{prefijo}_{limpio}_{marca}{extension}"


def encabezado_pedido(proveedor, parametros, modo: int) -> list[str]:
    from ..calculo import MODO_ROTACION

    return [
        f"Proveedor: {proveedor.nombre.strip() if proveedor else 'Sin proveedor'}",
        f"Sucursal: {parametros.sucursal}",
        f"Fecha: {datetime.date.today().strftime('%d/%m/%Y')}",
        "Modo: " + ("Inteligente (rotacion)" if modo == MODO_ROTACION else "Manual (min/max)"),
    ]
