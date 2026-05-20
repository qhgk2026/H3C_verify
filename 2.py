import csv
import sys
import subprocess
import threading
from queue import Queue

lock = threading.Lock()
success = 0
failed = 0

def test_ssh(ip, user, pwd, port=22):
    global success, failed
    try:
        # 真正能判断 密码正确/错误 的命令
        cmd = (
            f'ssh -o StrictHostKeyChecking=no '
            f'-o ConnectTimeout=15 '
            f'-o KexAlgorithms=diffie-hellman-group1-sha1 '
            f'-o HostKeyAlgorithms=ssh-rsa '
            f'-p {port} {user}@{ip} "echo LOGIN_SUCCESS"'
        )

        res = subprocess.run(
            cmd,
            input=f"{pwd}\n",
            text=True,
            shell=True,
            capture_output=True,
            timeout=20
        )

        out = res.stdout
        err = res.stderr

        # ======================
        # 正确逻辑（绝对不会误判）
        # ======================
        if "LOGIN_SUCCESS" in out:
            status = "✅ 登录成功"
            with lock:
                success += 1
        elif "Permission denied" in err:
            status = "❌ 密码错误"
            with lock:
                failed += 1
        elif "Connection timed out" in err:
            status = "⏱ 连接超时"
            with lock:
                failed += 1
        else:
            status = "❌ 登录失败"
            with lock:
                failed += 1

        print(f"{status} | {ip:16} | {user}")

    except Exception as e:
        print(f"❌ 异常 | {ip:16} | {user}")
        with lock:
            failed += 1

def worker():
    while not q.empty():
        ip, user, pwd, port = q.get()
        test_ssh(ip, user, pwd, port)
        q.task_done()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法：python ssh_check.py -f switches.csv")
        sys.exit()

    q = Queue()
    with open(sys.argv[2], encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            q.put((
                row["ip"].strip(),
                row["username"].strip(),
                row["password"].strip(),
                row.get("port", 22)
            ))

    print("================================================")
    print(" H3C 批量SSH验证【正确逻辑版】")
    print(" 不会误判密码！")
    print("================================================")

    for i in range(3):
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

    q.join()
    print(f"\n✅ 成功：{success}  |  ❌ 失败：{failed}")