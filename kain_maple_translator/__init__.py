"""Configure offline privacy BEFORE any ONNX Runtime import/initialization."""
import os

# API-only disabling happens too late for the minimal 1DS initialization
# event. This documented pre-init opt-out prevents uploader/device-ID setup.
os.environ['ORT_DISABLE_TELEMETRY'] = '1'
