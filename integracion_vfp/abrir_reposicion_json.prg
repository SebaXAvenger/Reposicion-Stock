*==========================================================================
* ABRIR_REPOSICION_JSON.PRG
*
* Variante del lanzador para cuando las rutas dan problemas por linea de
* comandos: rutas UNC muy largas, comillas, caracteres raros o limites de
* longitud del comando.
*
* En vez de armar una linea de comandos, VFP escribe un archivo JSON
* temporal y le pasa al programa una sola cosa: donde esta ese archivo.
* El programa lo lee y lo borra solo (--borrar-config).
*==========================================================================
LOCAL lcExe, lcJson, lnH, lcRuta2, lcRutaZip

lcExe = ADDBS(sis_path_) + "reposicion.exe"

IF NOT FILE(lcExe)
    MESSAGEBOX("No se encontro:" + CHR(13) + lcExe, 16, "Falta el ejecutable")
    RETURN
ENDIF

*--- Archivo temporal en la carpeta TEMP del usuario ----------------------
lcJson = ADDBS(SYS(2023)) + "repos_" + SYS(2015) + ".json"

lcRuta2   = IIF(TYPE("sis_path2") = "C", ALLTRIM(sis_path2), "")
lcRutaZip = IIF(TYPE("zip_path_") = "C", ALLTRIM(zip_path_), "")

lnH = FCREATE(lcJson)
IF lnH < 0
    MESSAGEBOX("No se pudo crear el archivo temporal:" + CHR(13) + lcJson, ;
               16, "Error")
    RETURN
ENDIF

* Las barras invertidas de las rutas de Windows se escapan: en JSON la
* barra invertida sola es un caracter de escape y rompe el archivo.
= FPUTS(lnH, '{')
= FPUTS(lnH, '  "sis_path_":  "' + STRTRAN(ALLTRIM(sis_path_), '\', '\\') + '",')
= FPUTS(lnH, '  "sis_path2":  "' + STRTRAN(lcRuta2, '\', '\\') + '",')
= FPUTS(lnH, '  "zip_path_":  "' + STRTRAN(lcRutaZip, '\', '\\') + '",')
= FPUTS(lnH, '  "sis_sucurs": "' + ALLTRIM(sis_sucurs) + '"')
= FPUTS(lnH, '}')
= FCLOSE(lnH)

DECLARE INTEGER ShellExecute IN shell32.dll ;
    INTEGER hwnd, STRING lpOperation, STRING lpFile, ;
    STRING lpParameters, STRING lpDirectory, INTEGER nShowCmd

= ShellExecute(0, "open", lcExe, ;
    '--config "' + lcJson + '" --borrar-config', ADDBS(sis_path_), 1)

RETURN
