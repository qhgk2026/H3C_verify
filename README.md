# verify_h3c.py 使用说明

`verify_h3c.py` 是一个用于批量验证 H3C Comware V5 交换机登录凭据的 Python 工具。

## 1. 脚本简介

该脚本支持 SSH 和 Telnet 两种协议，批量检查多台设备的用户名/密码是否有效。

## 2. 环境准备

### 2.1 Python 版本

推荐使用 Python 3.x。

### 2.2 依赖安装

- SSH 验证需要 `paramiko`
- Telnet 验证使用 `telnetlib`，但 Python 3.12 及以后版本可能已移除

安装 `paramiko`：

```bash
pip3 install paramiko
```

如果未安装 `paramiko`，SSH 验证会自动跳过并打印警告。

## 3. 输入文件格式

输入必须是 CSV 文件，字段如下：

- `ip`：目标交换机 IP 地址
- `username`：登录用户名
- `password`：登录密码
- `protocol`：协议，可选值 `ssh` 或 `telnet`，默认 `ssh`
- `port`：可选端口，默认 SSH 为 `22`，Telnet 为 `23`

### 示例 `switches.csv`

```csv
ip,username,password,protocol,port
192.168.1.10,admin,admin123,ssh,22
192.168.1.20,admin,admin123,telnet,23
192.168.1.30,admin,admin123
```

如果某行缺少 `protocol` 或 `port`，脚本会使用默认值。

## 4. 命令行参数

```bash
python3 verify_h3c.py -f switches.csv [-t 10] [-w 5] [-o result.csv]
```

参数说明：

- `-f`, `--file`
  - 必选
  - 指定输入 CSV 文件路径
- `-t`, `--timeout`
  - 可选
  - 单台设备连接超时秒数
  - 默认值：`10`
- `-w`, `--workers`
  - 可选
  - 并发线程数
  - 默认值：`5`
  - 建议不超过 `20`
- `-o`, `--output`
  - 可选
  - 结果输出 CSV 路径
  - 不指定时自动生成 `verify_result_YYYYMMDD_HHMMSS.csv`

## 5. 运行示例

### 5.1 基本运行

```bash
python3 verify_h3c.py -f switches.csv
```

### 5.2 指定超时和并发

```bash
python3 verify_h3c.py -f switches.csv -t 15 -w 10
```

### 5.3 指定输出文件

```bash
python3 verify_h3c.py -f switches.csv -o result.csv
```

## 6. 输出结果

### 6.1 控制台显示

脚本会打印每台设备的验证结果，包括：

- 进度序号
- IP
- 用户名
- 协议
- 状态：`OK` / `FAIL` / `SKIP` / `UNKNOWN`
- 用时
- 详细信息说明

### 6.2 CSV 输出

结果文件包含字段：

- `ip`
- `username`
- `protocol`
- `status`
- `message`
- `elapsed`

默认文件名类似：

```text
verify_result_20260512_153045.csv
```

## 7. 结果含义

- `OK`
  - 凭据验证成功
  - SSH 成功后会执行 `display version` 进行 H3C 设备确认
- `FAIL`
  - 登录失败
  - 可能原因：用户名/密码错误、网络不可达、连接被拒绝、超时等
- `SKIP`
  - 当前协议无法验证
  - 例如 `paramiko` 未安装导致 SSH 跳过，或 `telnetlib` 不可用导致 Telnet 跳过
- `UNKNOWN`
  - 无法确定登录状态
  - 例如 Telnet 返回了不明确的提示信息

## 8. 注意事项

- 如果没有安装 `paramiko`，SSH 验证会自动被跳过。
- Python 3.12+ 可能不自带 `telnetlib`，Telnet 验证可能不可用。
- 仅适用于 H3C Comware V5 交换机凭据验证。
- 如果 CSV 行数据不完整（缺少 IP、用户名、密码），该行会被跳过。

## 9. 返回码说明

- 全部验证完成且没有失败：退出码 `0`
- 存在失败项：退出码 `1`

## 10. 常见问题

### Q：没有输出结果文件？

A：如果未指定 `-o`，脚本会在当前目录自动生成结果 CSV。

### Q：SSH 连接成功但脚本提示不典型？

A：脚本检查 `display version` 输出是否包含 `H3C` / `Comware`，如果结果不标准则会标记为“非典型 H3C 输出”。

### Q：Telnet 登录后没有识别成功？

A：脚本尝试识别 H3C 常见提示符 `<设备名>` 或 `[设备名]`，如果不匹配则可能返回 `UNKNOWN`。
