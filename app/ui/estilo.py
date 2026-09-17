"""
Paleta y hoja de estilos.

Todo lo que en el formulario VFP se resolvia a mano (AddObject de shapes con
Curvature, DisabledBackColor para simular una tarjeta, DynamicBackColor con
expresiones IIF anidadas) aca es una hoja de estilos. Los colores semanticos
de las grillas siguen siendo los mismos que conoce el usuario:

    ROJO      stock en cero o negativo: se estan perdiendo ventas ahora
    NARANJA   quedan menos de 7 dias de stock: urgente
    AMARILLO  llego al punto de pedido, todavia hay margen
    VERDE     no es un aviso: marca la columna que se puede editar
"""

from __future__ import annotations

from PySide6.QtGui import QColor

# --- Superficies -----------------------------------------------------------
FONDO_APP = "#12151b"
FONDO_PANEL = "#1a1e26"
FONDO_PANEL_ALTO = "#212630"
FONDO_CAMPO = "#161a21"
BORDE = "#2b3240"
BORDE_SUAVE = "#232936"

# --- Texto -----------------------------------------------------------------
TEXTO = "#e6ebf4"
TEXTO_SUAVE = "#98a3b6"
TEXTO_TENUE = "#6b7686"

# --- Acentos ---------------------------------------------------------------
ACENTO = "#2f7fd8"
ACENTO_CLARO = "#4a95e8"
ACENTO_OSCURO = "#2668b0"
AZUL = "#58a8ff"
VERDE = "#6ed694"
AMBAR = "#ffbe5a"
ROJO = "#ff7676"

# --- Colores semanticos de las grillas -------------------------------------
# Se conservan los mismos que usaba DynamicBackColor en VFP, pero adaptados
# a fondo oscuro: en la version original eran pasteles pensados para un fondo
# blanco y sobre oscuro quedaban como manchas planas.
FILA_CRITICA = QColor("#4a2429")      # stock <= 0
FILA_URGENTE = QColor("#4a3520")      # menos de 7 dias
FILA_AVISO = QColor("#3d3a1f")        # llego al punto de pedido
FILA_EDITABLE = QColor("#1d3a29")     # columna A Pedir
FILA_EDITADA = QColor("#2a4a35")      # cantidad tocada a mano

TEXTO_CRITICO = QColor("#ff9b9b")
TEXTO_URGENTE = QColor("#ffc987")
TEXTO_NORMAL = QColor(TEXTO)
TEXTO_NUMERO = QColor("#cfd8e6")
TEXTO_APAGADO = QColor(TEXTO_TENUE)

FUENTE = '"Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", sans-serif'
FUENTE_MONO = '"Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace'


