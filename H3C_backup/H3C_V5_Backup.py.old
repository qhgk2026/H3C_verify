#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
H3C Comware V5 交换机批量配置备份工具
支持 SSH/Telnet 连接，图形化操作界面
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import threading
import os
import sys
import datetime
import json
import re
import socket
import time

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

try:
    import telnetlib
    HAS_TELNET = True
except ImportError:
    HAS_TELNET = True  # Python 3.12+ may not have telnetlib


# ============================================================
# H3C V5 交互引擎
# ============================================================

class H3CV5Connector:
    """H3C Comware V5 交换机连接器"""

    # V5 常见提示符
    PROMPTS = [
        rb'[>\]]\s*$',           # > 或 ]
        rb'[>\]]$',              # 末尾
        rb'<[^>]+>',             # <Sysname>
        rb'\[[^\]]+\]',          # [Sysname]
    ]

    def __init__(self, host, port, username, password, enable_password=None,
                 protocol='ssh', timeout=15, log_callback=None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.enable_password = enable_password
        self.protocol = protocol
        self.timeout = timeout
        self.log = log_callback or (lambda msg: None)
        self.client = None
        self.channel = None

    def connect_ssh(self):
        """SSH 方式连接"""
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            hostname=self.host,
            port=self.port or 22,
            username=self.username,
            password=self.password,
            timeout=self.timeout,
            allow_agent=False,
            look_for_keys=False,
            banner_timeout=30,
        )
        self.channel = self.client.invoke_shell(width=200, height=5000)
        self.channel.settimeout(self.timeout)
        # 等待初始提示符
        self._read_until_prompt()
        # 关闭分屏
        self._send_command('screen-length disable')
        self._read_until_prompt()

    def connect_telnet(self):
        """Telnet 方式连接"""
        port = self.port or 23
        self.channel = telnetlib.Telnet(self.host, port, timeout=self.timeout)
        # 等待用户名提示
        self.channel.read_until(b'Username:', timeout=self.timeout)
        self.channel.write(self.username.encode() + b'\n')
        # 等待密码提示
        self.channel.read_until(b'Password:', timeout=self.timeout)
        self.channel.write(self.password.encode() + b'\n')
        # 等待提示符
        self._read_until_prompt()
        # 关闭分屏
        self._send_command('screen-length disable')
        self._read_until_prompt()

    def connect(self):
        """建立连接"""
        self.log(f"正在连接 {self.host} ({self.protocol})...")
        try:
            if self.protocol == 'ssh':
                self.connect_ssh()
            else:
                self.connect_telnet()
            self.log(f"✓ {self.host} 连接成功")
            return True
        except Exception as e:
            self.log(f"✗ {self.host} 连接失败: {e}")
            return False

    def _read_until_prompt(self, wait=0.5):
        """读取直到出现提示符"""
        import time
        buf = b''
        start = time.time()
        while time.time() - start < self.timeout:
            try:
                if self.protocol == 'ssh' and self.channel:
                    data = self.channel.recv(4096)
                elif self.protocol == 'telnet' and self.channel:
                    data = self.channel.read_very_eager()
                else:
                    break
                if not data:
                    break
                buf += data
                # 检查是否匹配提示符
                text = buf.decode('utf-8', errors='replace').strip()
                for pat in self.PROMPTS:
                    if re.search(pat, buf[-50:]):
                        return buf.decode('utf-8', errors='replace')
                time.sleep(0.1)
            except socket.timeout:
                break
            except Exception:
                time.sleep(0.1)
        return buf.decode('utf-8', errors='replace')

    def _send_command(self, cmd):
        """发送命令"""
        if self.protocol == 'ssh' and self.channel:
            self.channel.sendall(cmd.encode() + b'\n')
        elif self.protocol == 'telnet' and self.channel:
            self.channel.write(cmd.encode() + b'\n')

    def get_config(self):
        """获取当前配置"""
        # 先关闭分屏，避免 --More-- 问题
        self._send_command('screen-length disable')
        time.sleep(0.5)
        self._read_until_prompt()  # 读取 screen-length disable 的回显
        time.sleep(0.3)
        # 再执行获取配置命令
        self._send_command('display current-configuration')
        output = self._read_long_output()
        # 恢复分屏
        self._send_command('screen-length enable')
        time.sleep(0.3)
        self._read_until_prompt()
        return output

    def _read_long_output(self):
        """读取长输出（自动处理分屏 --- More --- 提示）"""
        import time
        buf = b''
        start = time.time()
        idle_time = 0
        got_data = False  # 是否已收到数据

        while True:
            try:
                if self.protocol == 'ssh' and self.channel:
                    if self.channel.recv_ready():
                        data = self.channel.recv(4096)
                        if data:
                            idle_time = 0
                            got_data = True
                        else:
                            data = b''
                            idle_time += 0.1
                    else:
                        data = b''
                        idle_time += 0.1
                elif self.protocol == 'telnet' and self.channel:
                    try:
                        data = self.channel.read_very_eager()
                        if data:
                            idle_time = 0
                            got_data = True
                        else:
                            idle_time += 0.1
                    except EOFError:
                        break
                else:
                    break

                time.sleep(0.1)

                # 等待数据时的超时策略
                if not got_data and idle_time > 10:
                    # 还没收到任何数据，等久一点
                    self.log(f"  ⚠ {self.host} 等待响应超时(10s)")
                    break
                if got_data and idle_time > 5:
                    # 已收到数据但停了5秒，认为输出结束
                    break

                if not data:
                    continue

                buf += data
                text = buf.decode('utf-8', errors='replace')

                # 处理 More 提示 - 发送空格继续
                if '---- More ----' in text or '----More----' in text or '--More--' in text:
                    time.sleep(0.3)
                    self._send_command(' ')
                    # 清除已处理的 More 标记
                    buf = buf.replace(b'---- More ----', b'').replace(b'----More----', b'').replace(b'--More--', b'')
                    idle_time = 0
                    continue

                # 检查是否回到提示符（输出结束标志）
                last_chunk = text[-200:]  # 只看最近的内容
                for pat in self.PROMPTS:
                    pat_str = pat.decode() if isinstance(pat, bytes) else pat
                    if re.search(pat_str, last_chunk):
                        # 已回到提示符，输出结束
                        time.sleep(0.3)
                        result = buf.decode('utf-8', errors='replace')
                        return self._clean_output(result)

                if time.time() - start > 120:  # 2分钟总超时
                    self.log(f"  ⚠ {self.host} 读取超时，返回已获取内容")
                    break

            except socket.timeout:
                break
            except Exception as e:
                self.log(f"  ⚠ 读取异常: {e}")
                break

        result = buf.decode('utf-8', errors='replace')
        return self._clean_output(result)

    def _clean_output(self, text):
        """清理输出内容，移除控制字符和提示符"""
        # 移除 ANSI 转义序列
        text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
        # 移除退格符
        text = re.sub(r'[\x08]', '', text)
        # 移除回车
        text = text.replace('\r\n', '\n').replace('\r', '')
        # 移除命令回显
        lines = text.split('\n')
        cleaned = []
        for line in lines:
            # 跳过命令回显行
            if 'display current-configuration' in line:
                continue
            if 'screen-length disable' in line:
                continue
            if 'screen-length enable' in line:
                continue
            # 移除提示符行 (如 <Sysname> 或 [Sysname])
            if re.match(r'^<[A-Za-z0-9\-_]+>\s*$', line.strip()):
                continue
            if re.match(r'^\[[A-Za-z0-9\-_/]+\]\s*$', line.strip()):
                continue
            # 移除 More 分页提示
            if '---- More ----' in line or '----More----' in line or '--More--' in line:
                continue
            cleaned.append(line)
        result = '\n'.join(cleaned).strip()
        # 截取配置正文（从 # 号开始）
        cfg_start = result.find('#')
        if cfg_start > 0:
            result = result[cfg_start:]
        return result.strip()

    def get_device_info(self):
        """获取设备基本信息"""
        info = {}
        # 获取设备名称
        self._send_command('display device')
        output = self._read_long_output()
        info['device_info'] = output.strip()
        return info

    def disconnect(self):
        """断开连接"""
        try:
            if self.channel:
                self._send_command('quit')
        except:
            pass
        try:
            if self.client:
                self.client.close()
        except:
            pass
        self.client = None
        self.channel = None


