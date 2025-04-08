# Manuel Utilisateur - Convertisseur Texte ↔ Braille

## Introduction
Ce logiciel permet de convertir du texte en Braille et vice-versa, avec une interface synchronisée et des options d’édition, d’enregistrement et d’impression.

## Installation
1. Installez Python 3.8+.
2. Installez les dépendances : `pip install PyQt5 pytesseract pdfplumber python-docx reportlab pillow opencv-python`.
3. Installez LibLouis et Tesseract-OCR (voir `config.py` pour les chemins).
4. Exécutez `braille_ui.py`.

## Utilisation
### Connexion
- Lancez le logiciel et entrez vos identifiants ou inscrivez-vous via l’interface d’authentification.

### Interface principale
- **Zone Texte** : Saisissez ou modifiez le texte clair.
- **Zone Braille** : Visualisez ou modifiez le Braille (via "Inverser la conversion").
- **Barre d’outils** : Accédez aux fonctions principales (Nouveau, Ouvrir, Enregistrer, etc.).

### Fonctionnalités
- **Conversion** : Tapez du texte, il est converti en Braille en temps réel. Utilisez "Inverser" (Ctrl+R) pour passer en mode Braille → Texte.
- **Mise en forme** : Appliquez gras (Ctrl+B), italique (Ctrl+I), souligné (Ctrl+U), etc.
- **Enregistrement** : Sauvegardez en .txt, .bfr, .pdf ou .docx.
- **Impression** : Imprimez directement sur une imprimante Braille (Ctrl+P).
- **Zoom** : Ajustez avec Ctrl++ ou Ctrl+-.

### Raccourcis clavier
- Ctrl+N : Nouveau document
- Ctrl+O : Ouvrir
- Ctrl+S : Enregistrer
- Ctrl+P : Imprimer
- Ctrl+T : Traduire
- F11 : Plein écran

## Paramètres
- **Table Braille** : Choisissez une langue dans le menu déroulant.
- **Mise en page** : Ajustez les lignes et colonnes via "Paramètres".

## Support
Contactez-nous à support@example.com pour toute assistance.