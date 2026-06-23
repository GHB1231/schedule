"""
WSGI 入口 — PythonAnywhere 部署用
"""
import os
import sys

# 把项目目录加到 Python 路径
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# 设置数据目录
os.environ.setdefault("DATA_DIR", os.path.join(project_dir, "data_storage"))

from app import app as application
