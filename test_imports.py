"""快速测试 Web Dashboard 导入"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("1. testing db import...")
from src.web_dashboard import db
print("   db OK")
print("2. testing collector import...")
from src.web_dashboard.collector import DashboardCollector
print("   collector OK")
print("3. testing server import...")
from src.web_dashboard.server import app
print("   server OK")
print("\n✅ All imports passed!")