# ============================================================
# 设备列表管理
# ============================================================

class DeviceManager:
    """管理设备列表"""

    def __init__(self):
        self.devices = []  # [{host, port, protocol, username, password, enable_password, description}]

    def add_device(self, host, port, protocol, username, password,
                   enable_password='', description=''):
        self.devices.append({
            'host': host,
            'port': port,
            'protocol': protocol,
            'username': username,
            'password': password,
            'enable_password': enable_password,
            'description': description,
        })

    def load_from_file(self, filepath):
        """从文件加载设备列表
        支持格式:
        1. CSV: host,username,password,protocol,port,description
        2. JSON: [{host, username, password, ...}]
        3. TXT: 每行一个IP (使用默认凭据)
        """
        self.devices = []
        ext = os.path.splitext(filepath)[1].lower()

        if ext == '.json':
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    self.devices.append({
                        'host': item.get('host', ''),
                        'port': item.get('port', 22 if item.get('protocol', 'ssh') == 'ssh' else 23),
                        'protocol': item.get('protocol', 'ssh'),
                        'username': item.get('username', ''),
                        'password': item.get('password', ''),
                        'enable_password': item.get('enable_password', ''),
                        'description': item.get('description', ''),
                    })
        elif ext == '.csv':
            import csv
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row or row[0].startswith('#'):
                        continue
                    host = row[0].strip()
                    if not host or host == 'host':
                        continue
                    self.devices.append({
                        'host': host,
                        'username': row[1].strip() if len(row) > 1 else '',
                        'password': row[2].strip() if len(row) > 2 else '',
                        'protocol': row[3].strip().lower() if len(row) > 3 else 'ssh',
                        'port': int(row[4].strip()) if len(row) > 4 and row[4].strip().isdigit() else 0,
                        'enable_password': row[5].strip() if len(row) > 5 else '',
                        'description': row[6].strip() if len(row) > 6 else '',
                    })
        else:  # txt
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    # 支持 host:port 或 host,user,pass 格式
                    parts = line.split(',')
                    host_port = parts[0].strip()
                    if ':' in host_port:
                        host, port = host_port.rsplit(':', 1)
                        port = int(port)
                    else:
                        host = host_port
                        port = 0
                    self.devices.append({
                        'host': host,
                        'port': port,
                        'username': parts[1].strip() if len(parts) > 1 else '',
                        'password': parts[2].strip() if len(parts) > 2 else '',
                        'protocol': 'ssh',
                        'enable_password': parts[3].strip() if len(parts) > 3 else '',
                        'description': parts[4].strip() if len(parts) > 4 else '',
                    })

    def save_to_file(self, filepath):
        """保存设备列表到文件"""
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.json':
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.devices, f, ensure_ascii=False, indent=2)
        elif ext == '.csv':
            import csv
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['host', 'username', 'password', 'protocol', 'port', 'enable_password', 'description'])
                for d in self.devices:
                    writer.writerow([d['host'], d['username'], d['password'],
                                    d['protocol'], d['port'], d['enable_password'], d['description']])
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                for d in self.devices:
                    f.write(f"{d['host']},{d['username']},{d['password']},{d['protocol']}\n")


