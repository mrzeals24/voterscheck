import os
import zipfile

def extract_and_truncate_pdfs():
    # Source zip file path
    zip_path = r"C:\Users\prash\OneDrive\Prashanth\IdeaProjects\votersworkspace\voterscheck\pdfs\AC 175 Bommanahalli-20260808T110311Z-1-001.zip"
    if not os.path.exists(zip_path):
        zip_path = r"C:\Users\prash\OneDrive\Prashanth\IdeaProjects\votersworkspace\voterscheck\pdfs\AC 175 Bommanahalli-20260808T110311Z-1-001.pdf"

    # Destination folder path
    dest_path = r"C:\Users\prash\OneDrive\Prashanth\IdeaProjects\votersworkspace\voterscheck\pdfs\175-Bommanahalli"
    extended_dest_path = "\\\\?\\" + os.path.abspath(dest_path)

    if not os.path.exists(zip_path):
        print(f"Error: Could not find the source archive at {zip_path}")
        return

    print(f"Extracting and truncating files to: {dest_path}\n")
    os.makedirs(extended_dest_path, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.namelist():
                # Skip directory structures inside the zip, we will flatten or handle files directly
                if member.endswith('/'):
                    continue
                
                # Get just the file name out of any nested zip folders
                original_filename = os.path.basename(member)
                if not original_filename:
                    continue
                
                # Separate name and extension
                name_part, ext_part = os.path.splitext(original_filename)
                
                # Truncate to 50 characters if it's too long
                if len(name_part) > 50:
                    name_part = name_part[:50].strip()
                
                # Form the new file name
                new_filename = f"{name_part}{ext_part}"
                target_path = os.path.join(extended_dest_path, new_filename)
                
                # Handle potential duplicate names caused by truncation
                counter = 1
                while os.path.exists(target_path):
                    target_path = os.path.join(extended_dest_path, f"{name_part}_{counter}{ext_part}")
                    counter += 1

                # Extract and write the file
                with zip_ref.open(member) as source, open(target_path, "wb") as target:
                    target.write(source.read())
                    
                print(f"Extracted: {os.path.basename(target_path)}")
                
        print("\nSUCCESS: All PDFs extracted and truncated successfully!")
        
    except Exception as e:
        print(f"\nAn error occurred during extraction: {e}")

if __name__ == "__main__":
    extract_and_truncate_pdfs()
