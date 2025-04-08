import sys
import signal
from PyQt5.QtWidgets import QApplication
from frontend.ui import BrailleUI
from frontend.styles import set_light_mode

def signal_handler(sig, frame):
    print("\nInterruption détectée. Fermeture...")
    QApplication.quit()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    app = QApplication(sys.argv)
    set_light_mode(app)
    window = BrailleUI(app)
    window.show()
    sys.exit(app.exec_())