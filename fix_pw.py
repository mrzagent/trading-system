import sys

file_path = r"D:\dev\trading\backtest_fvg_15min_confirm.py"

with open(file_path, 'r') as f:
    content = f.read()

# Replace the password line
old_pw = '"password": "***"'
new_pw = '"password": "***"'

if old_pw in content:
    content = content.replace(old_pw, new_pw)
    with open(file_path, 'w') as f:
        f.write(content)
    print("Password updated successfully")
else:
    print("Password pattern not found")
    # Let's see what's there
    for i, line in enumerate(content.split('\n')):
        if 'password' in line.lower():
            print(f"Line {i}: {repr(line)}")
