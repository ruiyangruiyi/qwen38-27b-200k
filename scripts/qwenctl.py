#!/usr/bin/env python3
"""087 机 Qwen3.8-27B 服务管理（privatecam imagectl 同款风格）
用法: python3 qwenctl.py {start|stop|restart|status|test|install}
install = 新机部署：scp 本脚本到远端 + env 说明 + 目录校验（5090 等新机到手即用）
生产参数固定: 200K + KV_MEM 4.5G + chunk 2048 + DFlash2 + PREFIX_CACHE
"""
import subprocess, sys, time, urllib.request, os
# 本地自用版：自动加载同目录 .env（该文件 gitignore，绝不进仓库）
from pathlib import Path
_env = Path(__file__).parent / '.env'
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

# 远程主机配置从环境变量读（绝不硬编码密码）：
#   QWEN_SSH_HOST（如 connect.bjb1.seetacloud.com）
#   QWEN_SSH_PORT（如 49116）
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

def install():
    """新机部署助手：把 qwenctl.py 拷到远端 + 生成 .env 模板 + 校验目录结构
    （0902 更新：自启钩子已废弃，install 只做部署不做自启）
    """
    import shlex
    scp = ["sshpass", "-p", os.environ["QWEN_SSH_PASS"], "scp",
           "-o", "ConnectTimeout=15",
           "-P", os.environ.get("QWEN_SSH_PORT", "22"),
           str(Path(__file__).resolve()),
           f'{os.environ.get("QWEN_SSH_USER", "root")}@{os.environ.get("QWEN_SSH_HOST", "")}:/root/qwenctl.py']
    print("→ scp qwenctl.py → 远端 /root/ ...")
    r = subprocess.run(scp, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"✗ scp 失败: {r.stderr.strip()[:200]}"); return
    print("✓ qwenctl.py 已就位 /root/qwenctl.py")
    # 生成远端 .env 模板（自引用：远端管自己本机服务时 host 填 localhost 模式说明）
    env_tpl = ("# qwenctl 远端配置（本机直管模式可留空——qwenctl.py 在远端直接跑时读不到 ssh 就用本地 curl）\n"
               "# 若从远端再管别的机器才需要填：\n"
               "#QWEN_SSH_HOST=\n#QWEN_SSH_PORT=22\n#QWEN_SSH_PASS=\n"
               "#QWEN_PORT=18020\n")
    run(f"test -f /root/.qwen_env_done || printf '%s' {shlex.quote(env_tpl)} > /root/qwenctl.env.note && touch /root/.qwen_env_done")
    print("✓ env 说明已放 /root/qwenctl.env.note")
    # 校验部署目录
    r = run("test -d /root/autodl-tmp/qwen38-27b-rtx3090 && echo YES || echo NO")
    if r.stdout.strip() == "YES":
        print("✓ 模型目录 /root/autodl-tmp/qwen38-27b-rtx3090 存在")
    else:
        print("! 模型目录不存在——新机需先: git clone https://github.com/ruiyangruiyi/qwen38-27b-200k /root/autodl-tmp/qwen38-27b-rtx3090 && 跑 requantize（见 patches/）")
    print("完成。远端直接: python3 /root/qwenctl.py start（8-10 分钟起服务）")


if __name__ == "__main__":
    cmds = {"start": start, "stop": stop, "restart": lambda: (stop(), time.sleep(3), start()),
            "status": status, "test": test, "install": install}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__); sys.exit(1)
    cmds[sys.argv[1]]()
