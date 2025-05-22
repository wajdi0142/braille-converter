from backend.database import Database
from backend.models import Utilisateur, Texte, Fichier, Impression

def test_database():
    try:
        # Initialiser la base de données
        db = Database()
        print("1. Base de données initialisée avec succès")
        
        # Vérifier les tables
        tables = [table[0] for table in db.cursor.execute('SELECT name FROM sqlite_master WHERE type="table"').fetchall()]
        print("2. Tables créées:", tables)
        
        # Tester l'ajout d'un utilisateur
        user_id = db.ajouter_utilisateur("Test User", "test@example.com", "password123")
        print("3. Utilisateur ajouté avec ID:", user_id)
        
        # Tester la récupération de l'utilisateur
        user = db.get_utilisateur_by_email("test@example.com")
        print("4. Utilisateur récupéré:", user.nom if user else "Non trouvé")
        
        # Tester l'ajout d'un texte
        texte = Texte("Test content", "Test title")
        db.ajouter_texte(user_id, texte)
        print("5. Texte ajouté avec succès")
        
        # Tester l'ajout d'un fichier
        fichier = Fichier("test.txt", "/path/to/test.txt")
        db.sauvegarder_fichier(user_id, fichier)
        print("6. Fichier ajouté avec succès")
        
        # Tester l'ajout d'une impression
        impression = Impression("Test document", "Test printer")
        db.ajouter_impression(user_id, impression)
        print("7. Impression ajoutée avec succès")
        
        # Tester les statistiques
        stats = db.get_usage_stats(user_id)
        print("8. Statistiques récupérées:", stats)
        
        print("\nTous les tests ont été exécutés avec succès!")
        
    except Exception as e:
        print(f"Erreur lors du test: {str(e)}")
    finally:
        if 'db' in locals():
            db.fermer_connexion()

if __name__ == "__main__":
    test_database() 