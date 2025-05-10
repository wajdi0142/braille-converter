import os
from typing import Dict, List

class Texte:
    """Represents a text document."""
    
    def __init__(self, contenu: str, titre: str = ""):
        self.titre = titre
        self.contenu = contenu

    def __str__(self):
        return f"Texte(titre={self.titre}, contenu={self.contenu})"

class Fichier:
    def __init__(self, chemin: str, file_type: str):
        self.nom = os.path.basename(chemin)  # Extract file name from path
        self.chemin = chemin
        self.file_type = file_type

    def __str__(self):
        return f"Fichier(nom={self.nom}, chemin={self.chemin})"

class Impression:
    """Represents a print job."""
    
    def __init__(self, document: str, imprimante: str):
        self.document = document
        self.imprimante = imprimante

    def __str__(self):
        return f"Impression(document={self.document}, imprimante={self.imprimante})"

class Utilisateur:
    """Represents a user with associated texts, files, and impressions."""
    
    def __init__(self, nom: str, email: str):
        self.id = None
        self.nom = nom
        self.email = email
        self.preferences: Dict[str, str] = {}
        self.textes: List[Texte] = []
        self.fichiers: List[Fichier] = []
        self.impressions: List[Impression] = []

    def ajouterTexte(self, texte: Texte) -> None:
        """Add a text to the user."""
        self.textes.append(texte)

    def supprimerTexte(self, texte: Texte) -> None:
        """Remove a text from the user."""
        if texte in self.textes:
            self.textes.remove(texte)

    def sauvegarderFichier(self, fichier: Fichier) -> None:
        """Save a file for the user."""
        self.fichiers.append(fichier)

    def exporterFichier(self, format: str) -> None:
        """Export all user files in the specified format."""
        for fichier in self.fichiers:
            print(f"Exporting {fichier.nom} to {format}")

    def lancerImpression(self, imp: Impression) -> None:
        """Launch a print job for the user."""
        self.impressions.append(imp)
        print(f"Starting print: {imp.document} on {imp.imprimante}")

    def __str__(self):
        return f"Utilisateur(nom={self.nom}, email={self.email})"
class Texte:
    def __init__(self, contenu, titre):
        self.contenu = contenu
        self.titre = titre

class Fichier:
    def __init__(self, nom, chemin):
        self.nom = nom
        self.chemin = chemin