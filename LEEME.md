# Centro de control de quiebres de stock

Port a Python + Qt del formulario `reposicion.scx` de Visual FoxPro, para
compilar como `.exe` y correr por fuera del ERP.

---

## Estado

| Parte | Estado |
|---|---|
| Lectura de ARTICULO / PROVEEDO / ROTACION | listo |
| Modo Inteligente (rotación) | listo, con sus 5 filtros y el reparto entre depósitos |
| Modo Manual (mín/máx) | listo |
| Interfaz | listo |
| Exportar a Excel | listo (openpyxl, ya no hace falta Excel instalado) |
| Imprimir / PDF | listo (ya no hace falta XFRX ni `rep_compras.frx`) |
| Informe del análisis | listo |
| Ayuda en pantalla | listo, texto portado del original |
| Recalcular rotación | listo: port completo de `calcular_rotacion.prg` |
| Autodetección del entorno | listo: lee `CONFIG.DBF`, igual que `principal.prg` |

Las estructuras de ARTICULO, PROVEEDO, DOCUM y DOCCUER están confirmadas
contra las tablas reales. Los datos de prueba las replican campo por campo.

---

## Cómo arranca

Cinco capas, de mayor a menor prioridad. Gana la primera que aporte cada valor.

1. **Línea de comandos** — es como lo llama el ERP.
2. **Archivo de traspaso** — `--config c:\temp\algo.json`, para cuando las rutas dan problemas por línea de comandos.
3. **`reposicion.json` junto al `.exe`**.
4. **`%APPDATA%\Reposicion\reposicion.json`** — lo que guarda el propio programa al cerrarse.
5. **`CONFIG.DBF` del ERP** — sólo rellena lo que quedó vacío. Ver abajo.
6. Si después de todo eso falta algo, aparece el **asistente de primera ejecución**.

### El .exe se configura solo

`principal.prg` no inventa las rutas: las lee de `CONFIG.DBF` al arrancar.

```foxpro
sis_path_  = ADDBS(UPPER(ALLTRIM(cfg_path__)))
zip_path_  = ALLTRIM(cfg_respal)
sis_path2  = ALLTRIM(cfg_p_sis2)
sis_sucurs = cfg_sucurs
```

Las cuatro variables que este programa necesita están guardadas en una tabla,
en un lugar conocido. Así que el `.exe` hace lo mismo: busca `CONFIG.DBF` en su
propia carpeta y en la de datos, y se configura solo. **Copiado al lado de
`SISTEMA.EXE`, arranca sin que nadie configure nada.**

Esa capa nunca pisa un valor que haya llegado por línea de comandos, por el
archivo de traspaso o por la configuración guardada a mano: sólo rellena
vacíos. El botón *Detectar del sistema*, en la pantalla de configuración,
sí fuerza la relectura — ahí lo pidió el usuario. `--sin-autodeteccion` la
apaga del todo.

```
reposicion.exe --data "X:\SISTEMA\DATOS\" --data2 "Y:\SUC2\DATOS\" --sucursal "01"
```

| Parámetro | Era | Para qué |
|---|---|---|
| `--data` | `sis_path_` | Carpeta con ARTICULO.DBF, PROVEEDO.DBF y ROTACION.DBF |
| `--data2` | `sis_path2` | Carpeta de la otra sucursal. Opcional |
| `--sucursal` | `sis_sucurs` | Código de sucursal: filtra `AR_SUCU` |
| `--zip` | `zip_path_` | Segunda base. Solo para el recálculo de rotación |
| `--codepage` | — | `auto` (default), `cp1252`, `cp850`... |
| `--erp` | — | Carpeta donde está el `CONFIG.DBF` del sistema |
| `--sin-autodeteccion` | — | No leer `CONFIG.DBF` para completar lo que falte |
| `--diagnostico` | — | Revisa el entorno (tablas, campos, claves, permisos) y sale |
| `--ajustes` | — | Abre directo la pantalla de configuración |

En `integracion_vfp/` están los dos lanzadores para llamar desde el ERP:
`abrir_reposicion.prg` (línea de comandos) y `abrir_reposicion_json.prg`
(archivo de traspaso).

---

## Qué escribe y qué no

