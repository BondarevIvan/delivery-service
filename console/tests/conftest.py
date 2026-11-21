"""Делает app/upstream импортируемыми при прогоне тестов из console/."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# фоновое автоназначение выключаем, чтобы тесты не ходили в сеть
os.environ.setdefault("AUTO_DISPATCH", "0")
