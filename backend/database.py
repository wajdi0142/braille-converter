import sqlite3
import json
import os
import logging
from pathlib import Path
from typing import List
from .models import Utilisateur, Texte, Fichier, Impression
from .config import DB_PATH, DB_FOLDER

# Configure logging
logging.basicConfig(filename="database.log", level=logging.ERROR)

class Database:
    """Manages SQLite database for user data, texts, files, and impressions."""
    
    def __init__(self, db_name=DB_PATH):
        """Initialize database connection and create tables."""
        try:
            Path(DB_FOLDER).mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(db_name)
            self.cursor = self.conn.cursor()
            self.creer_tables()
        except sqlite3.Error as e:
            logging.error(f"Database initialization error: {e}")
            raise RuntimeError(f"Failed to initialize database: {e}")

    def creer_tables(self):
        """Create necessary database tables if they don't exist."""
        try:
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS utilisateurs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT,
                    preferences TEXT,
                    total_usage_time INTEGER DEFAULT 0,
                    last_login TIMESTAMP
                )''')
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS device_auth (
                    device_user TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES utilisateurs(id)
                )''')
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS textes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    utilisateur_id INTEGER,
                    titre TEXT,
                    char_count INTEGER,
                    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id)
                )''')
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS fichiers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    utilisateur_id INTEGER,
                    nom TEXT,
                    chemin TEXT,
                    file_type TEXT,
                    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id)
                )''')
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS impressions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    utilisateur_id INTEGER,
                    char_count INTEGER,
                    imprimante TEXT,
                    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id)
                )''')
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Table creation error: {e}")
            raise RuntimeError(f"Failed to create tables: {e}")

    def hash_password(self, password: str) -> str:
        """Hash a password using SHA-256."""
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()

    def ajouter_utilisateur(self, nom: str, email: str, password: str = None) -> int:
        """Add a new user to the database."""
        try:
            password_hash = self.hash_password(password) if password else None
            self.cursor.execute(
                "INSERT INTO utilisateurs (nom, email, password_hash, preferences) VALUES (?, ?, ?, ?)",
                (nom, email, password_hash, json.dumps({}))
            )
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.IntegrityError as e:
            logging.error(f"User addition error: {e}")
            raise ValueError(f"A user with email {email} already exists.")

    def verify_user(self, email: str, password: str) -> tuple:
        """Verify user credentials."""
        try:
            password_hash = self.hash_password(password)
            self.cursor.execute(
                "SELECT id, nom, email, preferences FROM utilisateurs WHERE email = ? AND password_hash = ?",
                (email, password_hash)
            )
            return self.cursor.fetchone()
        except sqlite3.Error as e:
            logging.error(f"User verification error: {e}")
            return None

    def get_utilisateur_by_email(self, email: str) -> Utilisateur:
        """Retrieve a user by email, including their texts, files, and impressions."""
        try:
            self.cursor.execute(
                "SELECT id, nom, email, preferences FROM utilisateurs WHERE email = ?", 
                (email,)
            )
            row = self.cursor.fetchone()
            if not row:
                return None
            user_id, nom, email, preferences_json = row
            utilisateur = Utilisateur(nom, email)
            utilisateur.id = user_id
            utilisateur.preferences = json.loads(preferences_json)

            self.cursor.execute("SELECT titre, char_count FROM textes WHERE utilisateur_id = ?", (user_id,))
            for titre, char_count in self.cursor.fetchall():
                utilisateur.ajouterTexte(Texte("", titre))

            self.cursor.execute("SELECT nom, chemin FROM fichiers WHERE utilisateur_id = ?", (user_id,))
            for nom, chemin in self.cursor.fetchall():
                utilisateur.sauvegarderFichier(Fichier(nom, chemin))

            self.cursor.execute("SELECT char_count, imprimante FROM impressions WHERE utilisateur_id = ?", (user_id,))
            for char_count, imprimante in self.cursor.fetchall():
                utilisateur.lancerImpression(Impression("", imprimante))

            return utilisateur
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logging.error(f"User retrieval error: {e}")
            return None

    def get_all_utilisateurs(self) -> List[Utilisateur]:
        """Retrieve all users."""
        try:
            self.cursor.execute("SELECT email FROM utilisateurs")
            return [self.get_utilisateur_by_email(row[0]) for row in self.cursor.fetchall()]
        except sqlite3.Error as e:
            logging.error(f"All users retrieval error: {e}")
            return []

    def update_password(self, email: str, new_password: str) -> None:
        """Update a user's password."""
        try:
            password_hash = self.hash_password(new_password)
            self.cursor.execute(
                "UPDATE utilisateurs SET password_hash = ? WHERE email = ?", 
                (password_hash, email)
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Password update error: {e}")

    def save_device_auth(self, device_user: str, user_id: int) -> None:
        """Save device authentication data."""
        try:
            self.cursor.execute("DELETE FROM device_auth WHERE device_user = ?", (device_user,))
            if user_id:
                self.cursor.execute(
                    "INSERT INTO device_auth (device_user, user_id) VALUES (?, ?)",
                    (device_user, user_id)
                )
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Device auth save error: {e}")

    def get_device_user(self, device_user: str) -> tuple:
        """Retrieve user associated with a device."""
        try:
            self.cursor.execute("SELECT user_id FROM device_auth WHERE device_user = ?", (device_user,))
            result = self.cursor.fetchone()
            if result:
                user_id = result[0]
                self.cursor.execute(
                    "SELECT id, nom, email, preferences FROM utilisateurs WHERE id = ?", 
                    (user_id,)
                )
                return self.cursor.fetchone()
            return None
        except sqlite3.Error as e:
            logging.error(f"Device user retrieval error: {e}")
            return None

    def ajouter_texte(self, utilisateur_id: int, texte: Texte) -> None:
        """Add a text record for a user."""
        try:
            self.cursor.execute(
                "INSERT INTO textes (utilisateur_id, titre, char_count) VALUES (?, ?, ?)",
                (utilisateur_id, texte.titre, len(texte.contenu))
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Text addition error: {e}")

    def supprimer_texte(self, utilisateur_id: int, texte: Texte) -> None:
        """Delete a text record for a user."""
        try:
            self.cursor.execute(
                "DELETE FROM textes WHERE utilisateur_id = ? AND titre = ? AND char_count = ?",
                (utilisateur_id, texte.titre, len(texte.contenu))
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Text deletion error: {e}")

    def sauvegarder_fichier(self, utilisateur_id: int, fichier: Fichier) -> None:
        """Save a file record for a user."""
        try:
            file_type = os.path.splitext(fichier.chemin)[1][1:].lower()
            self.cursor.execute(
                "INSERT INTO fichiers (utilisateur_id, nom, chemin, file_type) VALUES (?, ?, ?, ?)",
                (utilisateur_id, fichier.nom, fichier.chemin, file_type)
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"File save error: {e}")

    def ajouter_impression(self, utilisateur_id: int, imp: Impression) -> None:
        """Add an impression record for a user."""
        try:
            self.cursor.execute(
                "INSERT INTO impressions (utilisateur_id, char_count, imprimante) VALUES (?, ?, ?)",
                (utilisateur_id, len(imp.document), imp.imprimante)
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Impression addition error: {e}")

    def get_usage_stats(self, user_id: int) -> dict:
        """Retrieve usage statistics for a user."""
        try:
            self.cursor.execute("SELECT total_usage_time FROM utilisateurs WHERE id = ?", (user_id,))
            total_time = self.cursor.fetchone()[0] or 0
            self.cursor.execute(
                "SELECT file_type, COUNT(*) FROM fichiers WHERE utilisateur_id = ? GROUP BY file_type", 
                (user_id,)
            )
            file_stats = dict(self.cursor.fetchall())
            self.cursor.execute("SELECT COUNT(*) FROM textes WHERE utilisateur_id = ?", (user_id,))
            text_count = self.cursor.fetchone()[0]
            self.cursor.execute("SELECT COUNT(*) FROM impressions WHERE utilisateur_id = ?", (user_id,))
            print_count = self.cursor.fetchone()[0]
            return {
                "total_usage_time": total_time,
                "file_stats": file_stats,
                "text_count": text_count,
                "print_count": print_count
            }
        except sqlite3.Error as e:
            logging.error(f"Usage stats retrieval error: {e}")
            return {}

    def update_usage_time(self, user_id: int, additional_time: int) -> None:
        """Update a user's total usage time."""
        try:
            self.cursor.execute(
                "UPDATE utilisateurs SET total_usage_time = total_usage_time + ? WHERE id = ?",
                (additional_time, user_id)
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Usage time update error: {e}")

    def fermer_connexion(self):
        """Close the database connection."""
        try:
            self.conn.close()
        except sqlite3.Error as e:
            logging.error(f"Database close error: {e}")