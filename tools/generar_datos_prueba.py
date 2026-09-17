"""
Genera un juego de tablas DBF ficticias con la MISMA estructura de campos que
usa el formulario, para poder correr y verificar la aplicacion sin acceso al
ERP real.

    python3 tools/generar_datos_prueba.py [carpeta_destino] [cantidad]

Arma dos carpetas: DATOS (sucursal principal) y DATOS2 (la otra sucursal),
igual que sis_path_ y sis_path2.
"""

from __future__ import annotations

import datetime
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.dbf_writer import escribir_dbf  # noqa: E402

# Anchos EXACTOS de la tabla real (784 bytes por registro). Los campos
# extra estan a proposito: la tabla verdadera tiene 61 columnas y este
# programa usa 13, asi que las pruebas tienen que ejercitar la lectura
# selectiva sobre un registro ancho, no sobre uno de juguete.
CAMPOS_ARTICULO = [
    ("AR_SUCU", "C", 1, 0),
    ("AR_CODI", "C", 6, 0),       # 1 + 6 = 7, la clave que guarda DCC_ARTICU
    ("AR_DESC", "C", 100, 0),
    ("AR_OBSE", "C", 50, 0),
    ("AR_RUBR", "C", 3, 0),
    ("AR_SUBR", "C", 3, 0),
    ("AR_SSUB", "C", 3, 0),
    ("AR_PLU_", "C", 20, 0),
    ("AR_INTERNO", "C", 17, 0),
    ("ACTUALIZAD", "C", 12, 0),
    ("AR_PROV", "C", 7, 0),
    ("DESC_PROV", "C", 50, 0),
    ("AR_TIPO", "C", 2, 0),
    ("AR_CANT", "N", 13, 4),
    ("AR_CAN2", "N", 13, 4),
    ("AR_CANI", "N", 12, 4),
    ("AR_PESO", "N", 7, 2),
    ("AR_MINI", "N", 10, 4),
    ("AR_MAXI", "N", 12, 4),
    ("AR_FEIN", "D", 8, 0),
    ("AR_PVEN", "N", 12, 4),
    ("AR_COST", "N", 12, 4),
    ("AR_ACTIVO", "C", 1, 0),
    ("AR_MARCA", "C", 20, 0),
    ("AR_UBICACI", "C", 11, 0),
]

# CONFIG.DBF: de aca saca el ERP las rutas y la sucursal en principal.prg.
# El programa lo lee para configurarse solo.
CAMPOS_CONFIG = [
    ("CFG_PATH__", "C", 60, 0),
    ("CFG_P_SIS2", "C", 60, 0),
    ("CFG_RESPAL", "C", 60, 0),
    ("CFG_SUCURS", "C", 1, 0),
    ("CFG_CODSUC", "C", 3, 0),
    ("CFG_TITULO", "C", 40, 0),
    ("CFG_MAQUIN", "C", 2, 0),
    ("CFG_SERVER", "L", 1, 0),
    ("CFG_OBSERV", "C", 60, 0),
]

# Estructura real: OJO que PR_CODIGO es NUMERICO. La clave de 7 caracteres
# con la que AR_PROV referencia a esta tabla es PR_SUCURS + STR(PR_CODIGO, 6).
CAMPOS_PROVEEDO = [
    ("PR_SUCURS", "C", 1, 0),
    ("PR_CODIGO", "N", 6, 0),
    ("PR_NOMBRE", "C", 40, 0),
    ("PR_FANTAS", "C", 30, 0),
    ("PR_DIRECC", "C", 30, 0),
    ("PR_CUIT__", "C", 11, 0),
    ("PR_ACTIVO", "L", 1, 0),
]

# DOC_CLAVE_ mide 8 en la tabla real, no 14: la clave del comprobante es
# corta y eso importa, porque el cruce con DOCCUER es por ese campo.
CAMPOS_DOCUM = [
    ("DOC_CLIPRO", "C", 1, 0),
    ("DOC_CUENTA", "C", 7, 0),
    ("DOC_FECEMI", "D", 8, 0),
    ("DOC_FECVTO", "D", 8, 0),
    ("DOC_TIPDOC", "C", 2, 0),
    ("DOC_NRODOC", "C", 13, 0),
    ("DOC_TOTAL_", "N", 14, 2),
    ("DOC_CLAVE_", "C", 8, 0),
    ("DOC_OBSERV", "C", 25, 0),
    ("DOC_ANULED", "L", 1, 0),
    ("DOC_SUCURS", "C", 1, 0),
]

