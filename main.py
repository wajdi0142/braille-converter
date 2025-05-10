import os
import sys
import logging
from PyQt5.QtWidgets import QApplication
from frontend.ui import BrailleUI

# Ajouter le chemin du dossier parent au PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(filename='app_errors.log', level=logging.ERROR, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = BrailleUI(app)
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        logging.error(f"Erreur lors de l'exécution de l'application : {str(e)}")
        print(f"Une erreur s'est produite : {str(e)}. Consultez app_errors.log pour plus de détails.")
        sys.exit(1)