#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SQLite 数据库层
存储性能测试任务和采集数据，支持离线分析和历史回看
"""

import os
import sqlite3
import time
from datetime import datetime

DB_DIR = None  # 由 server.py 启动时设置
DB_FILENAME = "perf_dashboard.db"


def get_db_path():
    """获取数据库文件路径"""
    if DB_DIR:
        db_dir = DB_DIR
    else:
        db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results')
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, DB_FILENAME)


def get_connection():
    """获取数据库连接（线程安全，check_same_thread=False）"""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表结构"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time REAL,
            end_time REAL,
            device_id TEXT,
            device_model TEXT,
            device_brand TEXT,
            sdk_version TEXT,
            android_version TEXT,
            package_name TEXT,
            version_name TEXT,
            version_code TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cpu_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            timestamp REAL,
            datetime TEXT,
            total_cpu REAL,
            user_cpu REAL,
            sys_cpu REAL,
            idle_cpu REAL,
            app_cpu REAL,
            mem_used_mb REAL,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mem_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            timestamp REAL,
            datetime TEXT,
            total_pss REAL,
            java_heap REAL,
            native_heap REAL,
            system REAL,
            views INTEGER,
            activities INTEGER,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fd_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            timestamp REAL,
            datetime TEXT,
            fd_count INTEGER,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS thread_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            timestamp REAL,
            datetime TEXT,
            thread_count INTEGER,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fps_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            timestamp REAL,
            datetime TEXT,
            fps REAL,
            jank INTEGER,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
    ''')

    # 设置表（键值对存储持久化配置）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # 崩溃事件表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crash_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            timestamp REAL,
            datetime TEXT,
            old_pid INTEGER,
            log_file TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
    ''')

    # 为 tasks 表增加 crash_count 列（若不存在）
    try:
        cursor.execute('ALTER TABLE tasks ADD COLUMN crash_count INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # 列已存在

    # 清除上一次崩溃残留的活跃任务
    cursor.execute('UPDATE tasks SET end_time=?, is_active=0 WHERE is_active=1',
                   (time.time(),))
    cleaned = cursor.rowcount
    if cleaned:
        print(f'[DB] 清理 {cleaned} 个未正常结束的任务')
    conn.commit()
    conn.close()


# ==================== 持久化设置 ====================

def get_setting(key, default=''):
    """读取持久化设置"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key=?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else default


def set_setting(key, value):
    """保存持久化设置"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    ''', (key, value))
    conn.commit()
    conn.close()


# ---------- 任务管理 ----------

def create_task(device_id, device_model, device_brand, sdk_version, android_version,
                package_name, version_name, version_code):
    """创建新的测试任务"""
    conn = get_connection()
    cursor = conn.cursor()
    now = time.time()
    cursor.execute('''
        INSERT INTO tasks (start_time, device_id, device_model, device_brand, sdk_version,
                           android_version, package_name, version_name, version_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (now, device_id, device_model, device_brand, sdk_version,
          android_version, package_name, version_name, version_code))
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return task_id


def finish_task(task_id):
    """结束测试任务"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE tasks SET end_time=?, is_active=0 WHERE id=?',
                   (time.time(), task_id))
    conn.commit()
    conn.close()


def get_active_task():
    """获取当前活跃的任务"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tasks WHERE is_active=1 ORDER BY id DESC LIMIT 1')
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_tasks(limit=50):
    """获取所有历史任务"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, start_time, end_time, device_model, package_name, version_name, is_active
        FROM tasks ORDER BY id DESC LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_task_by_id(task_id):
    """获取指定任务信息"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tasks WHERE id=?', (task_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ==================== 崩溃事件 ====================

def insert_crash_event(task_id, timestamp, datetime_str, old_pid, log_file):
    """记录崩溃事件"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO crash_events (task_id, timestamp, datetime, old_pid, log_file)
        VALUES (?, ?, ?, ?, ?)
    ''', (task_id, timestamp, datetime_str, old_pid, log_file or ''))
    # 增加 tasks 表的 crash_count
    cursor.execute('UPDATE tasks SET crash_count = COALESCE(crash_count, 0) + 1 WHERE id=?', (task_id,))
    conn.commit()
    conn.close()


def get_crash_events(task_id):
    """获取指定任务的崩溃事件列表"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, timestamp, datetime, old_pid, log_file
        FROM crash_events WHERE task_id=? ORDER BY timestamp ASC
    ''', (task_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_crash_count(task_id):
    """获取指定任务的崩溃次数"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COALESCE(crash_count, 0) as cnt FROM tasks WHERE id=?', (task_id,))
    row = cursor.fetchone()
    conn.close()
    return row['cnt'] if row else 0


# ---------- 数据写入 ----------

def insert_cpu_data(task_id, timestamp, datetime_str, total_cpu, user_cpu, sys_cpu,
                    idle_cpu, app_cpu, mem_used_mb):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO cpu_data (task_id, timestamp, datetime, total_cpu, user_cpu, sys_cpu,
                              idle_cpu, app_cpu, mem_used_mb)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (task_id, timestamp, datetime_str, total_cpu, user_cpu, sys_cpu,
          idle_cpu, app_cpu, mem_used_mb))
    conn.commit()
    conn.close()


def insert_mem_data(task_id, timestamp, datetime_str, total_pss, java_heap, native_heap,
                    system, views, activities):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO mem_data (task_id, timestamp, datetime, total_pss, java_heap, native_heap,
                              system, views, activities)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (task_id, timestamp, datetime_str, total_pss, java_heap, native_heap,
          system, views, activities))
    conn.commit()
    conn.close()


def insert_fd_data(task_id, timestamp, datetime_str, fd_count):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO fd_data (task_id, timestamp, datetime, fd_count)
        VALUES (?, ?, ?, ?)
    ''', (task_id, timestamp, datetime_str, fd_count))
    conn.commit()
    conn.close()


def insert_thread_data(task_id, timestamp, datetime_str, thread_count):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO thread_data (task_id, timestamp, datetime, thread_count)
        VALUES (?, ?, ?, ?)
    ''', (task_id, timestamp, datetime_str, thread_count))
    conn.commit()
    conn.close()


def insert_fps_data(task_id, timestamp, datetime_str, fps, jank):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO fps_data (task_id, timestamp, datetime, fps, jank)
        VALUES (?, ?, ?, ?, ?)
    ''', (task_id, timestamp, datetime_str, fps, jank))
    conn.commit()
    conn.close()


# ---------- 历史查询 ----------

def get_cpu_history(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT timestamp, total_cpu, user_cpu, sys_cpu, app_cpu, mem_used_mb
        FROM cpu_data WHERE task_id=? ORDER BY timestamp ASC
    ''', (task_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_mem_history(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT timestamp, total_pss, java_heap, native_heap, system, views, activities
        FROM mem_data WHERE task_id=? ORDER BY timestamp ASC
    ''', (task_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_fd_history(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT timestamp, fd_count FROM fd_data WHERE task_id=? ORDER BY timestamp ASC
    ''', (task_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_thread_history(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT timestamp, thread_count FROM thread_data WHERE task_id=? ORDER BY timestamp ASC
    ''', (task_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_fps_history(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT timestamp, fps, jank FROM fps_data WHERE task_id=? ORDER BY timestamp ASC
    ''', (task_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
