import subprocess
subprocess.run(["git", "add", "-A"], check=True)
msg = """fix(ui): match average input style and block non-numeric input

- Remove custom avg-input CSS so fields use standard form-control style
- Add global CSS to hide number input spinners on all type=number fields
- Add keydown filter to average inputs to block non-digit characters
- Replace pre with div in audit modal for correct light/dark theme colors"""
subprocess.run(["git", "commit", "-m", msg], check=True)
