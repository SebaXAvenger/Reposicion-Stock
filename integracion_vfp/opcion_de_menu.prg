*==========================================================================
* OPCION DE MENU - Centro de control de quiebres de stock
*
* Este codigo va PEGADO EN LA COLUMNA "Procedimiento" de la opcion del menu
* del ERP (el .MNX). Es autocontenido a proposito: no llama a ningun PRG
* externo, asi que no hay que acordarse de copiar un archivo aparte ni de
* agregarlo al proyecto.
*
* COMO SE AGREGA (Visual FoxPro):
*   1.  MODIFY MENU <nombre del menu>
*   2.  Ubicarse en el popup donde va la opcion (Consultas, Informes,
*       Compras... donde corresponda).
*   3.  Nueva fila:
*         Prompt   : Reposicion de stock
*         Result   : Procedimiento          <-- NO "Comando"
*   4.  Boton "Crear" y pegar todo lo que sigue.
*   5.  Menu > Generar   (regenera el .MPR)
*   6.  Recompilar SISTEMA.EXE.
*
*==========================================================================
* OJO CON LA BARRA FINAL  --  leer antes de tocar el armado de parametros
*==========================================================================
* sis_path_ viene de ADDBS(), asi que SIEMPRE termina en barra invertida:
* "S:\". Y en Windows, una barra invertida justo antes de la comilla de
* cierre ESCAPA esa comilla:
*
*     --data "S:\" --sucursal "1" --data2 "X:\"
*
* no se parte en cinco argumentos. El \" del primero se interpreta como una
* comilla literal, la cadena nunca se cierra, y el programa recibe UN solo
* argumento con todo el resto adentro:
*
*     --data  ->  S:" --sucursal 1 --data2 X:"
*
* Resultado: la ruta llega rota y --sucursal y --data2 nunca se leen, asi
* que el programa cree que no le pasaron nada y abre la configuracion
* inicial. Sintoma clasico y muy dificil de adivinar.
*
* La solucion es DUPLICAR las barras finales antes de la comilla de cierre:
*
*     --data "S:\\"   ->  Windows entrega  S:\
*
* De eso se encarga la funcion Ent() del final. No armes los parametros a
* mano concatenando comillas: usala siempre.
*==========================================================================
LOCAL lcExe, lcParams, lnRet, lcMsg

*--- 1. Donde esta el ejecutable -----------------------------------------
* Vive en la carpeta de datos del servidor: una sola copia para todas las
* terminales, y se actualiza en un solo lugar.
lcExe = ADDBS(sis_path_) + "reposicion.exe"

IF NOT FILE(lcExe)
    MESSAGEBOX("No se encontro el programa de reposicion en:" + CHR(13) + ;
               lcExe + CHR(13) + CHR(13) + ;
               "Avisale al administrador del sistema.", ;
               16, "Falta el ejecutable")
    RETURN
ENDIF

*--- 2. Parametros --------------------------------------------------------
* Son las mismas variables publicas que el formulario usaba cuando vivia
* adentro del ERP.
lcParams = "--data "     + Ent(sis_path_) + " " + ;
           "--sucursal " + Ent(sis_sucurs)

* Opcionales: si no estan, el programa arranca igual, solo que sin el
* analisis consolidado de las dos sucursales.
IF TYPE("sis_path2") = "C" AND NOT EMPTY(sis_path2)
    lcParams = lcParams + " --data2 " + Ent(sis_path2)
ENDIF

IF TYPE("zip_path_") = "C" AND NOT EMPTY(zip_path_)
    lcParams = lcParams + " --zip " + Ent(zip_path_)
ENDIF

*--- 3. Lanzar ------------------------------------------------------------
* ShellExecute en vez de RUN: no bloquea el ERP mientras el programa esta
* abierto, y no deja una ventana de consola dando vueltas.
DECLARE INTEGER ShellExecute IN shell32.dll ;
    INTEGER hwnd, STRING lpOperation, STRING lpFile, ;
    STRING lpParameters, STRING lpDirectory, INTEGER nShowCmd

lnRet = ShellExecute(0, "open", lcExe, lcParams, ADDBS(sis_path_), 1)

* Un valor menor o igual a 32 es un codigo de error de ShellExecute
IF lnRet <= 32
    DO CASE
        CASE lnRet = 2
            lcMsg = "No se encontro el archivo."
        CASE lnRet = 3
            lcMsg = "No se encontro la carpeta."
        CASE lnRet = 5
            lcMsg = "Acceso denegado. Puede ser el antivirus o los permisos " + ;
                    "sobre la carpeta del servidor."
        CASE lnRet = 8
            lcMsg = "Memoria insuficiente."
        CASE lnRet = 31
            lcMsg = "Windows no sabe con que abrir el archivo."
        OTHERWISE
            lcMsg = "Codigo de error " + TRANSFORM(lnRet) + "."
    ENDCASE
    MESSAGEBOX("No se pudo abrir el programa de reposicion." + CHR(13) + ;
               CHR(13) + lcMsg, 16, "Error al iniciar")
ENDIF

RETURN


*==========================================================================
* Ent()  -  Entrecomilla un valor para pasarlo por linea de comandos.
*
* Duplica las barras invertidas del FINAL, que son las unicas que causan
* problema: son las que quedan pegadas a la comilla de cierre.
*
*     Ent("S:\")              ->  "S:\\"          Windows lee  S:\
*     Ent("X:\SIS\DATOS\")    ->  "X:\SIS\DATOS\\"          X:\SIS\DATOS\
*     Ent("1")                ->  "1"                       1
*
* Las barras del medio NO se tocan: fuera de ese caso, Windows las trata
* como caracteres comunes.
*==========================================================================
FUNCTION Ent
    LPARAMETERS tcValor
    LOCAL lcValor, lnBarras, lnLargo

    lcValor = ALLTRIM(TRANSFORM(tcValor))
    lnLargo = LEN(lcValor)
    lnBarras = 0

    DO WHILE lnBarras < lnLargo ;
             AND SUBSTR(lcValor, lnLargo - lnBarras, 1) == "\"
        lnBarras = lnBarras + 1
    ENDDO

    RETURN '"' + lcValor + REPLICATE("\", lnBarras) + '"'
ENDFUNC
