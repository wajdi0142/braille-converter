import os
import re
import getpass
import random
import logging
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QInputDialog, QLabel, QLineEdit, QMessageBox
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from backend.database import Database

# Configure logging
logging.basicConfig(filename="auth.log", level=logging.ERROR)

class AuthWidget(QWidget):
    """Widget for user authentication."""
    
    logout_signal = pyqtSignal()

    def __init__(self, parent):
        """Initialize the authentication widget."""
        super().__init__(parent)
        self.parent = parent
        self.db = Database()
        try:
            self.device_user = getpass.getuser()
        except Exception as e:
            logging.error(f"Failed to get device user: {e}")
            self.device_user = "unknown_user"
        self.verification_code = None
        self.logged_in_email = None
        # SMTP settings (disabled by default)
        self.smtp_enabled = False  # Set to True with valid credentials
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.smtp_user = os.getenv("SMTP_USER", "your_email@gmail.com")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "your_app_password")
        self.init_ui()

    def init_ui(self):
        """Set up the authentication UI."""
        self.setStyleSheet("""
            QWidget {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 10px;
                padding: 20px;
            }
            QLabel {
                font-size: 16px;
                color: #333;
            }
            QLineEdit {
                padding: 5px;
                border: 1px solid #999;
                border-radius: 5px;
                background-color: #fff;
            }
            QPushButton {
                padding: 8px 15px;
                border: 1px solid #555;
                border-radius: 5px;
                background-color: #4CAF50;
                color: white;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)

        self.main_layout = QVBoxLayout()
        self.main_layout.setAlignment(Qt.AlignCenter)

        # Titre
        self.title_label = QLabel("Authentification")
        self.title_label.setFont(QFont("Arial", 18, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.title_label)
        self.main_layout.addSpacing(20)

        # Email field
        self.email_layout = QHBoxLayout()
        self.email_label = QLabel("Email :")
        self.email_input = QLineEdit()
        self.email_layout.addWidget(self.email_label)
        self.email_layout.addWidget(self.email_input)
        self.main_layout.addLayout(self.email_layout)

        # Password field
        self.password_layout = QHBoxLayout()
        self.password_label = QLabel("Mot de passe :")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_layout.addWidget(self.password_label)
        self.password_layout.addWidget(self.password_input)
        self.main_layout.addLayout(self.password_layout)

        # Buttons
        self.button_layout = QHBoxLayout()
        self.login_button = QPushButton("Connexion")
        self.email_auth_button = QPushButton("Connexion par Email")
        self.register_button = QPushButton("Inscription")
        self.forgot_password_button = QPushButton("Mot de passe oublié ?")
        self.login_button.clicked.connect(self.login)
        self.email_auth_button.clicked.connect(self.email_auth)
        self.register_button.clicked.connect(self.register)
        self.forgot_password_button.clicked.connect(self.forgot_password)
        self.button_layout.addWidget(self.login_button)
        self.button_layout.addWidget(self.email_auth_button)
        self.button_layout.addWidget(self.register_button)
        self.button_layout.addWidget(self.forgot_password_button)
        self.main_layout.addLayout(self.button_layout)

        # Status message (initially hidden)
        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Arial", 14))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setVisible(False)  # Hidden by default
        self.main_layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

        # Logout button (after status message, initially hidden)
        self.logout_button = QPushButton("Déconnexion")
        self.logout_button.clicked.connect(self.logout)
        self.logout_button.setVisible(False)
        self.main_layout.addWidget(self.logout_button, alignment=Qt.AlignCenter)

        self.setLayout(self.main_layout)

    def check_device_auth(self):
        """Check if the device is authenticated."""
        try:
            device_user = self.db.get_device_user(self.device_user)
            if device_user:
                self.logged_in_email = device_user[2]
                self.show_logged_in_interface()
                user_info = {"nom": device_user[1], "email": device_user[2]}
                self.parent.show_main_interface(self.logged_in_email, user_info)
            else:
                self.show_login_interface()
        except Exception as e:
            logging.error(f"Device auth check error: {e}")
            self.status_label.setText("Erreur d'authentification")
            self.status_label.setVisible(True)

    def validate_email(self, email):
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        return re.match(pattern, email) is not None

    def login(self):
        """Handle user login."""
        email = self.email_input.text().strip()
        password = self.password_input.text().strip()
        if not email or not password:
            QMessageBox.warning(self, "Error", "Please fill in all fields.")
            return

        if not self.validate_email(email):
            QMessageBox.warning(self, "Error", "Invalid email format.")
            return

        try:
            user = self.db.verify_user(email, password)
            if user:
                self.db.save_device_auth(self.device_user, user[0])
                self.logged_in_email = email
                QMessageBox.information(self, "Success", "Login successful!")
                self.show_logged_in_interface()
                user_info = {"nom": user[1], "email": user[2]}
                self.parent.show_main_interface(self.logged_in_email, user_info)
            else:
                QMessageBox.warning(self, "Error", "Incorrect email or password.")
        except Exception as e:
            logging.error(f"Login error: {e}")
            QMessageBox.critical(self, "Error", f"Login failed: {e}")

    def email_auth(self):
        """Handle email-based authentication."""
        email = self.email_input.text().strip()
        if not email:
            QMessageBox.warning(self, "Error", "Please enter your email.")
            return

        if not self.validate_email(email):
            QMessageBox.warning(self, "Error", "Invalid email format.")
            return

        try:
            self.verification_code = random.randint(100000, 999999)
            if self.smtp_enabled:
                self.send_verification_email(email, self.verification_code)
            else:
                QMessageBox.information(
                    self, 
                    "Simulation", 
                    f"Verification code (simulated): {self.verification_code}"
                )

            code, ok = QInputDialog.getText(
                self, 
                "Verification", 
                "Enter the verification code:",
                QLineEdit.Normal, 
                ""
            )
            if ok and code.strip() == str(self.verification_code):
                user = self.db.get_utilisateur_by_email(email)
                if user:
                    self.db.save_device_auth(self.device_user, user.id)
                    self.logged_in_email = email
                    QMessageBox.information(self, "Success", "Email login successful!")
                    self.show_logged_in_interface()
                    user_info = {"nom": user.nom, "email": user.email}
                    self.parent.show_main_interface(self.logged_in_email, user_info)
                else:
                    QMessageBox.warning(self, "Error", "No user found with this email.")
            else:
                QMessageBox.warning(self, "Error", "Incorrect verification code.")
        except Exception as e:
            logging.error(f"Email auth error: {e}")
            QMessageBox.critical(self, "Error", f"Email authentication failed: {e}")

    def register(self):
        """Handle user registration."""
        email = self.email_input.text().strip()
        password = self.password_input.text().strip()
        if not email or not password:
            QMessageBox.warning(self, "Error", "Please fill in all fields.")
            return

        if not self.validate_email(email):
            QMessageBox.warning(self, "Error", "Invalid email format.")
            return

        if len(password) < 6:
            QMessageBox.warning(self, "Error", "Password must be at least 6 characters.")
            return

        try:
            nom = email.split("@")[0]
            self.db.ajouter_utilisateur(nom, email, password)
            QMessageBox.information(
                self, 
                "Success", 
                "Registration successful! You can now log in."
            )
            self.email_input.clear()
            self.password_input.clear()
        except ValueError as e:
            logging.error(f"Registration error: {e}")
            QMessageBox.warning(self, "Error", str(e))
        except Exception as e:
            logging.error(f"Registration error: {e}")
            QMessageBox.critical(self, "Error", f"Registration failed: {e}")

    def forgot_password(self):
        """Handle password reset."""
        email = self.email_input.text().strip()
        if not email:
            QMessageBox.warning(self, "Error", "Please enter your email.")
            return

        if not self.validate_email(email):
            QMessageBox.warning(self, "Error", "Invalid email format.")
            return

        try:
            user = self.db.get_utilisateur_by_email(email)
            if user:
                new_code = random.randint(100000, 999999)
                if self.smtp_enabled:
                    self.send_verification_email(email, new_code, is_reset=True)
                else:
                    QMessageBox.information(
                        self, 
                        "Simulation", 
                        f"Reset code (simulated): {new_code}"
                    )

                code, ok = QInputDialog.getText(
                    self, 
                    "Reset", 
                    "Enter the reset code:",
                    QLineEdit.Normal, 
                    ""
                )
                if ok and code.strip() == str(new_code):
                    new_password, ok = QInputDialog.getText(
                        self, 
                        "New Password",
                        "Enter a new password:", 
                        QLineEdit.Password
                    )
                    if ok and new_password and len(new_password) >= 6:
                        self.db.update_password(email, new_password)
                        QMessageBox.information(self, "Success", "Password reset successfully!")
                    else:
                        QMessageBox.warning(
                            self, 
                            "Error", 
                            "Password must be at least 6 characters."
                        )
                else:
                    QMessageBox.warning(self, "Error", "Incorrect reset code.")
            else:
                QMessageBox.warning(self, "Error", "No user found with this email.")
        except Exception as e:
            logging.error(f"Password reset error: {e}")
            QMessageBox.critical(self, "Error", f"Password reset failed: {e}")

    def send_verification_email(self, email, code, is_reset=False):
        """Send a verification email (disabled by default)."""
        from email.mime.text import MIMEText
        import smtplib
        subject = "Verification Code" if not is_reset else "Password Reset"
        body = f"Your verification code is: {code}\nThis code is valid for 10 minutes."
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = self.smtp_user
        msg['To'] = email

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
        except Exception as e:
            logging.error(f"Email send error: {e}")
            raise Exception(f"Failed to send email: {str(e)}")

    def show_logged_in_interface(self):
        """Show the logged-in interface."""
        try:
            # Hide login-related widgets
            self.email_label.hide()
            self.email_input.hide()
            self.password_label.hide()
            self.password_input.hide()
            self.login_button.hide()
            self.email_auth_button.hide()
            self.register_button.hide()
            self.forgot_password_button.hide()

            # Show status label and logout button
            self.status_label.setText(f"Connecté en tant que {self.logged_in_email}")
            self.status_label.setFont(QFont("Arial", 14, QFont.Bold))
            self.status_label.setVisible(True)  # Show the status label
            self.logout_button.setVisible(True)
        except Exception as e:
            logging.error(f"Show logged-in interface error: {e}")
            QMessageBox.critical(self, "Error", f"Failed to show logged-in interface: {e}")

    def show_login_interface(self):
        """Show the login interface."""
        try:
            # Show login-related widgets
            self.email_label.show()
            self.email_input.show()
            self.password_label.show()
            self.password_input.show()
            self.login_button.show()
            self.email_auth_button.show()
            self.register_button.show()
            self.forgot_password_button.show()

            # Hide status label and logout button
            self.status_label.setVisible(False)  # Hide the status label
            self.logout_button.setVisible(False)
        except Exception as e:
            logging.error(f"Show login interface error: {e}")
            QMessageBox.critical(self, "Error", f"Failed to show login interface: {e}")

    def logout(self):
        """Handle user logout."""
        try:
            self.db.save_device_auth(self.device_user, None)
            self.logged_in_email = None
            self.show_login_interface()
            QMessageBox.information(self, "Succès", "Déconnexion réussie !")
            # Emit the logout signal to notify the parent, but the parent will handle visibility
            self.logout_signal.emit()
        except Exception as e:
            logging.error(f"Logout error: {e}")
            QMessageBox.critical(self, "Error", f"Logout failed: {e}")

    def logged_in_event(self):
        """Clear input fields and show login interface after logout."""
        self.email_input.clear()
        self.password_input.clear()
        self.show_login_interface()