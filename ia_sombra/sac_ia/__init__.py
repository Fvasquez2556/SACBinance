"""
IA en sombra para SACBinance: Kronos + GPT-6 Luna/Sol, a ciegas, sin tocar SAC.

Un proceso aparte que LEE la base de SACBinance en solo lectura y ESCRIBE solo
en la suya. Por cada aviso que llega a Telegram congela el contexto, pide a
Kronos trayectorias futuras y a Luna y Sol una decision, y doce horas despues
etiqueta lo que paso con el mismo evaluador de recorridos que usa SAC.

Nada de lo que decide llega al operador hasta el veredicto: la medicion es a
ciegas. El estudio esta congelado en `registro.py`.
"""
