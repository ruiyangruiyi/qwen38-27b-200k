#!/bin/bash
# 6006 -> 18020 socat 保活（每 60s 检查，死了拉活）
while true; do
  if ! ss -tln | grep -q ":6006 "; then
    nohup socat TCP-LISTEN:6006,reuseaddr,fork TCP:127.0.0.1:18020 </dev/null >>/tmp/socat_6006.log 2>&1 &
  fi
  sleep 60
done
