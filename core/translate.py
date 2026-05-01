from deep_translator import GoogleTranslator
import textwrap
import re

def clean_text(text):
    """
    Replaces multiple whitespace characters (including newlines) with a single space.
    This prevents PDFs from breaking sentences into isolated words.
    """
    return re.sub(r'\s+', ' ', text).strip()

def translate_to_english(text):
    """
    Translates non-English text to English.
    If the text is already English, it generally remains unchanged.
    Handles chunking for large texts (Google Translate limit is 5000 chars).
    """
    if not text or not text.strip():
        return text

    # Clean text to restore sentence structure
    text = clean_text(text)

    # Initialize translator (auto-detect source, translate to english)
    translator = GoogleTranslator(source='auto', target='en')
    
    # Chunk the text to avoid the 5000 character limit
    # Since we cleaned the text, we can use replace_whitespace=True
    chunks = textwrap.wrap(text, width=4500, replace_whitespace=True, drop_whitespace=True)
    
    translated_chunks = []
    for chunk in chunks:
        try:
            translated_chunk = translator.translate(chunk)
            translated_chunks.append(translated_chunk)
        except Exception as e:
            print(f"Translation warning on chunk: {e}")
            # If translation fails, fallback to original chunk
            translated_chunks.append(chunk)
            
    return "".join(translated_chunks)

if __name__ == "__main__":
    # Test cases
    test_hindi = "नमस्ते, मेरा नाम जॉन है और मेरी जन्म तिथि 1990-01-01 है।"
    print(f"Original: {test_hindi}")
    print(f"Translated: {translate_to_english(test_hindi)}")
    
    test_english = "This is already in English."
    print(f"Original: {test_english}")
    print(f"Translated: {translate_to_english(test_english)}")