CAMPOS_DOCCUER = [
    ("DCC_CLAVE_", "C", 8, 0),
    ("DCC_ARTICU", "C", 7, 0),     # = AR_SUCU + AR_CODI
    ("DCC_CANTID", "N", 10, 3),
    ("DCC_PRECIO", "N", 14, 4),
    ("DCC_TASIVA", "N", 5, 2),
    ("DCC_BONIFI", "N", 6, 2),
    ("DCC_FECHA_", "D", 8, 0),
    ("DCC_COSTO_", "N", 12, 4),
]

CAMPOS_ROTACION = [
    ("ROT_ARTIC", "C", 7, 0),   # = AR_SUCU + AR_CODI, igual que DCC_ARTICU
    ("ROT_ORIGE", "C", 1, 0),
    ("ROT_PROME", "N", 12, 2),
    ("ROT_MEDIA", "N", 12, 2),
    ("ROT_MESCON", "N", 4, 0),
    ("ROT_UNIDS", "N", 14, 3),
    ("ROT_ULTVTA", "D", 8, 0),
    ("ROT_FECCAL", "D", 8, 0),
    ("ROT_NEGRO", "L", 1, 0),
    ("ROT_DESDE", "D", 8, 0),
    ("ROT_HASTA", "D", 8, 0),
    ("ROT_MESES", "N", 4, 0),
]

NOMBRES_PROVEEDOR = [
    "ORANGE BLUE IMPORT & EXPORT TOOLS", "ROGGIO LUIS S.A.",
    "LUSOTOFF ARGENTINA S.A.", "DUFF IRL S.R.L.", "BARBUY TEAM S.A.",
    "TUBOS SRL", "RODOLFO RERGER S. R. L.", "FERRETERA CENTRAL IT S.R.L.",
    "EINHELL ARGENTINA S.A.", "SANCHEZ NESTOR FERNANDO",
    "PREMEN TOOLS ARGENTINA S.A.", "FERRETERA GENERAL PAZ",
    "BARAVALLE ROBERTO RUBEN", "RADIO ELECTRON S.A.",
    "RC DISTRIBUCIONES SRL", "BULONFER S.A.", "ROLAUT S.A.",
    "HERRAMIENTAS DEL SUR SRL", "METALURGICA VIRREYES", "ABRASIVOS UNIDOS SA",
]

FAMILIAS = [
    ("AMOL", "AMOLADORA", "UN"), ("MECH", "MECHA", "UN"),
    ("DISC", "DISCO DE CORTE", "UN"), ("GANC", "GANCHO", "UN"),
    ("MOSQ", "MOSQUETON", "UN"), ("CINC", "CINCEL", "UN"),
    ("MART", "MARTILLO DEMOLEDOR", "UN"), ("MALL", "MALLA SOLDADA", "M2"),
    ("GRIL", "GRILLETE", "UN"), ("FECA", "FECALERA EXTENSIBLE", "UN"),
    ("LLAV", "LLAVE COMBINADA", "UN"), ("PINZ", "PINZA UNIVERSAL", "UN"),
    ("TORN", "TORNILLO AUTOPERFORANTE", "CJA"), ("SOGA", "SOGA POLIPROPILENO", "MT"),
    ("CADE", "CADENA GALVANIZADA", "MT"), ("BULO", "BULON HEXAGONAL", "UN"),
]

MARCAS = [
    "STANLEY", "DEWALT", "BOSCH", "MAKITA", "BLACK+DECKER", "EINHELL",
    "NEBRASKA", "FINISTERRE", "EEZTA", "TRAMONTINA", "BAHCO", "GAMMA",
]

MEDIDAS = [
    '1/4"', '3/8"', '1/2"', '5/8"', '3/4"', '1"', "4.5MM", "6MM", "8MM",
    "10MM", "12MM", "115MM", "230MM", "20V", "1600W", "2000W", "50CM",
]


