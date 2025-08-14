import os
import re
import shutil

def rename_word_clips(directory="."):
    """Rename word clips by removing _001, _002, etc. numbering"""
    
    print(f"Scanning directory: {os.path.abspath(directory)}")
    
    # Find all mp4 files in the current directory
    mp4_files = [f for f in os.listdir(directory) if f.endswith('.mp4')]
    
    if not mp4_files:
        print("No .mp4 files found in current directory!")
        return
    
    print(f"Found {len(mp4_files)} .mp4 files")
    
    renamed_count = 0
    skipped_count = 0
    error_count = 0
    
    for filename in mp4_files:
        try:
            # Check if filename matches pattern word_###.mp4
            name_parts = filename.rsplit('_', 1)  # Split from right, max 1 split
            
            if len(name_parts) == 2:
                word_part = name_parts[0]
                number_part = name_parts[1]  # Should be "001.mp4"
                
                # Check if number part matches pattern (3 digits + .mp4)
                if re.match(r'^\d{3}\.mp4$', number_part):
                    new_filename = f"{word_part}.mp4"
                    
                    # Check if target filename already exists
                    if os.path.exists(new_filename):
                        if new_filename == filename:
                            print(f"  Skip: {filename} (already in correct format)")
                            skipped_count += 1
                        else:
                            print(f"  Warning: {new_filename} already exists, skipping {filename}")
                            skipped_count += 1
                    else:
                        # Rename the file
                        os.rename(filename, new_filename)
                        print(f"  Renamed: {filename} → {new_filename}")
                        renamed_count += 1
                else:
                    print(f"  Skip: {filename} (doesn't match word_###.mp4 pattern)")
                    skipped_count += 1
            else:
                print(f"  Skip: {filename} (no underscore found)")
                skipped_count += 1
                
        except Exception as e:
            print(f"  Error processing {filename}: {e}")
            error_count += 1
    
    print(f"\n=== SUMMARY ===")
    print(f"Files renamed: {renamed_count}")
    print(f"Files skipped: {skipped_count}")
    print(f"Errors: {error_count}")
    print(f"Total processed: {len(mp4_files)}")

def rename_with_backup(directory=".", create_backup=True):
    """Rename files with optional backup"""
    
    if create_backup:
        backup_dir = os.path.join(directory, "backup_original_names")
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
            print(f"Created backup directory: {backup_dir}")
        
        # Copy all mp4 files to backup first
        mp4_files = [f for f in os.listdir(directory) if f.endswith('.mp4')]
        print(f"Backing up {len(mp4_files)} files...")
        
        for filename in mp4_files:
            try:
                shutil.copy2(filename, os.path.join(backup_dir, filename))
            except Exception as e:
                print(f"Error backing up {filename}: {e}")
                return
        
        print("Backup complete!")
    
    # Now rename the files
    rename_word_clips(directory)

def main():
    print("Word Clip Renamer")
    print("This script will rename files from 'word_001.mp4' to 'word.mp4'")
    print("=" * 50)
    
    # Ask user if they want to create backup
    while True:
        backup_choice = input("Create backup before renaming? (y/n): ").lower().strip()
        if backup_choice in ['y', 'yes']:
            create_backup = True
            break
        elif backup_choice in ['n', 'no']:
            create_backup = False
            break
        else:
            print("Please enter 'y' for yes or 'n' for no")
    
    # Confirm before proceeding
    current_dir = os.path.abspath(".")
    print(f"\nWorking directory: {current_dir}")
    
    while True:
        confirm = input("Proceed with renaming? (y/n): ").lower().strip()
        if confirm in ['y', 'yes']:
            break
        elif confirm in ['n', 'no']:
            print("Operation cancelled.")
            return
        else:
            print("Please enter 'y' for yes or 'n' for no")
    
    # Perform the renaming
    if create_backup:
        rename_with_backup()
    else:
        rename_word_clips()
    
    print("\nDone!")

if __name__ == "__main__":
    main()