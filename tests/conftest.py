import os
import sys

# Ensure src/ is importable as top-level package
ROOT = os.path.abspath(os.getcwd())
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

