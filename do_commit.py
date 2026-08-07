"""Commit all changes."""
import subprocess
subprocess.run(["git", "add", "-A"], check=True)
msg = """fix(ui): correct average input format to 000.00 with real-time formatting

- Change average inputs from type=number to type=text with inputmode=decimal
- Auto-format digits as user types: 12345 -> 123.45 (no dot needed)
- Remove maxlength=6 that blocked input when formatted value filled field
- Strip leading zeros during typing so all 5 digit slots are usable
- Add padAverageInput on blur to show final 000.00 format (e.g. 45.45 -> 045.45)
- Add formatAvgForDisplay for admin modal to show stored averages in 000.00 format
- Add shared .avg-input CSS to base.html (centered, tabular-nums)
- Fix test isolation: drop_all before create_all in conftest to purge stale test.db
- Cap average schema validation at le=167 (theoretical 9-darter max)
- Add tests for new input format, no-maxlength, padAverageInput"""
subprocess.run(["git", "commit", "-m", msg], check=True)
