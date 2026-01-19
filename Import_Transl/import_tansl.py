import os
import csv
import shutil

def list_games(base_folder):
    return [f for f in os.listdir(base_folder) if os.path.isdir(os.path.join(base_folder, f))]

def load_translations(csv_path):
    translations = {}
    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if len(row) >= 2:
                translations[row[0].strip()] = row[1].strip()
    return translations

def extract_translation_keys(file_path):
    keys = set()
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped_line = line.strip()
            if stripped_line.startswith("translate portuguese"):
                parts = stripped_line.split(" ", 2)
                if len(parts) > 2:
                    keys.add(parts[2].strip())
    return keys

def update_translation_files(game_folder, translations):
    tl_folder = os.path.join(game_folder, "game", "tl", "portuguese")
    if not os.path.exists(tl_folder):
        print(f"Translation folder not found: {tl_folder}")
        return

    replaced, added, missing = 0, 0, 0
    missing_keys = []
    found_keys = set()
    
    for root, _, files in os.walk(tl_folder):
        for file in files:
            if file.endswith(".rpy"):
                file_path = os.path.join(root, file)
                found_keys.update(extract_translation_keys(file_path))
                backup_path = file_path + ".bak"
                shutil.copy(file_path, backup_path)  # Create a backup
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                with open(file_path, "w", encoding="utf-8") as f:
                    for line in lines:
                        stripped_line = line.strip()
                        if stripped_line.startswith("translate portuguese"):
                            parts = stripped_line.split(" ", 2)
                            if len(parts) > 2:
                                key = parts[2].strip()
                                if key in translations:
                                    f.write(f'    "{translations[key]}"\n')
                                    replaced += 1
                                else:
                                    missing_keys.append(key)
                                    f.write(line)
                                    missing += 1
                        else:
                            f.write(line)
    
    print(f"Translations replaced: {replaced}")
    print(f"Translations missing: {missing}")
    
    print("Keys found in .rpy files but not in CSV:")
    for key in (found_keys - translations.keys()):
        print(f" - {key}")
    
    print("Keys in CSV but not in .rpy files:")
    for key in (translations.keys() - found_keys):
        print(f" - {key}")
    
    print("Update complete!")

def main():
    base_folder = r"D:\Windows-Dateienordner\Dokumente\DAZ 3D\Novel\Test"
    csv_path = os.path.join(base_folder, "Tools", "Import_Transl", "dialogue.csv")
    
    if not os.path.exists(csv_path):
        print("Translation file not found!")
        return

    games = list_games(base_folder)
    if not games:
        print("No games found in Test folder.")
        return
    
    print("Available games:")
    for idx, game in enumerate(games, 1):
        print(f"{idx}. {game}")
    
    choice = int(input("Select a game by number: ")) - 1
    if choice < 0 or choice >= len(games):
        print("Invalid choice.")
        return
    
    game_folder = os.path.join(base_folder, games[choice])
    confirm = input(f"Are you sure you want to update translations for {games[choice]}? (yes/no): ")
    if confirm.lower() != "yes":
        print("Operation canceled.")
        return
    
    translations = load_translations(csv_path)
    update_translation_files(game_folder, translations)

if __name__ == "__main__":
    main()
