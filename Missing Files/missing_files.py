import os
import subprocess
import sys

# Function to check if a package is installed
def check_and_install(package):
    try:
        __import__(package)
    except ImportError:
        user_input = input(f"The package '{package}' is not installed. Do you want to install it? (yes/no): ").strip().lower()
        if user_input == 'yes':
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
        else:
            print(f"The package '{package}' is required. Exiting.")
            exit()

# Check and install necessary packages
check_and_install('pandas')
check_and_install('send2trash')

import pandas as pd
from send2trash import send2trash

# Ask user for the base directory
base_dir = input("Enter the base directory (e.g., C:\\Users\\olli_\\Documents\\GitHub\\BoundToCollege): ").strip()

# Set the path to the dialogue.tab file
file_path = os.path.join(base_dir, 'dialogue.tab')

# Set the path to the audio folder
audio_folder_path = os.path.join(base_dir, 'game', 'audio', 'voice')

# Check if the dialogue.tab file exists
if not os.path.exists(file_path):
    print(f"The file '{file_path}' does not exist. Please check the path and try again.")
    exit()

# Check if the audio folder exists
if not os.path.exists(audio_folder_path):
    print(f"The audio folder '{audio_folder_path}' does not exist. Please check the path and try again.")
    exit()

# Read the text file with tab separator
spreadsheet = pd.read_csv(file_path, sep='\t')

# Column name in the spreadsheet that contains the audio file names
file_name_column = 'Identifier'

# Get a list of all files in the audio folder (without extensions)
audio_files = set(os.path.splitext(file)[0] for file in os.listdir(audio_folder_path) if file.endswith('.mp3'))

# Get a list of all audio file names from the spreadsheet
spreadsheet_files = set(spreadsheet[file_name_column].tolist())

# Find missing files
missing_files = spreadsheet_files - audio_files

# Find files in the folder that are not listed in the spreadsheet
extra_files = audio_files - spreadsheet_files

# Output the missing files
if missing_files:
    print("The following files are missing from the folder:")
    for file in missing_files:
        print(file)
else:
    print("No files are missing.")

# Output the extra files
if extra_files:
    print("\nThe following files are in the folder but not listed in the spreadsheet:")
    for file in extra_files:
        print(file)
else:
    print("All files in the folder are listed in the spreadsheet.")

# Initialize counters
deleted_files_count = 0

# Prompt user for deletion
if extra_files:
    user_input = input("\nDo you want to move the extra files to the recycle bin? (y)es/(n)o: ").strip().lower()
    if user_input == 'y':
        for file in extra_files:
            file_path = os.path.join(audio_folder_path, file + '.mp3')  # Assuming all files have the .mp3 extension
            if os.path.exists(file_path) and os.path.isfile(file_path):
                send2trash(file_path)
                deleted_files_count += 1
                print(f"Moved to recycle bin: {file_path}")
        print("All extra files have been moved to the recycle bin.")
    else:
        print("No files were moved to the recycle bin.")

# Filter the spreadsheet to keep only rows with missing files
missing_files_df = spreadsheet[spreadsheet[file_name_column].isin(missing_files)]

# Save the filtered dataframe to a new tab-separated file
missing_files_df.to_csv('dialogue_missing.tab', sep='\t', index=False)

# Display summary
print("\nSummary:")
print(f"Number of missing files: {len(missing_files)}")
print(f"Number of files moved to recycle bin: {deleted_files_count}")
print(f"Number of files not listed in the spreadsheet: {len(extra_files)}")
