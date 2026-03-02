#!/bin/bash
source venv/bin/activate
# O Flet precisa de alguns argumentos específicos para o PyInstaller
flet pack main.py --name "AnimeManager" --icon icon.png
