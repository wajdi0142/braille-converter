import time
import sys
from PyQt5.QtWidgets import QApplication
from frontend.braille_tab import BrailleTab
from frontend.ui import BrailleUI

def test_performance():
    app = QApplication(sys.argv)
    main_window = BrailleUI(app)
    tab = BrailleTab(main_window)
    
    # Test de chargement
    print("Test de chargement du fichier...")
    start_time = time.time()
    tab.load_large_file("test_large_file.txt")
    load_time = time.time() - start_time
    print(f"Temps de chargement: {load_time:.2f} secondes")
    
    # Test de conversion
    print("\nTest de conversion...")
    start_time = time.time()
    tab.update_conversion()
    conversion_time = time.time() - start_time
    print(f"Temps de conversion: {conversion_time:.2f} secondes")
    
    # Test de modification
    print("\nTest de modification...")
    start_time = time.time()
    tab.text_input.append("Test de modification")
    modification_time = time.time() - start_time
    print(f"Temps de modification: {modification_time:.2f} secondes")
    
    # Afficher les résultats
    print("\nRésultats des tests:")
    print(f"Temps total: {load_time + conversion_time + modification_time:.2f} secondes")
    print(f"Taille du cache: {len(tab._conversion_cache)} entrées")
    
    return app.exec_()

def test_large_file_performance():
    app = QApplication(sys.argv)
    window = BrailleUI()
    window.show()
    
    # Mesurer le temps de chargement
    start_time = time.time()
    
    # Simuler l'import d'un gros fichier
    with open('test_large_file.txt', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Mesurer le temps de conversion
    conversion_start = time.time()
    window.import_text(content)
    conversion_end = time.time()
    
    # Afficher les résultats
    print(f"Temps de chargement du fichier: {time.time() - start_time:.2f} secondes")
    print(f"Temps de conversion: {conversion_end - conversion_start:.2f} secondes")
    
    return app.exec_()

if __name__ == "__main__":
    test_performance()
    test_large_file_performance() 