**Nunca toca las tablas del sistema.** ARTICULO, PROVEEDO, DOCUM y DOCCUER
se abren en modo lectura y se traen a memoria. No usa el CDX, no toma
bloqueos y no necesita el driver OLE DB de Visual FoxPro — por eso se puede
compilar en 64 bits sin problemas. El ERP puede tener las mismas tablas
abiertas al mismo tiempo.

**Lo único que escribe es `ROTACION.DBF`**, que es la tabla propia del
módulo, y solo cuando se aprieta *Recalcular rotación*. La escritura es
atómica: se genera un archivo temporal en la misma carpeta y recién al
final se reemplaza. O queda la tabla nueva entera, o queda la vieja
intacta; nunca una a medias. Si otro puesto la tiene abierta, el reemplazo
falla con un mensaje claro y la tabla anterior sigue sirviendo.

El `ROTACION.CDX` viejo se borra en cada regeneración. El formulario nunca
hace `SEEK` sobre esa tabla (la lee con un `SELECT ... GROUP BY`), así que
el índice no hace falta — pero un CDX de la corrida anterior junto a una
tabla nueva apunta a registros que ya no existen, y eso sí rompe.

Las cantidades que se editan a mano viven solo en memoria y salen por
Excel, PDF o el informe, igual que en el formulario original.

---

## Estructura

```
main.py                    punto de entrada y cascada de parámetros
app/
  vfp.py                   semántica de VFP: ROUND, EXACT OFF, NVL, PADR
  dbf.py                   lector de DBF de VFP, solo lectura
  config.py                parámetros y su resolución en cascada
  datos.py                 lee las tablas y arma el catálogo en memoria
  calculo.py               port de CandidatosRotacion / CandidatosManual
  rotacion.py              port de calcular_rotacion.prg
  config_erp.py            autodetección leyendo CONFIG.DBF
  diagnostico.py           revisión del entorno para la puesta en marcha
  dbf_escritor.py          escribe ROTACION.DBF, con reemplazo atómico
  ui/
    estilo.py              paleta y hoja de estilos
    widgets.py             tarjetas KPI, interruptor, control segmentado
    modelos.py             las dos grillas
    ventana.py             ventana principal
    ayuda.py               ayuda en pantalla
    ajustes.py             configuración / primera ejecución
    dialogo_rotacion.py    recálculo de rotación, con progreso e informe
    dialogo_diagnostico.py informe del diagnóstico del entorno
  salidas/
    excel.py  pdf.py  informe.py
tests/                     pruebas
tools/                     datos de prueba, capturas, arneses de línea de comandos
integracion_vfp/           lanzadores y opción de menú para el ERP
PUESTA_EN_MARCHA.md        pasos para instalarlo en el servidor
reposicion.spec            empaquetado con PyInstaller
```

---

## Desarrollo

```bash
pip install PySide6 openpyxl reportlab

# tablas ficticias para probar sin el ERP
python3 tools/generar_datos_prueba.py /tmp/prueba 8000

# correr
python3 main.py --data /tmp/prueba/DATOS --data2 /tmp/prueba/DATOS2 --sucursal 1

# el cálculo sin interfaz, con el embudo de descartes
python3 tools/probar_calculo.py --data /tmp/prueba/DATOS --sucursal 1 --consolidar

# el recálculo de rotación sin interfaz (= DO calcular_rotacion WITH 24, .T.)
python3 tools/probar_rotacion.py --data /tmp/prueba/DATOS --data2 /tmp/prueba/DATOS2 \
    --zip /tmp/prueba/ZIP --sucursal 1

# pruebas
python3 tools/correr_pruebas.py

# ver la estructura de una tabla real
python3 -c "from app.dbf import describir; print(describir(r'X:\DATOS\ARTICULO.DBF'))"
```

## Compilar

```bat
pip install pyinstaller pillow
python tools\generar_icono.py     :: crea reposicion.ico y version.txt
pyinstaller reposicion.spec       :: deja dist\reposicion.exe
```

El icono y el `version.txt` son **opcionales**: si no están, el `.spec` avisa
y compila igual, con el icono genérico de Windows. Pillow sólo hace falta
para generarlos.

