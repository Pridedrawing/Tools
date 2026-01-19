import pandas as pd
import requests

# Load the data
file_path = 'D:/Windows-Dateienordner/Dokumente/DAZ 3D/Novel/Test/Tools/Language Detection/dialogue.tab'
df = pd.read_csv(file_path, sep='\t')

# DeepL API key
DEEPL_API_KEY = 'bcf9bc45-3353-4e6a-7394-8923c47ce64e'

# Function to detect language using DeepL API
def detect_language(text):
    url = "https://api.deepl.com/v2/translate"  # Correct endpoint
    params = {
        "auth_key": DEEPL_API_KEY,
        "text": text,
        "target_lang": "EN"  # Target language doesn't matter for detection
    }
    response = requests.post(url, data=params)
    
    # Log the response for debugging
    print(f"Response: {response.json()}")
    
    if response.status_code == 200:
        result = response.json()
        if 'translations' in result and result['translations']:
            return result['translations'][0].get('detected_source_language', 'unknown')
        else:
            return 'unknown'
    else:
        return 'error'

# Apply language detection to the "Dialogue" column
df['Language'] = df['Dialogue'].apply(detect_language)

# Save the updated dataframe to a new file
output_path = 'D:/Windows-Dateienordner/Dokumente/DAZ 3D/Novel/Test/Tools/Language Detection/dialogue_with_language.tab'
df.to_csv(output_path, sep='\t', index=False)

print("Language detection completed and saved to:", output_path)
