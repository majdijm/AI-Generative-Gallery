import os
import shutil
import json

def prepare_for_github():
    """
    Prepare the project for GitHub push by:
    1. Ensuring the uploads directory has only a .gitkeep file
    2. Creating a clean metadata.json file if it doesn't exist
    3. Checking for any temporary files to remove
    """
    print("Preparing project for GitHub push...")
    
    # 1. Clean uploads directory
    uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    if os.path.exists(uploads_dir):
        print(f"Cleaning uploads directory: {uploads_dir}")
        # Keep track of files to preserve
        files_to_keep = ['.gitkeep']
        
        # Remove all files except those in files_to_keep
        for filename in os.listdir(uploads_dir):
            if filename not in files_to_keep:
                file_path = os.path.join(uploads_dir, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                        print(f"  Removed: {filename}")
                except Exception as e:
                    print(f"  Error removing {filename}: {e}")
    
    # 2. Create a clean metadata.json if it doesn't exist
    metadata_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'metadata.json')
    if not os.path.exists(metadata_file) or os.path.getsize(metadata_file) == 0:
        print(f"Creating clean metadata.json file")
        with open(metadata_file, 'w') as f:
            json.dump({}, f)
    else:
        print(f"Backing up existing metadata.json")
        # Create a backup of the current metadata
        shutil.copy2(metadata_file, f"{metadata_file}.bak")
        
        # Create a clean metadata file
        with open(metadata_file, 'w') as f:
            json.dump({}, f)
    
    # 3. Check for any __pycache__ directories
    for root, dirs, files in os.walk(os.path.dirname(os.path.abspath(__file__))):
        if '__pycache__' in dirs:
            pycache_dir = os.path.join(root, '__pycache__')
            print(f"Removing __pycache__ directory: {pycache_dir}")
            try:
                shutil.rmtree(pycache_dir)
            except Exception as e:
                print(f"  Error removing {pycache_dir}: {e}")
    
    print("Project prepared for GitHub push!")
    print("\nReminder: The following files will be excluded by .gitignore:")
    print("  - uploads/* (except .gitkeep)")
    print("  - metadata.json")
    print("  - metadata.json.bak")
    print("  - __pycache__/")
    print("  - venv/")
    print("  - instance/")
    
    print("\nTo push to GitHub, use the following commands:")
    print("  git add .")
    print("  git commit -m \"Your commit message\"")
    print("  git push origin main")

if __name__ == "__main__":
    prepare_for_github()
