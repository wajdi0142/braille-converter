# Projet Convertisseur Texte ↔ Braille

## Description
Ce projet est un logiciel permettant de convertir du texte clair en Braille et vice-versa, avec une interface utilisateur synchronisée développée en Python avec PyQt5 et LibLouis.

## Prérequis
- Python 3.8+
- Dépendances : `PyQt5`, `pytesseract`, `pdfplumber`, `python-docx`, `reportlab`, `pillow`, `opencv-python`
- LibLouis (installé à `C:\msys64\usr\bin\lou_translate.exe`)
- Tesseract-OCR (installé à `C:\Program Files\Tesseract-OCR\tesseract.exe`)

## Installation
1. Clonez le dépôt : `git clone <url>`
2. Installez les dépendances : `pip install -r requirements.txt`
3. Configurez les chemins dans `backend/config.py` si nécessaire.
4. Lancez le programme : `python frontend/braille_ui.py`

## Générer un exécutable
1. Installez PyInstaller : `pip install pyinstaller`
2. Exécutez : `pyinstaller --onefile --windowed frontend/braille_ui.py`
3. L’exécutable sera dans le dossier `dist`.

## Tests
Exécutez les tests unitaires : `python tests.py`

## Structure
- `backend/` : Logique métier (conversion, gestion de fichiers, base de données).
- `frontend/` : Interface utilisateur (PyQt5).
- `tests.py` : Tests unitaires.
- `MANUEL_UTILISATEUR.md` : Documentation utilisateur.

## Contributeurs
- [Votre nom ou pseudonyme]