#!/usr/bin/env python3
"""087 机 Qwen3.8-27B 服务管理（privatecam imagectl 同款风格）
用法: python3 qwenctl.py {start|stop|restart|status|test}
生产参数固定: 200K + KV_MEM 4.5G + chunk 2048 + DFlash2 + PREFIX_CACHE
"""
import subprocess, sys, time, urllib.request, os

# 远程主机配置从环境变量读（绝不硬编码密码）：
#   QWEN_SSH_HOST（你的服务器地址）
#   QWEN_SSH_PORT（SSH 端口）
#   QWEN_SSH_USER（默认 root）
#   QWEN_SSH_PASS（sshpass 密码；若配了免密公钥可留空走 SSH_ASKPASS=none）
#   QWEN_PORT（vllm 端口，默认 18020）
SSH = ["sshpass", "-p", os.environ["QWEN_SSH_PASS"], "ssh",
       "-o", "ConnectTimeout=15",
       "-p", os.environ.get("QWEN_SSH_PORT", "22"),
       f'{os.environ.get("QWEN_SSH_USER", "root")}@{os.environ.get("QWEN_SSH_HOST", "")}']
if not os.environ.get("QWEN_SSH_HOST"):
    sys.exit("请先 export QWEN_SSH_HOST / QWEN_SSH_PORT / QWEN_SSH_PASS（见文件头注释）")
PORT = os.environ.get("QWEN_PORT", "18020")
URL = f"http://127.0.0.1:{PORT}/v1/models"
START_CMD = ("cd /root/autodl-tmp/qwen38-27b-rtx3090 && "
             "env CTX=huge SPEC=dflash2 PORT=18020 DFLASH_MAX_LEN=200000 "
             "KV_MEM=4500000000 PREFIX_CACHE=1 "
             "nohup bash single-user/start_qwen.sh > /root/autodl-tmp/vllm_prod.log 2>&1 &")

def run(cmd, timeout=60):
    return subprocess.run(SSH + [cmd], capture_output=True, text=True, timeout=timeout)

def remote_curl():
    r = run("curl -s -m 8 -o /dev/null -w '%{http_code}' http://127.0.0.1:18020/v1/models")
    return r.stdout.strip()

def start():
    code = remote_curl()
    if code == "200":
        print("✓ 服务已在运行 (200)")
        return
    print("启动 vllm（约 8-10 分钟：模型加载+cudagraph）...")
    run("pkill -9 -f 'vllm serve' 2>/dev/null; sleep 2", timeout=30)
    run(START_CMD)
    for i in range(20):
        time.sleep(30)
        code = remote_curl()
        print(f"  [{(i+1)*30}s] {code}")
        if code == "200":
            print("✓ 服务就绪")
            keepers()
            return
    print("✗ 10 分钟未就绪，查日志: /root/autodl-tmp/vllm_prod.log")

def keepers():
    run("pgrep -f keeper_supervisor.sh > /dev/null || setsid nohup bash /root/keeper_supervisor.sh > /dev/null 2>&1 < /dev/null &")
    print("✓ 守护链已确认")

def stop():
    run("pkill -9 -f 'vllm serve'; pkill -f start_qwen; sleep 2")
    print("✓ 已停止（守护链保留，会自动拉活——彻底停用: pkill -f keeper_supervisor; pkill -f vllm_supervisor）")

def status():
    code = remote_curl()
    print(f"服务: {'✓ 200 在线' if code=='200' else '✗ '+code}")
    r = run("ps aux | grep -cE 'keeper_supervisor.sh$|vllm_supervisor.sh$|socat_keeper.sh$'")
    print(f"守护链: {'✓ '+r.stdout.strip()+' 层' if r.stdout.strip()!='0' else '✗ 未起（start 会补）'}")
    r = run("ss -tln | grep -c 6006")
    print(f"6006 转发: {'✓' if r.stdout.strip()!='0' else '✗'}")

def test():
    code = remote_curl()
    if code != "200":
        print(f"✗ 服务不在线 ({code})，先 start"); return
    r = run('''curl -s -m 30 -X POST http://127.0.0.1:18020/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"1+1？只答数字"}],"max_tokens":10,"chat_template_kwargs":{"enable_thinking":false}}' | grep -o '"content": *"[^"]*"' | head -1''')
    print(f"推理: {r.stdout.strip() or '✗ 无响应'}")

if __name__ == "__main__":
    cmds = {"start": start, "stop": stop, "restart": lambda: (stop(), time.sleep(3), start()),
            "status": status, "test": test}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__); sys.exit(1)
    cmds[sys.argv[1]]()
