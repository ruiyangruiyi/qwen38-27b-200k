#!/bin/bash
# vllm_supervisor：EngineDead 自愈。/v1/models 三连挂(各5s) → 杀干净 → 重拉生产版
# 生产参数跟 12:22 纯文本版一致；要开 VISION 时改本文件的 VISION=1
FAIL=0
while true; do
  if curl -s -o /dev/null --max-time 5 http://127.0.0.1:18020/v1/models; then
    FAIL=0
  else
    FAIL=$((FAIL+1))
    echo "$(date '+%F %T') probe fail x$FAIL" >> /root/vllm_supervisor.log
    if [ $FAIL -ge 3 ]; then
      echo "$(date '+%F %T') EngineDead suspected, killing+relaunching" >> /root/vllm_supervisor.log
      pkill -f "vllm serve" 2>/dev/null
      pkill -f "EngineCore" 2>/dev/null
      sleep 8
      cd /root/autodl-tmp/qwen38-27b-rtx3090 && env CTX=huge SPEC=dflash2 PORT=18020 DFLASH_MAX_LEN=200000 KV_MEM=4500000000 PREFIX_CACHE=1 VISION=${VISION:-0} nohup bash single-user/start_qwen.sh > /root/autodl-tmp/vllm_prod.log 2>&1 &
      FAIL=0
      sleep 420  # 等启动（模型加载+graph capture 约2-3分钟），期间不探
    fi
  fi
  sleep 30
done