Un par de cosas que ahorran tiempo:

- **No compiles desde una terminal de administrador.** PyInstaller lo avisa
  con un DEPRECATION y a partir de la 7.0 directamente no va a dejar.
- Si algo falla, `build\reposicion\warn-reposicion.txt` lista los módulos que
  no encontró.
- Para probar el `.exe` sin ir hasta una terminal: `dist\reposicion.exe
  --ajustes` abre directo la pantalla de configuración.

---

## Diferencias de comportamiento respecto del formulario original

Todas deliberadas. Las formulas y los umbrales no se tocaron.

1. **Mover un parámetro ya no relee las tablas.** El formulario corría
   `CargarQuiebres()` completo con cada cambio de spinner, y eso volvía a
   recorrer ARTICULO.DBF entero. Acá el catálogo queda en memoria y solo se
   rehacen las cuentas: la respuesta es inmediata. F5 sigue forzando la
   relectura completa, y cambiar el filtro de sucursal o "analizar todas las
   series" también, porque cambian qué se lee.

2. **Excel sin Excel.** La exportación era automatización COM y exigía tener
   Office instalado. Ahora el `.xlsx` se escribe directamente.

3. **PDF sin XFRX.** El layout es código y viaja adentro del ejecutable. Ya
   no hay que mantener `rep_compras.frx` aparte ni depender de que XFRX.PRG
   esté cargado en el entorno.

4. **El reparto entre depósitos es opcional.** Las columnas "Pedir acá" y
   "Pedir otra" están detrás de un checkbox, para que la descripción del
   artículo tenga lugar.

5. **La configuración se recuerda.** Los parámetros con los que se cerró el
   programa vuelven la próxima vez.

6. **Los remitos internos ya no cuentan como venta, por defecto.** Ver la
   sección siguiente: es el único cambio que mueve números.

7. **`ROT_ARTIC` no se trunca.** El PRG lo fijaba a mano en `C(7)`; acá el
   ancho sale del dato real. Si la clave mide más, el informe lo avisa.

8. **El recálculo tarda segundos, no minutos.** 700.000 renglones de
   DOCCUER se procesan en menos de 6 segundos, con barra de progreso y sin
   congelar la ventana. Con los volúmenes reales (DOCUM 105.681, DOCCUER
   231.186) son un par de segundos.

9. **El Excel trae la ubicación de depósito.** `AR_UBICACI` sale como
   columna D. Antes de pedir un artículo que figura en negativo conviene ir
   a mirar el estante, y ahora la planilla dice cuál.

10. **Tiene en cuenta las temporadas.** Ver la sección siguiente. Se apaga
    con el interruptor *Considerar temporadas* y el cálculo vuelve a ser
    exactamente el del formulario original.

---

## Temporadas (estacionalidad)

El promedio (o la mediana) de ventas es parejo para todo el año. Con
*Considerar temporadas* activado, la venta mensual se multiplica por un
**índice estacional** antes de calcular los días de stock y la cantidad a
pedir:

```
índice = venta esperada en los próximos `cobertura` días según el perfil
         / venta mensual promedio del año
```

**El perfil** se arma al *Recalcular rotación*: `ROTACION.DBF` suma
`ROT_EST01`..`ROT_EST12` (venta promedio de cada mes calendario) y
`ROT_ESTHIS` (meses de historia). Van al final de la tabla, así que no se
mueve ninguna columna que ya existía.

- Los primeros 3 meses de la ventana solo sirven para saber si el artículo
  ya existía o es nuevo; **no entran al perfil**. El mes que decide tiene
  venta por definición, y metido en el perfil inflaba ese mes del año en los
  artículos de poca venta (con ventas parejas, septiembre a noviembre daban
  el doble).
- Artículo nuevo: el perfil arranca el mes siguiente a su primera venta.
- Hacen falta 12 meses de historia, o sea **recalcular con 15 meses o más**
  (el valor por defecto es 24).

**De dónde sale el índice**, en este orden (`app/calculo.py`, constantes
`ESTAC_*`):

1. Del propio artículo: 12+ meses de historia, 24+ unidades por año y 6+
   meses con venta.
2. De su rubro (`AR_RUBR`): suma de los artículos del rubro con historia
   completa; mínimo 5 artículos y 60 unidades por año.
