from PyQt5.QtWidgets import QApplication

def set_light_mode(app: QApplication):
    """Set the application to light mode."""
    app.setStyleSheet("""
        QWidget {
            background-color: #ffffff;
            color: #000000;
        }
        QTextEdit {
            background-color: #f9f9f9;
            border: 1px solid #ccc;
            border-radius: 5px;
            padding: 5px;
        }
        QPushButton {
            background-color: #e0e0e0;
            border: 1px solid #a0a0a0;
            border-radius: 5px;
            padding: 5px;
        }
        QPushButton:hover {
            background-color: #d0d0d0;
        }
        QComboBox {
            background-color: #f0f0f0;
            border: 1px solid #ccc;
            border-radius: 5px;
            padding: 2px;
        }
        QTabWidget::pane {
            border: 1px solid #ccc;
            background-color: #ffffff;
        }
        QTabBar::tab {
            background-color: #e0e0e0;
            border: 1px solid #ccc;
            border-bottom: none;
            padding: 5px;
        }
        QTabBar::tab:selected {
            background-color: #ffffff;
            border-bottom: 2px solid #ffffff;
        }
        QToolBar {
            background-color: #f0f0f0;
            border: none;
        }
        QStatusBar {
            background-color: #f0f0f0;
            border-top: 1px solid #ccc;
        }
    """)

def set_dark_mode(app: QApplication):
    """Set the application to dark mode."""
    app.setStyleSheet("""
        QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QTextEdit {
            background-color: #3c3c3c;
            border: 1px solid #555;
            border-radius: 5px;
            padding: 5px;
            color: #ffffff;
        }
        QPushButton {
            background-color: #4a4a4a;
            border: 1px solid #666;
            border-radius: 5px;
            padding: 5px;
            color: #ffffff;
        }
        QPushButton:hover {
            background-color: #5a5a5a;
        }
        QComboBox {
            background-color: #3c3c3c;
            border: 1px solid #555;
            border-radius: 5px;
            padding: 2px;
            color: #ffffff;
        }
        QTabWidget::pane {
            border: 1px solid #555;
            background-color: #2b2b2b;
        }
        QTabBar::tab {
            background-color: #4a4a4a;
            border: 1px solid #555;
            border-bottom: none;
            padding: 5px;
            color: #ffffff;
        }
        QTabBar::tab:selected {
            background-color: #2b2b2b;
            border-bottom: 2px solid #2b2b2b;
        }
        QToolBar {
            background-color: #3c3c3c;
            border: none;
        }
        QStatusBar {
            background-color: #3c3c3c;
            border-top: 1px solid #555;
            color: #ffffff;
        }
        
        /* Styles pour les menus en mode sombre */
        QMenu {
            background-color: #2b2b2b;
            border: 1px solid #555;
            color: #ffffff;
        }

        QMenu::item {
            padding: 5px 10px;
            background-color: transparent; /* Rendre le fond transparent par défaut */
            color: #ffffff;
        }

        QMenu::item:selected { /* Style pour l'élément de menu sélectionné */
            background-color: #5a5a5a; /* Une couleur de fond légèrement plus claire */
            color: #ffffff; /* Assurer que le texte reste blanc */
        }

        QMenu::separator {
            height: 1px;
            background: #555;
            margin: 5px 10px;
        }
        
        /* Styles pour la barre de menu principale en mode sombre */
        QMenuBar {
            background-color: #3c3c3c; /* Couleur de fond similaire à la barre d'outils */
            color: #ffffff;
            spacing: 5px; /* Espacement entre les éléments du menu */
        }

        QMenuBar::item {
            padding: 5px 10px; /* Padding autour du texte de l'élément de menu */
            background: transparent; /* Fond transparent par défaut */
            color: #ffffff;
        }

        QMenuBar::item:selected { /* Au survol ou sélectionné */
            background: #5a5a5a; /* Couleur de fond au survol/sélection */
        }

        QMenuBar::item:pressed { /* Lorsqu'on clique */
            background: #6a6a6a; /* Couleur de fond lorsqu'il est pressé */
        }
    """)