# ============================================================
# 主界面
# ============================================================

class H3CBackupApp:
    """H3C V5 批量备份工具主界面"""

    def __init__(self, root):
        self.root = root
        self.root.title("H3C V5 交换机批量配置备份工具QHGK-2025-05-19")
        self.root.geometry("960x720")
        self.root.minsize(800, 600)

        self.device_mgr = DeviceManager()
        self.running = False
        self.stop_flag = False
        self.backup_results = []  # [{host, status, file, error}]

        self._build_ui()
        self._center_window()

    def _center_window(self):
        """窗口居中"""
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f'+{x}+{y}')

    def _build_ui(self):
        """构建界面"""
        style = ttk.Style()
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 14, 'bold'))
        style.configure('Section.TLabelframe.Label', font=('Microsoft YaHei UI', 10, 'bold'))
        style.configure('Run.TButton', font=('Microsoft YaHei UI', 11, 'bold'))

        # 主容器
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_frame = ttk.Frame(main)
        title_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(title_frame, text="🖥 H3C Comware V5 批量配置备份-ZM20260519", style='Title.TLabel').pack(side=tk.LEFT)
        ttk.Label(title_frame, text="支持 SSH / Telnet 连接", foreground='gray').pack(side=tk.RIGHT, padx=10)

        # ===== 连接设置区 =====
        conn_frame = ttk.LabelFrame(main, text="连接设置", style='Section.TLabelframe', padding=8)
        conn_frame.pack(fill=tk.X, pady=(0, 6))

        # 第一行: 协议 + 凭据
        row1 = ttk.Frame(conn_frame)
        row1.pack(fill=tk.X, pady=2)

        ttk.Label(row1, text="默认协议:").pack(side=tk.LEFT, padx=(0, 4))
        self.protocol_var = tk.StringVar(value='ssh')
        ttk.Radiobutton(row1, text="SSH", variable=self.protocol_var, value='ssh').pack(side=tk.LEFT)
        ttk.Radiobutton(row1, text="Telnet", variable=self.protocol_var, value='telnet').pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(row1, text="用户名:").pack(side=tk.LEFT, padx=(0, 4))
        self.username_var = tk.StringVar(value='admin')
        ttk.Entry(row1, textvariable=self.username_var, width=14).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(row1, text="密码:").pack(side=tk.LEFT, padx=(0, 4))
        self.password_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.password_var, width=16, show='●').pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(row1, text="Enable密码:").pack(side=tk.LEFT, padx=(0, 4))
        self.enable_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.enable_var, width=12, show='●').pack(side=tk.LEFT)

        # 第二行: 端口 + 超时
        row2 = ttk.Frame(conn_frame)
        row2.pack(fill=tk.X, pady=2)

        ttk.Label(row2, text="SSH端口:").pack(side=tk.LEFT, padx=(0, 4))
        self.ssh_port_var = tk.IntVar(value=22)
        ttk.Spinbox(row2, from_=1, to=65535, textvariable=self.ssh_port_var, width=6).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(row2, text="Telnet端口:").pack(side=tk.LEFT, padx=(0, 4))
        self.telnet_port_var = tk.IntVar(value=23)
        ttk.Spinbox(row2, from_=1, to=65535, textvariable=self.telnet_port_var, width=6).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(row2, text="超时(秒):").pack(side=tk.LEFT, padx=(0, 4))
        self.timeout_var = tk.IntVar(value=15)
        ttk.Spinbox(row2, from_=5, to=120, textvariable=self.timeout_var, width=6).pack(side=tk.LEFT)

        # ===== 设备列表区 =====
        dev_frame = ttk.LabelFrame(main, text="设备列表", style='Section.TLabelframe', padding=8)
        dev_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        # 工具栏
        toolbar = ttk.Frame(dev_frame)
        toolbar.pack(fill=tk.X, pady=(0, 4))

        ttk.Button(toolbar, text="📁 导入设备", command=self._import_devices).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="💾 导出设备", command=self._export_devices).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Button(toolbar, text="➕ 添加", command=self._add_device).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="✏ 编辑", command=self._edit_device).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🗑 删除", command=self._delete_device).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Button(toolbar, text="🔍 测试选中", command=self._test_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="清空列表", command=self._clear_devices).pack(side=tk.LEFT, padx=2)

        # 手动添加行
        add_row = ttk.Frame(dev_frame)
        add_row.pack(fill=tk.X, pady=(4, 4))

        ttk.Label(add_row, text="IP:").pack(side=tk.LEFT, padx=(0, 2))
        self.quick_ip_var = tk.StringVar()
        ttk.Entry(add_row, textvariable=self.quick_ip_var, width=18).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Label(add_row, text="描述:").pack(side=tk.LEFT, padx=(0, 2))
        self.quick_desc_var = tk.StringVar()
        ttk.Entry(add_row, textvariable=self.quick_desc_var, width=20).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(add_row, text="快速添加", command=self._quick_add).pack(side=tk.LEFT)

        # 设备列表 Treeview
        tree_frame = ttk.Frame(dev_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ('host', 'protocol', 'port', 'username', 'description', 'status')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=6)
        self.tree.heading('host', text='IP 地址')
        self.tree.heading('protocol', text='协议')
        self.tree.heading('port', text='端口')
        self.tree.heading('username', text='用户名')
        self.tree.heading('description', text='描述')
        self.tree.heading('status', text='状态')
        self.tree.column('host', width=150)
        self.tree.column('protocol', width=60)
        self.tree.column('port', width=60)
        self.tree.column('username', width=80)
        self.tree.column('description', width=200)
        self.tree.column('status', width=100)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ===== 备份设置区 =====
        bk_frame = ttk.LabelFrame(main, text="备份设置", style='Section.TLabelframe', padding=8)
        bk_frame.pack(fill=tk.X, pady=(0, 6))

        bk_row = ttk.Frame(bk_frame)
        bk_row.pack(fill=tk.X)

        ttk.Label(bk_row, text="备份目录:").pack(side=tk.LEFT, padx=(0, 4))
        self.backup_dir_var = tk.StringVar(value=os.path.join(os.path.expanduser('~'), 'Desktop', 'H3C_Backup'))
        ttk.Entry(bk_row, textvariable=self.backup_dir_var, width=45).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bk_row, text="浏览", command=self._browse_dir).pack(side=tk.LEFT, padx=(0, 16))

        self.auto_date_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bk_row, text="按日期建子目录", variable=self.auto_date_var).pack(side=tk.LEFT, padx=(0, 12))

        self.auto_hostname_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bk_row, text="文件名含设备名", variable=self.auto_hostname_var).pack(side=tk.LEFT)

        # ===== 操作按钮区 =====
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(4, 4))

        self.run_btn = ttk.Button(btn_frame, text="▶ 开始备份", style='Run.TButton', command=self._start_backup)
        self.run_btn.pack(side=tk.LEFT, padx=4, ipadx=16, ipady=4)

        self.stop_btn = ttk.Button(btn_frame, text="⏹ 停止", command=self._stop_backup, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=4, ipadx=10, ipady=4)

        # 进度条
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(btn_frame, variable=self.progress_var, maximum=100, length=300)
        self.progress.pack(side=tk.LEFT, padx=16, fill=tk.X, expand=True)

        self.status_label = ttk.Label(btn_frame, text="就绪")
        self.status_label.pack(side=tk.RIGHT, padx=4)

        # ===== 日志区 =====
        log_frame = ttk.LabelFrame(main, text="运行日志", style='Section.TLabelframe', padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 0))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=tk.WORD,
                                                   font=('Consolas', 9), bg='#1e1e2e', fg='#cdd6f4',
                                                   insertbackground='white')
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 日志工具栏
        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(log_toolbar, text="复制日志", command=self._copy_log).pack(side=tk.LEFT, padx=2)
        ttk.Button(log_toolbar, text="清空日志", command=self._clear_log).pack(side=tk.LEFT, padx=2)

    # ===== 日志 =====

    def log(self, msg, tag=None):
        """输出日志"""
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        self.log_text.insert(tk.END, f"[{timestamp}] {msg}\n")
        self.log_text.see(tk.END)

    def _copy_log(self):
        content = self.log_text.get('1.0', tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(content)

    def _clear_log(self):
        self.log_text.delete('1.0', tk.END)

    # ===== 设备管理 =====

    def _refresh_tree(self):
        """刷新设备列表"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, dev in enumerate(self.device_mgr.devices):
            self.tree.insert('', tk.END, iid=str(i), values=(
                dev['host'],
                dev.get('protocol', 'ssh'),
                dev.get('port', ''),
                dev.get('username', ''),
                dev.get('description', ''),
                dev.get('status', '待备份'),
            ))

    def _import_devices(self):
        """导入设备列表"""
        filepath = filedialog.askopenfilename(
            title="导入设备列表",
            filetypes=[("所有支持格式", "*.csv *.json *.txt"),
                       ("CSV 文件", "*.csv"), ("JSON 文件", "*.json"), ("文本文件", "*.txt")]
        )
        if not filepath:
            return
        try:
            self.device_mgr.load_from_file(filepath)
            # 补充默认凭据
            for dev in self.device_mgr.devices:
                if not dev.get('username'):
                    dev['username'] = self.username_var.get()
                if not dev.get('password'):
                    dev['password'] = self.password_var.get()
                if not dev.get('protocol'):
                    dev['protocol'] = self.protocol_var.get()
                if not dev.get('port'):
                    dev['port'] = self.ssh_port_var.get() if dev['protocol'] == 'ssh' else self.telnet_port_var.get()
                dev['status'] = '待备份'
            self._refresh_tree()
            self.log(f"✓ 已导入 {len(self.device_mgr.devices)} 台设备")
        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    def _export_devices(self):
        filepath = filedialog.asksaveasfilename(
            title="导出设备列表",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("JSON 文件", "*.json")]
        )
        if not filepath:
            return
        try:
            self.device_mgr.save_to_file(filepath)
            self.log(f"✓ 设备列表已导出到 {filepath}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _add_device(self):
        """添加设备对话框"""
        dlg = tk.Toplevel(self.root)
        dlg.title("添加设备")
        dlg.geometry("400x300")
        dlg.transient(self.root)
        dlg.grab_set()

        fields = {}
        for i, (label, default) in enumerate([
            ('IP 地址', ''),
            ('协议 (ssh/telnet)', self.protocol_var.get()),
            ('端口', str(self.ssh_port_var.get())),
            ('用户名', self.username_var.get()),
            ('密码', ''),
            ('Enable 密码', ''),
            ('描述', ''),
        ]):
            ttk.Label(dlg, text=label + ":").grid(row=i, column=0, padx=10, pady=4, sticky=tk.W)
            var = tk.StringVar(value=default)
            entry = ttk.Entry(dlg, textvariable=var, width=30)
            if '密码' in label:
                entry.configure(show='●')
            entry.grid(row=i, column=1, padx=10, pady=4)
            fields[label] = var

        def on_ok():
            host = fields['IP 地址'].get().strip()
            if not host:
                messagebox.showwarning("提示", "请输入 IP 地址")
                return
            protocol = fields['协议 (ssh/telnet)'].get().strip().lower()
            port = int(fields['端口'].get()) if fields['端口'].get().isdigit() else 0
            self.device_mgr.add_device(
                host=host,
                port=port,
                protocol=protocol,
                username=fields['用户名'].get().strip() or self.username_var.get(),
                password=fields['密码'].get().strip() or self.password_var.get(),
                enable_password=fields['Enable 密码'].get().strip(),
                description=fields['描述'].get().strip(),
            )
            self.device_mgr.devices[-1]['status'] = '待备份'
            self._refresh_tree()
            dlg.destroy()
            self.log(f"✓ 已添加设备 {host}")

        ttk.Button(dlg, text="确定", command=on_ok).grid(row=7, column=0, columnspan=2, pady=16)

    def _edit_device(self):
        """编辑选中设备"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中设备")
            return
        idx = int(sel[0])
        dev = self.device_mgr.devices[idx]
        self._add_device()  # TODO: 简化实现，预填数据

    def _delete_device(self):
        sel = self.tree.selection()
        if not sel:
            return
        if messagebox.askyesno("确认", "确定删除选中的设备？"):
            for item in reversed(sel):
                idx = int(item)
                del self.device_mgr.devices[idx]
            self._refresh_tree()

    def _test_selected(self):
        """测试选中设备的连通性"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中设备")
            return
        idx = int(sel[0])
        dev = self.device_mgr.devices[idx]

        def test():
            self.log(f"🔍 测试 {dev['host']} 连通性...")
            conn = H3CV5Connector(
                host=dev['host'], port=dev.get('port', 22),
                username=dev.get('username', ''),
                password=dev.get('password', ''),
                protocol=dev.get('protocol', 'ssh'),
                timeout=self.timeout_var.get(),
                log_callback=self.log,
            )
            try:
                if conn.connect():
                    self.log(f"✅ {dev['host']} 连接测试成功")
                    dev['status'] = '可连接'
                else:
                    dev['status'] = '连接失败'
            except Exception as e:
                self.log(f"❌ {dev['host']} 连接失败: {e}")
                dev['status'] = '连接失败'
            finally:
                conn.disconnect()
            self._refresh_tree()

        threading.Thread(target=test, daemon=True).start()

    def _clear_devices(self):
        if messagebox.askyesno("确认", "清空所有设备？"):
            self.device_mgr.devices = []
            self._refresh_tree()

    def _quick_add(self):
        """快速添加设备"""
        ip = self.quick_ip_var.get().strip()
        if not ip:
            return
        # 支持多个IP，用空格或分号分隔
        ips = re.split(r'[;，,\s]+', ip)
        count = 0
        for addr in ips:
            addr = addr.strip()
            if not addr:
                continue
            # 支持网段展开: 192.168.1.1-10
            if '-' in addr and addr.count('.') == 3:
                base, range_part = addr.rsplit('.', 1)
                if '-' in range_part:
                    start, end = range_part.split('-', 1)
                    try:
                        for n in range(int(start), int(end) + 1):
                            host = f"{base}.{n}"
                            self.device_mgr.add_device(
                                host=host,
                                port=self.ssh_port_var.get() if self.protocol_var.get() == 'ssh' else self.telnet_port_var.get(),
                                protocol=self.protocol_var.get(),
                                username=self.username_var.get(),
                                password=self.password_var.get(),
                                enable_password=self.enable_var.get(),
                                description=self.quick_desc_var.get(),
                            )
                            self.device_mgr.devices[-1]['status'] = '待备份'
                            count += 1
                    except ValueError:
                        continue
            else:
                self.device_mgr.add_device(
                    host=addr,
                    port=self.ssh_port_var.get() if self.protocol_var.get() == 'ssh' else self.telnet_port_var.get(),
                    protocol=self.protocol_var.get(),
                    username=self.username_var.get(),
                    password=self.password_var.get(),
                    enable_password=self.enable_var.get(),
                    description=self.quick_desc_var.get(),
                )
                self.device_mgr.devices[-1]['status'] = '待备份'
                count += 1

        self._refresh_tree()
        self.quick_ip_var.set('')
        self.quick_desc_var.set('')
        self.log(f"✓ 已快速添加 {count} 台设备")

    def _browse_dir(self):
        dirpath = filedialog.askdirectory(title="选择备份目录")
        if dirpath:
            self.backup_dir_var.set(dirpath)

    # ===== 备份执行 =====

    def _start_backup(self):
        """开始批量备份"""
        if not self.device_mgr.devices:
            messagebox.showwarning("提示", "设备列表为空，请先添加设备")
            return
        if not self.password_var.get() and not any(d.get('password') for d in self.device_mgr.devices):
            messagebox.showwarning("提示", "请输入密码")
            return
        if self.running:
            return

        self.running = True
        self.stop_flag = False
        self.run_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.backup_results = []

        threading.Thread(target=self._backup_worker, daemon=True).start()

    def _stop_backup(self):
        self.stop_flag = True
        self.log("⚠ 正在停止...")

    def _backup_worker(self):
        """备份工作线程"""
        devices = self.device_mgr.devices
        total = len(devices)
        success_count = 0
        fail_count = 0

        # 准备备份目录
        base_dir = self.backup_dir_var.get()
        if self.auto_date_var.get():
            date_str = datetime.datetime.now().strftime('%Y-%m-%d')
            backup_dir = os.path.join(base_dir, date_str)
        else:
            backup_dir = base_dir

        os.makedirs(backup_dir, exist_ok=True)
        self.log(f"📁 备份目录: {backup_dir}")

        for i, dev in enumerate(devices):
            if self.stop_flag:
                self.log("⏹ 已停止备份")
                break

            # 更新进度
            progress = (i / total) * 100
            self.root.after(0, lambda p=progress: self.progress_var.set(p))
            self.root.after(0, lambda i=i, t=total: self.status_label.configure(text=f"备份中 {i+1}/{t}"))

            host = dev['host']
            protocol = dev.get('protocol', self.protocol_var.get())
            port = dev.get('port') or (self.ssh_port_var.get() if protocol == 'ssh' else self.telnet_port_var.get())
            username = dev.get('username') or self.username_var.get()
            password = dev.get('password') or self.password_var.get()
            enable_pwd = dev.get('enable_password') or self.enable_var.get()

            self.log(f"\n{'='*50}")
            self.log(f"📡 [{i+1}/{total}] 备份 {host} ...")

            dev['status'] = '备份中...'
            self.root.after(0, self._refresh_tree)

            conn = H3CV5Connector(
                host=host, port=port,
                username=username, password=password,
                enable_password=enable_pwd,
                protocol=protocol,
                timeout=self.timeout_var.get(),
                log_callback=self.log,
            )

            try:
                if not conn.connect():
                    dev['status'] = '连接失败'
                    fail_count += 1
                    self.backup_results.append({'host': host, 'status': 'fail', 'file': '', 'error': '连接失败'})
                    self.root.after(0, self._refresh_tree)
                    continue

                # 获取配置
                self.log(f"  ⬇ 正在获取配置...")
                config = conn.get_config()

                if not config or len(config) < 20:
                    dev['status'] = '配置为空'
                    fail_count += 1
                    self.backup_results.append({'host': host, 'status': 'fail', 'file': '', 'error': '配置为空'})
                    self.log(f"  ⚠ {host} 获取的配置内容为空或过短")
                    self.root.after(0, self._refresh_tree)
                    continue

                # 尝试从配置中提取设备名
                hostname = host
                name_match = re.search(r'sysname\s+(\S+)', config)
                if name_match:
                    hostname = name_match.group(1)

                # 生成文件名
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                if self.auto_hostname_var.get():
                    filename = f"{hostname}_{host}_{timestamp}.cfg"
                else:
                    filename = f"{host}_{timestamp}.cfg"

                filepath = os.path.join(backup_dir, filename)

                # 写入配置文件
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"# H3C Configuration Backup\n")
                    f.write(f"# Device: {host} ({hostname})\n")
                    f.write(f"# Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"# Protocol: {protocol}\n")
                    f.write(f"{'#'*50}\n\n")
                    f.write(config)

                dev['status'] = '✓ 已备份'
                success_count += 1
                self.backup_results.append({'host': host, 'status': 'success', 'file': filepath, 'error': ''})
                self.log(f"  ✅ {host} 备份成功 → {filename} ({len(config)} 字符)")

            except Exception as e:
                dev['status'] = f'错误: {str(e)[:30]}'
                fail_count += 1
                self.backup_results.append({'host': host, 'status': 'fail', 'file': '', 'error': str(e)})
                self.log(f"  ❌ {host} 备份失败: {e}")
            finally:
                conn.disconnect()

            self.root.after(0, self._refresh_tree)

        # 完成
        self.progress_var.set(100)
        self.running = False
        self.run_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)

        self.log(f"\n{'='*50}")
        self.log(f"📊 备份完成! 成功: {success_count}, 失败: {fail_count}, 总计: {total}")
        self.log(f"📁 备份目录: {backup_dir}")
        self.status_label.configure(text=f"完成 ✓{success_count} ✗{fail_count}")

        # 生成备份报告
        self._save_report(backup_dir)

    def _save_report(self, backup_dir):
        """保存备份报告"""
        report_file = os.path.join(backup_dir, '_backup_report.txt')
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(f"H3C V5 交换机批量配置备份报告\n")
                f.write(f"{'='*60}\n")
                f.write(f"备份时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"备份目录: {backup_dir}\n\n")
                f.write(f"{'IP 地址':<20} {'状态':<12} {'文件'}\n")
                f.write(f"{'-'*20} {'-'*12} {'-'*40}\n")
                for r in self.backup_results:
                    status = '✓ 成功' if r['status'] == 'success' else '✗ 失败'
                    f.write(f"{r['host']:<20} {status:<12} {r['file'] or r['error']}\n")
            self.log(f"📋 备份报告已保存: {report_file}")
        except Exception as e:
            self.log(f"⚠ 保存报告失败: {e}")


# ============================================================
# 入口
# ============================================================

def main():
    if not HAS_PARAMIKO:
        print("错误: 需要安装 paramiko 库")
        print("请运行: pip install paramiko")
        sys.exit(1)

    root = tk.Tk()

    # 设置 DPI 感知 (Windows)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = H3CBackupApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
