import google.generativeai as genai
import logging
import os

class Translator:
    def __init__(self):
        # Configure the Gemini API with your API key
        # Replace 'YOUR_GEMINI_API_KEY' with your actual API key
        # It is recommended to use environment variables to store API keys
        api_key = os.getenv("GEMINI_API_KEY", "AIzaSyBwhOKUNWKGCMB-Rx74Z9fhPJccECEfzBM") # Replace AIzaSyC1
        if api_key == "YOUR_GEMINI_API_KEY":
             logging.warning("GEMINI_API_KEY environment variable not set or using placeholder. Please replace 'YOUR_GEMINI_API_KEY' with your actual key or set the environment variable.")

        genai.configure(api_key=api_key)

        # Initialize the Gemini model for text generation
        self.model = genai.GenerativeModel('gemini-1.5-flash-latest') # Using a suitable model for text tasks

        # Define a list of commonly used languages for the UI, as Gemini supports many languages
        self.supported_languages = [
            'Français', 'English', 'Español', 'Deutsch', 'Italiano', 
            'Português', 'Русский', '中文', '日本語', 'العربية'
        ]

    def get_supported_languages(self):
        """Returns a list of commonly supported languages for the UI."""
        return self.supported_languages

    def translate_text(self, text, source_lang_name, target_lang_name):
        """
        Translates the text from the source language to the target language using Gemini.
        
        Args:
            text (str): The text to translate
            source_lang_name (str): The source language name
            target_lang_name (str): The target language name
            
        Returns:
            str: The translated text
        """
        try:
            prompt = f"Translate the following text from {source_lang_name} to {target_lang_name}:\n\n{text}"
            response = self.model.generate_content(prompt)
            # Extract the translated text from the model's response
            # Adjust this based on the actual response structure of the model
            translated_text = response.text.strip()
            return translated_text

        except Exception as e:
            logging.error(f"Error during translation with Gemini API: {str(e)}")
            # Re-raise the exception to be handled by the caller (BrailleUI)
            raise Exception(f"Translation error: {str(e)}")

    def detect_language(self, text):
        """
        Detects the language of the text using Gemini.
        
        Args:
            text (str): The text to analyze
            
        Returns:
            str: The detected language name or None if detection fails
        """
        try:
            prompt = f"Detect the language of the following text and respond with only the language name (e.g., English, French):\n\n{text}"
            response = self.model.generate_content(prompt)
            # Extract the detected language name from the model's response
            detected_lang_name = response.text.strip()
            
            # Basic validation/mapping if needed, or just return the model's response
            # For simplicity, returning the model's response directly
            return detected_lang_name if detected_lang_name else None

        except Exception as e:
            logging.error(f"Error during language detection with Gemini API: {str(e)}")
            return None # Return None on error 