def generar(
    destino: Path,
    cantidad: int = 4000,
    semilla: int = 20260821,
    clave_corta: bool = False,
) -> None:
    random.seed(semilla)
    hoy = datetime.date.today()

    carpeta1 = destino / "DATOS"
    carpeta2 = destino / "DATOS2"
    carpeta1.mkdir(parents=True, exist_ok=True)
    carpeta2.mkdir(parents=True, exist_ok=True)

    # --- Proveedores ---------------------------------------------------
    proveedores = []
    codigos_proveedor = []
    for i, nombre in enumerate(NOMBRES_PROVEEDOR, start=1):
        numero = i * 13
        # La clave que guarda AR_PROV: sucursal + codigo justificado a la
        # derecha en 6 lugares, con espacios. El proveedor 13 es "1    13".
        codigo = "1" + str(numero).rjust(6)
        codigos_proveedor.append(codigo)
        proveedores.append(
            {
                "PR_SUCURS": "1",
                "PR_CODIGO": numero,          # numerico, como en la tabla real
                "PR_NOMBRE": nombre[:40],
                "PR_FANTAS": nombre.split()[0][:30],
                "PR_DIRECC": "",
                "PR_CUIT__": f"30{random.randint(10000000, 99999999)}{random.randint(0, 9)}",
                "PR_ACTIVO": True,
            }
        )
    escribir_dbf(carpeta1 / "PROVEEDO.DBF", CAMPOS_PROVEEDO, proveedores)

    # --- CONFIG.DBF, para probar la autodeteccion del entorno -----------
    escribir_dbf(destino / "CONFIG.DBF", CAMPOS_CONFIG, [{
        "CFG_PATH__": str(carpeta1),
        "CFG_P_SIS2": str(carpeta2),
        "CFG_RESPAL": str(destino / "ZIP"),
        "CFG_SUCURS": "1",
        "CFG_CODSUC": "001",
        "CFG_TITULO": "FERRETERIA DE PRUEBA",
        "CFG_MAQUIN": "1A",
        "CFG_SERVER": False,
        "CFG_OBSERV": "",
    }])
    print(f"CONFIG.DBF           1 fila    -> {destino}")

    # --- Articulos ------------------------------------------------------
    articulos_1 = []
    articulos_2 = []
    rotacion = []

    desde = datetime.date(hoy.year - 1, hoy.month, 1)
    hasta = datetime.date(hoy.year, hoy.month, 1) - datetime.timedelta(days=1)

    for n in range(cantidad):
        prefijo, base_desc, unidad = random.choice(FAMILIAS)
        # AR_CODI mide 6 en la tabla real. La clave que ve DCC_ARTICU es
        # AR_SUCU + AR_CODI = 7 caracteres.
        codigo = f"{prefijo[:1]}{n:05d}"
        clave = "1" + codigo

        descripcion = " ".join(
            [
                base_desc,
                random.choice(MARCAS),
                random.choice(MEDIDAS),
                random.choice(["", "PROFESIONAL", "INDUSTRIAL", "REFORZADO", ""]),
            ]
        ).strip()

        # 8% sin proveedor asignado, para ejercitar el grupo *SINPRO
        proveedor = "" if random.random() < 0.08 else random.choice(codigos_proveedor)
        # DESC_PROV: el nombre del proveedor denormalizado en ARTICULO.
        # En un 15% se deja vacio, que es lo habitual en datos reales.
        indice = codigos_proveedor.index(proveedor) if proveedor else -1
        desc_prov = (
            NOMBRES_PROVEEDOR[indice]
            if indice >= 0 and random.random() > 0.15 else ""
        )

        costo = round(random.choice([1, 1, 1, 10, 100]) * random.uniform(500, 90000), 2)

        # Distribucion de stock parecida a la real: bastante en cero,
        # un 7% en negativo (errores de inventario) y el resto positivo.
        sorteo = random.random()
        if sorteo < 0.07:
            stock = -round(random.uniform(1, 60), 3)
        elif sorteo < 0.30:
            stock = 0.0
        else:
            stock = round(random.uniform(1, 400), 3)

        # Solo unos poquitos tienen min/max cargados: el original avisa que
        # hoy son 2 de 33.008, aca se deja un 1% para que el modo manual
        # devuelva algo.
        if random.random() < 0.01:
            minimo = round(random.uniform(5, 40), 2)
            maximo = minimo + round(random.uniform(10, 80), 2)
        else:
            minimo = 0.0
            maximo = 0.0

        activo = "S" if random.random() > 0.05 else "N"

        articulos_1.append(
            {
                "AR_SUCU": "1",
                "AR_CODI": codigo,
                # PADL a 20, con los espacios ADELANTE, tal como el ERP real
                "AR_PLU_": f"P{n:06d}".rjust(20),
                "AR_DESC": descripcion,
                "AR_TIPO": unidad,
                "AR_PROV": proveedor,
                "DESC_PROV": desc_prov,
                "AR_MINI": minimo,
                "AR_MAXI": maximo,
                "AR_CANT": stock,
                "AR_COST": costo,
                "AR_ACTIVO": activo,
                "AR_RUBR": prefijo[:3],
                "AR_MARCA": descripcion.split()[1] if len(descripcion.split()) > 1 else "",
                "AR_UBICACI": f"{random.choice('ABCDEFG')}-{random.randint(1, 40):02d}-{random.randint(1, 9)}",
                "AR_OBSE": "",
            }
        )

        # La otra sucursal: mismo maestro, distinto stock
        articulos_2.append(
            {
                **articulos_1[-1],
                "AR_CANT": round(random.uniform(-10, 250), 3)
                if random.random() > 0.25
                else 0.0,
            }
        )

        # --- Rotacion -----------------------------------------------------
        # 65% del catalogo tuvo alguna venta en la ventana
        if random.random() < 0.65:
            meses_con = random.choice([1, 1, 2, 3, 5, 8, 11, 12, 12])
            promedio = round(random.uniform(0.2, 60), 2)
            mediana = round(promedio * random.uniform(0.3, 1.1), 2)
            if meses_con <= 1:
                mediana = 0.0
            rotacion.append(
                {
                    "ROT_ARTIC": clave,
                    "ROT_ORIGE": "L",
                    "ROT_PROME": promedio,
                    "ROT_MEDIA": mediana,
                    "ROT_MESCON": meses_con,
                    "ROT_UNIDS": round(promedio * meses_con, 3),
                    "ROT_ULTVTA": hoy - datetime.timedelta(days=random.randint(1, 300)),
                    "ROT_FECCAL": hoy,
                    "ROT_NEGRO": True,
                    "ROT_DESDE": desde,
                    "ROT_HASTA": hasta,
                    "ROT_MESES": 12,
                }
            )
            if random.random() < 0.5:
                promedio_r = round(promedio * random.uniform(0.2, 1.5), 2)
                rotacion.append(
                    {
                        "ROT_ARTIC": clave,
                        "ROT_ORIGE": "R",
                        "ROT_PROME": promedio_r,
                        "ROT_MEDIA": round(promedio_r * 0.8, 2),
                        "ROT_MESCON": max(1, meses_con - random.randint(0, 3)),
                        "ROT_UNIDS": round(promedio_r * meses_con, 3),
                        "ROT_ULTVTA": hoy - datetime.timedelta(days=random.randint(1, 300)),
                        "ROT_FECCAL": hoy,
                        "ROT_NEGRO": True,
                        "ROT_DESDE": desde,
                        "ROT_HASTA": hasta,
                        "ROT_MESES": 12,
                    }
                )

    escribir_dbf(carpeta1 / "ARTICULO.DBF", CAMPOS_ARTICULO, articulos_1)
    escribir_dbf(carpeta2 / "ARTICULO.DBF", CAMPOS_ARTICULO, articulos_2)
    escribir_dbf(carpeta1 / "ROTACION.DBF", CAMPOS_ROTACION, rotacion)

    print(f"ARTICULO.DBF   {len(articulos_1):>7,} filas   -> {carpeta1}")
    print(f"ARTICULO.DBF   {len(articulos_2):>7,} filas   -> {carpeta2}")
    print(f"PROVEEDO.DBF   {len(proveedores):>7,} filas   -> {carpeta1}")
    print(f"ROTACION.DBF   {len(rotacion):>7,} filas   -> {carpeta1}")

    # --- Comprobantes ---------------------------------------------------
    claves = [a["AR_SUCU"] + a["AR_CODI"] for a in articulos_1]
    for carpeta, sucursal, cantidad_docs in (
        (carpeta1, "1", max(400, cantidad // 3)),
        (carpeta2, "2", max(300, cantidad // 5)),
        (destino / "ZIP", "", max(200, cantidad // 8)),
    ):
        carpeta.mkdir(parents=True, exist_ok=True)
        docs, renglones = _generar_comprobantes(
            claves, sucursal, cantidad_docs, hoy, clave_corta
        )
        escribir_dbf(carpeta / "DOCUM.DBF", CAMPOS_DOCUM, docs)
        escribir_dbf(carpeta / "DOCCUER.DBF", CAMPOS_DOCCUER, renglones)
        print(
            f"DOCUM.DBF      {len(docs):>7,} filas   -> {carpeta}\n"
            f"DOCCUER.DBF    {len(renglones):>7,} filas   -> {carpeta}"
        )


def _generar_comprobantes(
    claves_articulo: list[str],
    sucursal: str,
    cantidad: int,
    hoy: datetime.date,
    clave_corta: bool,
) -> tuple[list[dict], list[dict]]:
    """Arma un DOCUM + DOCCUER con dos anios de movimiento.

    Incluye a proposito casos que el calculo tiene que saber manejar:
    comprobantes anulados, de proveedor (DOC_CLIPRO="P"), tipos que no
    cuentan, notas de credito que restan, remitos internos, y en el
    pendrive comprobantes con DOC_SUCURS vacio.
    """
    tipos = ["FC"] * 60 + ["FE"] * 15 + ["ND"] * 5 + ["NC"] * 6 + ["CE"] * 3 + \
            ["RI"] * 6 + ["PR"] * 3 + ["NV"] * 2
    documentos = []
    renglones = []

    for n in range(cantidad):
        # DOC_CLAVE_ mide 8: prefijo de origen + 7 digitos
        clave = f"{sucursal or 'Z'}{n:07d}"[:8]
        fecha = hoy - datetime.timedelta(days=random.randint(1, 760))
        tipo = random.choice(tipos)

        # El pendrive mezcla sucursales, y algunos vienen sin cargar
        if sucursal:
            doc_sucursal = sucursal
        else:
            doc_sucursal = random.choice(["1", "1", "2", "", ""])

        documentos.append({
            "DOC_CLAVE_": clave,
            "DOC_FECEMI": fecha,
            "DOC_TIPDOC": tipo,
            "DOC_SUCURS": doc_sucursal,
            "DOC_CLIPRO": "C" if random.random() > 0.12 else "P",
            "DOC_ANULED": random.random() < 0.04,
            "DOC_NRODOC": f"0001-{n:08d}",
            "DOC_CUENTA": f"1{random.randint(1, 9999):>6}",
            "DOC_FECVTO": fecha,
            "DOC_TOTAL_": round(random.uniform(1000, 900000), 2),
            "DOC_OBSERV": "",
        })

        for _ in range(random.randint(1, 6)):
            articulo = random.choice(claves_articulo)
            if clave_corta:
                articulo = articulo[1:]
            renglones.append({
                "DCC_CLAVE_": clave,
                "DCC_ARTICU": articulo,
                "DCC_CANTID": round(random.uniform(1, 40), 3),
                "DCC_PRECIO": round(random.uniform(1000, 200000), 2),
                "DCC_TASIVA": 21.0,
                "DCC_BONIFI": 0.0,
                "DCC_COSTO_": round(random.uniform(500, 150000), 2),
                # Vacio a proposito en el 98%, como en la base real
                "DCC_FECHA_": fecha if random.random() < 0.02 else None,
            })

    return documentos, renglones


if __name__ == "__main__":
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/claude/prueba")
    total = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
    generar(carpeta, total, clave_corta="--clave-corta" in sys.argv)
