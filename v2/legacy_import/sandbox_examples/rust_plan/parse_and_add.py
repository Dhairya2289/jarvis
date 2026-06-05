import re
import subprocess
import sys
from datetime import date, timedelta

def main():
    md_file = "/home/dhairya/rust_study_plan.md"
    with open(md_file, 'r') as f:
        content = f.read()
    
    # Find lines like "- **Day 1:** Install Rust via rustup, hello world, basic syntax (variables, mutability, data types). *Exercise:* Convert temperature converter."
    # We'll use regex to capture day number and the rest of the line until next Day line or end.
    # Simpler: split by lines and process
    lines = content.split('\n')
    day_re = re.compile(r'- \*\*Day (\d+):\*\* (.+)')
    tasks = []
    for line in lines:
        m = day_re.match(line.strip())
        if m:
            day = int(m.group(1))
            desc = m.group(2).strip()
            # Remove trailing *Exercise:* part? Keep as is.
            tasks.append((day, desc))
    
    if not tasks:
        print("No tasks found")
        return
    
    today = date.today()
    for day, desc in tasks:
        due = today + timedelta(days=day-1)
        due_str = due.isoformat()
        week = ((day-1)//7)+1
        # Add to taskwarrior
        cmd = ['task', 'add', desc, f'tag:rust', f'tag:week{week}', f'tag:day{day}', f'due:{due_str}']
        print(f"Adding: {cmd}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error adding task day {day}: {result.stderr}")
        else:
            print(f"Added task day {day}")

if __name__ == '__main__':
    main()
