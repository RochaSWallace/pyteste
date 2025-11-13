import os
import sys
import json
import webbrowser
from pathlib import Path
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QLocale
from GUI_qt.git import get_last_version
from GUI_qt.load_providers import base_path
from GUI_qt.config import get_config, update_lang
from PyQt6.QtWidgets import QMessageBox
import time

def base():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return base_path()

current_dir = os.path.join(base(), 'GUI_qt')
assets = os.path.join(current_dir, 'assets')

class NewVersion():
    def __init__(self):
        self.msg_box = QMessageBox()
        self.show_message_box()

    def show_message_box(self):
        translations = {}
        with open(os.path.join(assets, 'translations.json'), 'r', encoding='utf-8') as file:
            translations = json.load(file)

        config = get_config()
        if not config:
            language = QLocale.system().name()
            update_lang(language)
        else:
            language = config.lang
        if language not in translations:
            language = 'en'
        
        translation = translations[language]

        self.msg_box.setWindowIcon(QIcon(os.path.join(assets, 'icon.ico')))
        self.msg_box.setWindowTitle(translation['new_version'])
        self.msg_box.setText(translation['new_version_description'])
        self.msg_box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

        self.msg_box.button(QMessageBox.StandardButton.Ok).clicked.connect(self.open_website)
        self.msg_box.button(QMessageBox.StandardButton.Cancel).clicked.connect(self.block_application)
        
        self.msg_box.exec()

    def open_website(self):
        version = get_last_version()
        webbrowser.open(f'https://github.com/RochaSWallace/pyteste/releases/tag/v{version}')
        # Loop infinito para bloquear aplicação
        print("Atualize para a versão mais recente!")
        while True:
            time.sleep(1)
    
    def block_application(self):
        # Loop infinito para bloquear aplicação se usuário cancelar
        print("Aplicação bloqueada. Atualize para continuar.")
        self.msg_box.close()
        while True:
            time.sleep(1)
    
    def close_application(self):
        # Mantido para compatibilidade, mas não será usado
        self.msg_box.close()

