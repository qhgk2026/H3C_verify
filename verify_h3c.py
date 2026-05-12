#!/usr/bin/env python3
"""
H3C 交换机（Comware V5）批量登录凭据验证工具
===============================================
功能：批量验证 H3C V5 交换机的 SSH / Telnet 登录用户名密码是否可用
用法：python3 verify_h3c.py -f switches.csv [-t 10] [-o result.csv]
输入：CSV 文件，格式：ip,username,password,protocol,port
输出：控制台表格 + CSV 结果文件
"""

import csv
import sys
import time
import socket
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# ---------- 尝试导入 paramiko ----------
try:
    import paramiko
    PARAMIKO_OK = True
except ImportError:
    PARAMIKO_OK = False
    print("[警告] paramiko 未安装，SSH 验证不可用。请执行: pip3 install paramiko")

# ---------- 尝试导入 telnetlib ----------
try:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import telnetlib
    TELNET_OK = True
except ImportError:
    TELNET_OK = False
    print("[警告] telnetlib 不可用（Python 3.12+ 已移除），Telnet 验证不可用。")


# ============================================================
#  核心验证函数
# ============================================================

def verify_ssh(ip, username, password, port=22, timeout=10):
    """
    通过 SSH 验证 H3C 交换机登录凭据
    成功登录后执行 'display version' 确认是 H3C 设备，然后退出
    """
    if not PARAMIKO_OK:
        return "SKIP", "paramiko 未安装"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=ip,
            port=int(port),
            username=username,
            password=password,
            timeout=timeout,
            allow_agent=False,
            look_for_keys=False,
            banner_timeout=timeout,
        )
        # 登录成功，执行一条命令确认设备可达
        stdin, stdout, stderr = client.exec_command("display version", timeout=timeout)
        output = stdout.read().decode("utf-8", errors="replace").strip()
        # H3C V5 的 display version 输出通常包含 "H3C" 或 "Comware"
        is_h3c = ("H3C" in output) or ("Comware" in output) or ("h3c" in output.lower())
        if is_h3c:
            return "OK", "SSH 登录成功，已确认 H3C 设备"
        else:
            return "OK", f"SSH 登录成功（非典型 H3C 输出）"
    except paramiko.AuthenticationException:
        return "FAIL", "认证失败（用户名或密码错误）"
    except paramiko.SSHException as e:
        # 有时 H3C V5 不支持 exec_command（仅支持 shell），尝试 invoke_shell
        if "No existing session" in str(e) or "channel" in str(e).lower():
            # 用 invoke_shell 方式再试
            try:
                transport = client.get_transport()
                if transport and transport.is_active():
                    shell = transport.open_session()
                    shell.get_pty()
                    shell.invoke_shell()
                    time.sleep(1)
                    shell.send("display version\n")
                    time.sleep(2)
                    output = shell.recv(4096).decode("utf-8", errors="replace")
                    shell.send("quit\n")
                    return "OK", "SSH 登录成功（shell 模式）"
                else:
                    return "FAIL", f"SSH 异常: {e}"
            except Exception as e2:
                return "FAIL", f"SSH shell 模式也失败: {e2}"
        return "FAIL", f"SSH 异常: {e}"
    except socket.timeout:
        return "FAIL", "连接超时"
    except socket.error as e:
        return "FAIL", f"网络错误: {e}"
    except Exception as e:
        return "FAIL", f"未知错误: {type(e).__name__}: {e}"
    finally:
        client.close()


def verify_telnet(ip, username, password, port=23, timeout=10):
    """
    通过 Telnet 验证 H3C 交换机登录凭据
    H3C V5 的 Telnet 登录流程：
      1. 等待 "Username:" 提示 → 输入用户名
      2. 等待 "Password:" 提示 → 输入密码
      3. 看到 ">" 或 "]" 提示符表示登录成功
    """
    if not TELNET_OK:
        return "SKIP", "telnetlib 不可用"

    tn = None
    try:
        tn = telnetlib.Telnet(ip, int(port), timeout=timeout)

        # 等待用户名提示（H3C 可能输出 "Username:" 或 "Login:"）
        idx, match, text = tn.expect(
            [b"Username:", b"username:", b"Login:", b"login:"],
            timeout=timeout
        )
        if idx == -1:
            return "FAIL", f"未收到用户名提示，原始输出: {text[:200]}"

        tn.write(username.encode("ascii") + b"\n")

        # 等待密码提示
        idx, match, text = tn.expect(
            [b"Password:", b"password:"],
            timeout=timeout
        )
        if idx == -1:
            return "FAIL", f"未收到密码提示，原始输出: {text[:200]}"

        tn.write(password.encode("ascii") + b"\n")

        # 等待命令行提示符（H3C 的提示符通常是 <设备名> 或 [设备名]）
        time.sleep(2)
        idx, match, text = tn.expect(
            [rb"<[^>]+>", rb"\[[^\]]+\]", rb"Login invalid", rb"Login failed",
             rb"Authentication fail", rb"Password:", rb"Username:"],
            timeout=timeout
        )

        output_text = text.decode("utf-8", errors="replace")

        if idx in (4, 5, 6):
            # 收到认证失败或再次要求输入密码/用户名
            return "FAIL", f"认证失败（用户名或密码错误），输出: {output_text[:200]}"
        elif idx in (0, 1):
            # 看到了 <xxx> 或 [xxx] 提示符 → 登录成功
            return "OK", "Telnet 登录成功"
        else:
            # 其他输出，尝试进一步判断
            if "<" in output_text and ">" in output_text:
                return "OK", "Telnet 登录成功"
            return "UNKNOWN", f"无法确定登录状态，输出: {output_text[:200]}"

    except socket.timeout:
        return "FAIL", "连接超时"
    except ConnectionRefusedError:
        return "FAIL", "连接被拒绝（Telnet 服务未启用）"
    except socket.error as e:
        return "FAIL", f"网络错误: {e}"
    except Exception as e:
        return "FAIL", f"未知错误: {type(e).__name__}: {e}"
    finally:
        if tn:
            try:
                tn.close()
            except:
                pass


