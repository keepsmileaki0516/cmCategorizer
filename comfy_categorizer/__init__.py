import os
import sys

# Add skills path for importing
skills_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if skills_path not in sys.path:
    sys.path.append(skills_path)

from comfy_categorizer.comfy_categorizer import ComfyCategorizer

def run():
    cc = ComfyCategorizer()
    
    target_num = None
    workflow_type = 'default'
    
    if len(sys.argv) > 1:
        first_arg = sys.argv[1]
        
        # Parse format: "5" or "5,detailed"
        if first_arg.isdigit():
            target_num = int(first_arg)
        elif ',' in first_arg:
            parts = first_arg.split(',')
            if parts[0].isdigit():
                target_num = int(parts[0])
            if len(parts) > 1:
                workflow_type = parts[1].strip()
        else:
            workflow_type = first_arg
    
    result = cc.run(target_num=target_num, workflow_type=workflow_type)
    print("Result:", result)
    return result

if __name__ == "__main__":
    run()