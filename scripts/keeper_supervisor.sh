#!/bin/bash
# keeper 的 keeper：每 120s 确认 socat_keeper + vllm_supervisor 都活着
while true; do
  pgrep -f "socat_keeper.sh" > /dev/null || nohup bash /root/socat_keeper.sh > /tmp/keeper.log 2>&1 &
  pgrep -f "vllm_supervisor.sh" > /dev/null || nohup bash /root/vllm_supervisor.sh > /tmp/vllm_sup.log 2>&1 &
  sleep 120
done
