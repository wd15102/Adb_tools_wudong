#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""向 index.html 的 </style> 前插入崩溃面板 CSS 样式"""

import re

html_path = r'D:\WorkCode\AdbTool-maste\src\web_dashboard\templates\index.html'

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

crash_css = '''
        /* ========== 崩溃事件面板 ========== */
        .crash-event-panel {
            background: rgba(244,114,182,0.05);
            border: 1px solid rgba(244,114,182,0.15);
            border-radius: 12px;
            padding: 0.8rem 1.2rem;
            margin-bottom: 1rem;
            backdrop-filter: blur(16px);
            display: none;
        }
        .crash-panel-header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 0.5rem;
        }
        .crash-panel-title {
            font-size: 0.9rem; font-weight: 600; color: #f472b6;
        }
        .crash-panel-toggle {
            background: rgba(244,114,182,0.1);
            color: #f472b6;
            border: 1px solid rgba(244,114,182,0.2);
            border-radius: 6px;
            padding: 3px 12px;
            font-size: 0.72rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        .crash-panel-toggle:hover {
            background: rgba(244,114,182,0.2);
        }
        .crash-event-list { max-height: 500px; overflow-y: auto; }
        .crash-event-list::-webkit-scrollbar { width: 4px; }
        .crash-event-list::-webkit-scrollbar-track { background: transparent; }
        .crash-event-list::-webkit-scrollbar-thumb {
            background: rgba(244,114,182,0.2);
            border-radius: 2px;
        }
        .crash-event-item {
            background: rgba(10,14,26,0.4);
            border: 1px solid rgba(244,114,182,0.08);
            border-radius: 8px;
            margin-bottom: 4px;
            overflow: hidden;
            transition: all 0.2s;
        }
        .crash-event-summary {
            display: flex; gap: 1rem; align-items: center;
            padding: 6px 12px;
            cursor: pointer;
            transition: background 0.2s;
            font-size: 0.82rem;
        }
        .crash-event-summary:hover {
            background: rgba(244,114,182,0.06);
        }
        .crash-event-expand {
            color: #64748b; font-size: 0.7rem; width: 1rem;
        }
        .crash-event-time {
            color: #94a3b8; font-size: 0.75rem; min-width: 140px;
            font-family: 'JetBrains Mono', monospace;
        }
        .crash-event-pid {
            color: #64748b; font-size: 0.75rem; min-width: 70px;
        }
        .crash-event-reason {
            color: #f472b6; font-size: 0.8rem; flex: 1;
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .crash-event-detail {
            padding: 8px 12px 12px;
            border-top: 1px solid rgba(244,114,182,0.06);
        }
        .crash-detail-actions { margin-bottom: 6px; }
        .crash-log-btn {
            background: rgba(56,189,248,0.1);
            color: #38bdf8;
            border: 1px solid rgba(56,189,248,0.2);
            border-radius: 6px;
            padding: 3px 12px;
            font-size: 0.72rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        .crash-log-btn:hover {
            background: rgba(56,189,248,0.2);
        }
        .crash-log-preview pre {
            margin: 0;
        }

        /* 新崩溃闪烁 */
        @keyframes crash-flash {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; box-shadow: 0 0 20px rgba(244,114,182,0.3); }
        }
        .crash-event-item:first-child .crash-event-summary {
            animation: crash-flash 1s ease-in-out 3;
        }
'''

# Find the last </style> tag and insert crash CSS before it
idx = content.rfind('</style>')
if idx > 0:
    content = content[:idx] + crash_css + '\n    ' + content[idx:]
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK: crash CSS inserted')
else:
    print('ERROR: </style> not found')