3. Si no, índice 1: calcula igual que siempre.

El perfil se suaviza con el mes anterior y el siguiente (1-2-1), y el
índice se acota entre 0,3 y 3. Con una `ROTACION.DBF` generada por el PRG
de VFP o por una versión anterior, el programa calcula sin temporadas y la
leyenda avisa que hay que recalcular.

---

## La clave de proveedor

Vale la pena dejarla escrita, porque no se deduce mirando el formulario.

```
ARTICULO.AR_PROV    Character(7)
PROVEEDO.PR_SUCURS  Character(1)
PROVEEDO.PR_CODIGO  Numeric(6)      <-- NUMÉRICO
```

El puente entre los dos es la regla de `Form.NormalizarProv`:

```foxpro
IF LEN(lcCod) <> 7
    lcCod = "1" + PADL(lcCod, 6)
ENDIF
```

O sea que la clave es **la sucursal pegada adelante del código justificado a
la derecha en 6 lugares, con espacios**. El proveedor 232 de la sucursal 1 es
`"1   232"` — ni `"232"`, ni `"1000232"`. Es lo mismo que hace
`STR(PR_CODIGO, 6)` en el tag `COD_ALFA` del CDX, que es contra lo que el
formulario hacía `SEEK` sin nombrar nunca el campo.

Como `PR_CODIGO` es numérico, un `PADR()` ingenuo sobre el valor leído produce
`"232    "` y **ningún** proveedor engancha: la lista entera sale con
`[código] no está en PROVEEDO`. Está armado en `datos.clave_proveedor()`, con
pruebas que verifican que las dos puntas del cruce dan la misma cadena.

Si aun así apareciera algún nombre sin resolver, queda de red `DESC_PROV`, el
nombre del proveedor que ARTICULO trae denormalizado en la ficha del artículo.

---

## Los remitos internos: hay que tomar una decisión

`calcular_rotacion.prg` declara **`ProcesarFuente` dos veces** en el mismo
archivo, con el mismo nombre y criterios opuestos:

- **Línea 375** — la que Visual FoxPro usa, por ser la primera:
  `INLIST(DOC_TIPDOC, "FC","FE","RI","ND","DE","NC","CE")` → **los RI cuentan como venta**.
- **Línea 521** — nunca se ejecuta: saca `RI` de la lista y lo deja detrás de
  `llRIesVenta = .F.`, con un comentario que explica por qué la primera está
  mal: *"un remito interno mueve mercadería de un depósito al otro: baja el
  stock del que provee, pero NO es una venta. Contarlo como consumo infla la
  demanda de la sucursal que abastece a la otra"*.

Alguien detectó el problema, escribió la corrección, y la corrección quedó
muerta porque VFP resuelve el nombre duplicado con la primera definición.

El programa deja la elección en la pantalla de *Recalcular rotación*, con el
valor por defecto en la versión corregida (**los RI no son venta**). Eso hace
que los números **no coincidan** con los que genera el ERP hoy. Si hace falta
que coincidan mientras se hace la transición, alcanza con tildar la opción.

---

## Cosas que hay que verificar contra los datos reales

- **Codificación.** Si las descripciones aparecen con caracteres raros,
  cambiar el codepage en la pantalla de ajustes (`cp850` es el otro
  candidato).
- **Filtro de sucursal.** Se reprodujo el `SET EXACT OFF` del original, donde
  `AR_SUCU = lcSucu` significa *empieza con*. Si existen sucursales `1` y
  `10`, la `1` arrastra a la `10`. Se puede endurecer poniendo
  `exact_off: false` en el JSON de configuración.
- **La clave de artículo: resuelta.** `AR_SUCU C(1)` + `AR_CODI C(6)` = 7, que
  es exactamente lo que miden `DCC_ARTICU C(7)` y `ROT_ARTIC C(7)`. El cruce
  va por la clave completa y no hay nada que truncar. El programa igual
  tolera la otra forma (código solo) y reporta cuál enganchó, en el informe
  del recálculo y en el diagnóstico de la corrida. **Mirá ese porcentaje la
  primera vez**: si sale bajo, algo cambió.
