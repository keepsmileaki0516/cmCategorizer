import os
import sys

# Add skills path for importing
skills_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if skills_path not in sys.path:
    sys.path.append(skills_path)

from alldelete.DiscordDeleter import run as delete_run

if __name__ == "__main__":
    channel_id = sys.argv[1] if len(sys.argv) > 1 else None
    result = delete_run(channel_id)
    print(result)
    sys.exit(0 if "Error" not in result else 1)