def hoja_de_estilos() -> str:
    return f"""
QWidget {{
    background-color: {FONDO_APP};
    color: {TEXTO};
    font-family: {FUENTE};
    font-size: 12px;
}}

/* ---------- Encabezado ---------- */
#barraTitulo {{
    background-color: {FONDO_PANEL};
    border-bottom: 1px solid {BORDE};
}}
#tituloApp {{
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.6px;
    color: {TEXTO};
}}

/* ---------- Tarjetas de indicadores ---------- */
#tarjetaKpi {{
    background-color: {FONDO_PANEL_ALTO};
    border: 1px solid {BORDE};
    border-radius: 8px;
}}
#tarjetaKpi QLabel {{ background: transparent; }}
#kpiRotulo {{
    color: {TEXTO_SUAVE};
    font-size: 11px;
    letter-spacing: 0.7px;
    font-weight: 600;
}}
#kpiValor {{
    color: {TEXTO};
    font-size: 17px;
    font-weight: 700;
}}
#kpiIcono {{ font-size: 15px; }}

/* ---------- Paneles ---------- */
#panel {{
    background-color: {FONDO_PANEL};
    border: 1px solid {BORDE_SUAVE};
    border-radius: 8px;
}}
#tituloPanel {{
    color: {TEXTO_SUAVE};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
    background: transparent;
    padding: 2px 2px 6px 2px;
}}
#seccion {{
    color: {TEXTO_SUAVE};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
    background: transparent;
}}
#leyenda {{
    color: {TEXTO_TENUE};
    font-size: 11px;
    background: transparent;
}}
#leyendaAviso {{
    color: {AMBAR};
    font-size: 11px;
    background: transparent;
}}

/* ---------- Botones ---------- */
QPushButton {{
    background-color: {FONDO_PANEL_ALTO};
    color: {TEXTO};
    border: 1px solid {BORDE};
    border-radius: 6px;
    padding: 7px 14px;
    font-size: 12px;
}}
QPushButton:hover {{ background-color: #2a3040; border-color: #3a4356; }}
QPushButton:pressed {{ background-color: #1c212b; }}
QPushButton:disabled {{ color: {TEXTO_TENUE}; border-color: {BORDE_SUAVE}; }}

QPushButton#primario {{
    background-color: {ACENTO};
    border: 1px solid {ACENTO};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton#primario:hover {{ background-color: {ACENTO_CLARO}; border-color: {ACENTO_CLARO}; }}
QPushButton#primario:pressed {{ background-color: {ACENTO_OSCURO}; }}

QPushButton#salir {{
    background-color: {FONDO_PANEL_ALTO};
    border: 1px solid {BORDE};
}}
QPushButton#salir:hover {{ background-color: #4a2429; border-color: #6d3238; }}

QPushButton#ayuda {{
    border-radius: 12px;
    padding: 0px;
    min-width: 24px; max-width: 24px;
    min-height: 24px; max-height: 24px;
    color: {TEXTO_SUAVE};
}}

/* ---------- Solapas ---------- */
QTabWidget::pane {{
    border: 1px solid {BORDE_SUAVE};
    border-radius: 8px;
    background-color: {FONDO_PANEL};
    top: -1px;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {TEXTO_TENUE};
    border: 1px solid transparent;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    padding: 7px 18px;
    margin-right: 2px;
    font-size: 12px;
}}
QTabBar::tab:hover {{ color: {TEXTO_SUAVE}; }}
QTabBar::tab:selected {{
    background-color: {FONDO_PANEL};
    color: {TEXTO};
    border: 1px solid {BORDE_SUAVE};
    border-bottom-color: {FONDO_PANEL};
    font-weight: 600;
}}

/* ---------- Campos ---------- */
QSpinBox, QLineEdit, QComboBox {{
    background-color: {FONDO_CAMPO};
    border: 1px solid {BORDE};
    border-radius: 5px;
    padding: 5px 8px;
    color: {TEXTO};
    selection-background-color: {ACENTO};
}}
QSpinBox:focus, QLineEdit:focus, QComboBox:focus {{ border-color: {ACENTO}; }}
/* Las flechas de spinbox y combo las dibuja el estilo Fusion. Sustituirlas
   por triangulos de CSS (el truco de los bordes) sale como un cuadradito
   solido en Qt, asi que solo se les cambia el fondo. */
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {FONDO_PANEL_ALTO};
    border-left: 1px solid {BORDE};
    width: 16px;
}}
QSpinBox::up-button {{ border-top-right-radius: 4px; }}
QSpinBox::down-button {{ border-bottom-right-radius: 4px; }}
QComboBox {{ padding-right: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {FONDO_PANEL_ALTO};
    border: 1px solid {BORDE};
    selection-background-color: {ACENTO};
    outline: none;
}}

QCheckBox {{ color: {TEXTO_SUAVE}; spacing: 7px; background: transparent; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {BORDE};
    border-radius: 4px;
    background-color: {FONDO_CAMPO};
}}
QCheckBox::indicator:hover {{ border-color: {ACENTO}; }}
QCheckBox::indicator:checked {{
    background-color: {ACENTO};
    border-color: {ACENTO};
    image: none;
}}

QLabel {{ background: transparent; }}

/* ---------- Grillas ---------- */
QTableView {{
    background-color: {FONDO_PANEL};
    alternate-background-color: #1d222b;
    gridline-color: {BORDE_SUAVE};
    border: 1px solid {BORDE_SUAVE};
    border-radius: 6px;
    selection-background-color: #24405e;
    selection-color: {TEXTO};
    outline: none;
}}
QTableView::item {{ padding: 3px 6px; border: none; }}
QTableView::item:focus {{ outline: none; }}

QHeaderView {{ background-color: {FONDO_PANEL_ALTO}; }}
QHeaderView::section {{
    background-color: {FONDO_PANEL_ALTO};
    color: {TEXTO_SUAVE};
    border: none;
    border-right: 1px solid {BORDE_SUAVE};
    border-bottom: 1px solid {BORDE};
    padding: 6px 6px;
    font-size: 11px;
    font-weight: 600;
}}
QHeaderView::section:hover {{ color: {TEXTO}; }}
QTableCornerButton::section {{
    background-color: {FONDO_PANEL_ALTO};
    border: none;
}}

QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #333c4d; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #45516a; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #333c4d; border-radius: 5px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: #45516a; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- Barra de estado / totales ---------- */
#panelTotales {{
    background-color: {FONDO_PANEL_ALTO};
    border: 1px solid {BORDE};
    border-radius: 8px;
}}
#rotuloTotal {{ color: {TEXTO_SUAVE}; font-size: 11px; background: transparent; }}
#valorTotal {{ color: {TEXTO}; font-size: 13px; font-weight: 700; background: transparent; }}
#valorTotalMonto {{ color: {VERDE}; font-size: 13px; font-weight: 700; background: transparent; }}

QSplitter::handle {{ background-color: transparent; }}
QSplitter::handle:horizontal {{ width: 8px; }}

QToolTip {{
    background-color: {FONDO_PANEL_ALTO};
    color: {TEXTO};
    border: 1px solid {BORDE};
    padding: 5px;
    border-radius: 4px;
}}

QProgressBar {{
    background-color: {FONDO_CAMPO};
    border: 1px solid {BORDE};
    border-radius: 4px;
    text-align: center;
    color: {TEXTO_SUAVE};
    height: 6px;
}}
QProgressBar::chunk {{ background-color: {ACENTO}; border-radius: 3px; }}
"""
