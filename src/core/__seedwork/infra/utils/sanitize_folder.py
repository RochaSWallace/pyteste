import re

def sanitize_folder_name(folder_name):
        name = (folder_name[:200]) if len(folder_name) > 200 else folder_name
        sanitized_name = re.sub(r'[\\/:*?"<>|]', '', name)
        return sanitized_name.strip()