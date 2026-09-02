# qwen38-27b-200k

单卡 RTX 4090（24G）跑满 Qwen3.8-27B 200K 上下文——三天从 78K 拉到 200K 的完整部署方案。

基于 [syv-ai/qwen38-27b-rtx3090](https://github.com/syv-ai/qwen38-27b-rtx3090) 二次开发。

## 亮点

- **200K 上下文**（KVarN 4/2-bit KV + DFlash2 投机解码组合，原作者没做过的配置）
- **实测数据**：空载 327 c/s / 真实对话 139 c/s / 76K 捞针 28s / 272 条消息会话首 token 2.7s
- **prefix cache**：turn-2 从 16s → 0.6s（27 倍）
- **生产级守护链**：三层 supervisor 自动拉活（开机后一条命令手动拉起）

## 快速开始

```bash
# 租一张 4090（AutoDL 或任意平台），然后：
CTX=huge SPEC=dflash2 DFLASH_MAX_LEN=200000 \
KV_MEM=4500000000 PREFIX_CACHE=1 \
bash scripts/start_qwen.sh
```

完整参数说明见 [docs/deployment-notes.md](docs/deployment-notes.md)。

## 目录结构

```
scripts/
  start_qwen.sh       # 一键启动（生产参数内含）
  vllm_supervisor.sh  # vLLM 守护（挂掉自动拉活）
  keeper_supervisor.sh# 守护链根（拉活整条链）
  socat_keeper.sh     # 6006 端口转发守护
  qwenctl.py          # 远程管理（start/stop/status/test；本地 .env 读连接配置，.env 不进 git）
patches/              # vLLM 0.27.1 全套补丁（从生产机原样同步）
  ├─ kvarn-*.patch        # KVarN 4/2-bit KV cache 移植
  ├─ dflash2-*.patch      # DFlash2 投机解码
  ├─ install.sh           # 一键安装到 venv
  └─ _check_applied.py    # 补丁应用状态自检
docs/
  deployment-notes.md # 完整部署笔记（三天踩坑全记录）
```

新机部署顺序：`patches/install.sh`（补丁）→ `scripts/start_qwen.sh`（起服务）→ 需要守护链时再跑 `qwenctl.py start`。

从 Mac 管新机一条命令（scp qwenctl.py 过去+目录校验）：`python3 scripts/qwenctl.py install`（0902 新增，自启钩子已废弃，install 只做部署）

## 踩坑速查

| 症状 | 原因 | 解法 |
|------|------|------|
| pgrep 有进程但 API 不通 | 引擎僵死 | 用 curl 判活不用 pgrep |
| 双 conda env 行为不一致 | nohup 解析到错误 vllm | exec 改绝对路径 |
| 满配 245K 长 prefill OOM | 245760 是池容量不是单发长度 | 单发控制在 62K 内 |
| 4096 chunk 起不来 | 激活峰值翻倍过不了 KV 校验 | 2048 是 4090 甜点 |
| 100K+ 断崖式变慢 | 注意力显存访问模式崩坏 | 滑窗控制在 100K 内 |
| localhost 请求 502 | 系统代理劫持 | 空 opener 直连 |

## License

MIT

## 运行环境说明

脚本按 AutoDL 风格路径书写（`/root/autodl-tmp`、`/root/miniconda3`、conda env `vllm27`）。其他平台部署时按你的实际路径替换 `scripts/` 内的：
- `QWEN_DIR`（模型仓库目录，默认 `/root/autodl-tmp/qwen38-27b-rtx3090`）
- conda 激活行
- 日志路径