def verify_switch(ip, username, password, protocol="ssh", port=None, timeout=10):
    """
    验证单台交换机的登录凭据
    返回: (ip, username, protocol, status, message, elapsed_seconds)
    """
    if port is None:
        port = 22 if protocol.lower() == "ssh" else 23

    start = time.time()
    if protocol.lower() == "ssh":
        status, msg = verify_ssh(ip, username, password, int(port), timeout)
    elif protocol.lower() == "telnet":
        status, msg = verify_telnet(ip, username, password, int(port), timeout)
    else:
        status, msg = "SKIP", f"不支持的协议: {protocol}"
    elapsed = round(time.time() - start, 2)

    return (ip, username, protocol, status, msg, elapsed)


# ============================================================
#  CSV 读取
# ============================================================

def load_switches(filepath):
    """
    读取 CSV 文件，返回列表
    CSV 格式：ip,username,password,protocol,port
    protocol 和 port 列可选，默认 ssh / 22
    """
    switches = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ip = row.get("ip", "").strip()
            username = row.get("username", "").strip()
            password = row.get("password", "").strip()
            protocol = row.get("protocol", "ssh").strip()
            port = row.get("port", "").strip()
            if not ip or not username or not password:
                print(f"[跳过] 数据不完整: {row}")
                continue
            switches.append({
                "ip": ip,
                "username": username,
                "password": password,
                "protocol": protocol if protocol else "ssh",
                "port": port if port else None,
            })
    return switches


# ============================================================
#  主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="H3C V5 交换机批量登录凭据验证工具"
    )
    parser.add_argument(
        "-f", "--file", required=True,
        help="CSV 文件路径，格式: ip,username,password,protocol,port"
    )
    parser.add_argument(
        "-t", "--timeout", type=int, default=10,
        help="单台设备连接超时秒数（默认 10）"
    )
    parser.add_argument(
        "-w", "--workers", type=int, default=5,
        help="并发线程数（默认 5，建议不超过 20）"
    )
    parser.add_argument(
        "-o", "--output", default="",
        help="结果输出 CSV 路径（默认自动生成）"
    )
    args = parser.parse_args()

    # 读取设备列表
    switches = load_switches(args.file)
    if not switches:
        print("[错误] 未读取到有效设备数据，请检查 CSV 文件格式")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  H3C V5 交换机批量凭据验证")
    print(f"  设备数量: {len(switches)} | 超时: {args.timeout}s | 并发: {args.workers}")
    print(f"  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    results = []
    completed = 0

    # 多线程并发验证
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for sw in switches:
            future = executor.submit(
                verify_switch,
                sw["ip"], sw["username"], sw["password"],
                sw["protocol"], sw["port"], args.timeout
            )
            futures[future] = sw

        for future in as_completed(futures):
            completed += 1
            ip, username, protocol, status, msg, elapsed = future.result()

            # 状态图标
            icon = {
                "OK": "✅",
                "FAIL": "❌",
                "SKIP": "⏭️",
                "UNKNOWN": "❓",
            }.get(status, "❓")

            # 实时输出
            print(
                f"  [{completed}/{len(switches)}] {icon} {ip:15s} | "
                f"{username:10s} | {protocol:6s} | {status:7s} | "
                f"{elapsed:5.1f}s | {msg}"
            )

            results.append({
                "ip": ip,
                "username": username,
                "protocol": protocol,
                "status": status,
                "message": msg,
                "elapsed": elapsed,
            })

    # ---------- 统计汇总 ----------
    ok_count = sum(1 for r in results if r["status"] == "OK")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    skip_count = sum(1 for r in results if r["status"] == "SKIP")
    unknown_count = sum(1 for r in results if r["status"] == "UNKNOWN")

    print(f"\n{'='*60}")
    print(f"  验证完成")
    print(f"  ✅ 成功: {ok_count}  ❌ 失败: {fail_count}  "
          f"⏭️ 跳过: {skip_count}  ❓ 未知: {unknown_count}")
    print(f"  结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # ---------- 输出 CSV ----------
    output_path = args.output
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"verify_result_{timestamp}.csv"

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["ip", "username", "protocol", "status", "message", "elapsed"])
        writer.writeheader()
        writer.writerows(results)

    print(f"  结果已保存至: {output_path}")

    # 如果有失败的，列出失败设备清单
    if fail_count > 0:
        print(f"\n  --- 失败设备清单 ---")
        for r in results:
            if r["status"] == "FAIL":
                print(f"    {r['ip']:15s} | {r['username']:10s} | {r['message']}")
        print()

    # 返回退出码：全部成功返回0，有失败返回1
    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()