import os
import hashlib
from pathlib import Path

def get_file_hash(filepath):
    """Get MD5 hash of a file"""
    try:
        with open(filepath, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        return f"ERROR: {e}"

def compare_directories():
    """Compare PHP files between Chatbot/php and xampp/htdocs/php"""
    chatbot_dir = r"C:\Users\Administrator\Chatbot\php"
    htdocs_dir = r"C:\xampp\htdocs\php"
    
    print("=" * 80)
    print("COMPARING PHP FILES")
    print("=" * 80)
    
    # Get all PHP files from Chatbot directory
    chatbot_files = {}
    if os.path.exists(chatbot_dir):
        for file in os.listdir(chatbot_dir):
            if file.endswith('.php'):
                filepath = os.path.join(chatbot_dir, file)
                chatbot_files[file] = get_file_hash(filepath)
    
    # Get all PHP files from htdocs directory
    htdocs_files = {}
    if os.path.exists(htdocs_dir):
        for file in os.listdir(htdocs_dir):
            if file.endswith('.php'):
                filepath = os.path.join(htdocs_dir, file)
                htdocs_files[file] = get_file_hash(filepath)
    
    # Compare files
    all_files = set(chatbot_files.keys()) | set(htdocs_files.keys())
    
    identical = []
    different = []
    only_chatbot = []
    only_htdocs = []
    
    for file in sorted(all_files):
        chatbot_hash = chatbot_files.get(file)
        htdocs_hash = htdocs_files.get(file)
        
        if chatbot_hash and htdocs_hash:
            if chatbot_hash == htdocs_hash:
                identical.append(file)
            else:
                different.append(file)
        elif chatbot_hash:
            only_chatbot.append(file)
        else:
            only_htdocs.append(file)
    
    # Print results
    print(f"\n✓ IDENTICAL FILES ({len(identical)}):")
    for file in identical:
        print(f"  ✓ {file}")
    
    if different:
        print(f"\n⚠ DIFFERENT FILES ({len(different)}):")
        for file in different:
            print(f"  ⚠ {file}")
            print(f"     Chatbot: {chatbot_files[file]}")
            print(f"     Htdocs:  {htdocs_files[file]}")
    
    if only_chatbot:
        print(f"\n⚠ ONLY IN CHATBOT FOLDER ({len(only_chatbot)}):")
        for file in only_chatbot:
            print(f"  • {file}")
    
    if only_htdocs:
        print(f"\n⚠ ONLY IN HTDOCS FOLDER ({len(only_htdocs)}):")
        for file in only_htdocs:
            print(f"  • {file}")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total files compared: {len(all_files)}")
    print(f"✓ Identical: {len(identical)}")
    print(f"⚠ Different: {len(different)}")
    print(f"⚠ Missing in htdocs: {len(only_chatbot)}")
    print(f"⚠ Extra in htdocs: {len(only_htdocs)}")
    
    if different or only_chatbot:
        print("\n" + "=" * 80)
        print("ACTION REQUIRED")
        print("=" * 80)
        if different:
            print(f"Files need to be synced to htdocs:")
            for file in different:
                print(f"  - {file}")
        if only_chatbot:
            print(f"\nFiles need to be copied to htdocs:")
            for file in only_chatbot:
                print(f"  - {file}")
        
        print("\nRun this command to copy all files:")
        print(f"  Copy-Item '{chatbot_dir}\\*.php' '{htdocs_dir}' -Force")
    else:
        print("\n✓ All PHP files are synchronized!")

if __name__ == "__main__":
    compare_directories()
