"""PyInstaller pre-import hook: no ORT uploader even during frozen startup."""
import os
os.environ['ORT_DISABLE_TELEMETRY'] = '1'
os.environ['PYTHONUTF8'] = '1'
os.environ['PYTHONIOENCODING'] = 'utf-8:backslashreplace'
