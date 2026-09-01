# 把 24G 显存榨到 200K：我们和 Qwen3.8-27B 的三天极限拉扯

> 一天一夜，78K → 143K → 200K 上下文，单卡 RTX 4090。

## 起点

社区里跑 Qwen3.8-27B 的 24G 卡，上下文普遍停在 64K（bf16 KV）或 136K（int8 KV）。AutoDL 一张 4090，想跑满 200K？原版 repo 的作者自己都说"245K 是池容量不是单请求可灌长度"。

我们不信邪。

## 三级跳

**78K → 143K**：requantize 重打包。原 repo 的 prepare 脚本跑不通，十轮修复穿过去——quant config 跨层、ignore 正则、extra_tensors 重复键（这个最阴，同一个 tensor 被打包两次导致加载即炸）。顺手写了个 DenseDequantLMHeadMethod patch，LM head 反量化，原 repo 没有。

**143K → 200K**：KVarN 4/2-bit KV cache 塞进 DFlash2 投机解码链路。这个组合原作者没做过——KVarN 的 block-size 128 对齐和 DFlash2 的 eager verify 分支都要自己配。跑通那天显存 24G 满，池 200K，并发 1.09x。

**200K 生产化**：prefix cache。turn-2 从 16s 掉到 0.6s（27 倍）。代价是 KV 池让 16% 给 state page——值。

## 踩过的坑（按疼的程度排序）

1. **重启后 vllm 僵死**——pgrep 有进程但引擎死（显存 1MiB 残留壳）。判断活性用 curl 不是 pgrep
2. **双 conda env 打架**——机器两个 vllm 环境，nohup 里 `exec vllm` 解析到没 patch 的那个。修法：exec 行改绝对路径
3. **满配 245K 长 prefill 必 OOM**——KV_MEM 是 pin 的，GPU_UTIL 降了它不降。245760 是池容量不是单发长度，76K 文档全量灌一样撞死
4. **4096 chunk 的显存陷阱**——chunk 翻倍激活峰值也翻倍，两台 4090 都过不了 KV 校验（可用池 3.54G < 需求 3.91G）。2048 是这对机型的甜点
5. **chunked prefill 的效率悬崖**——97K 全量重算 2 秒，131K 要 74-130 秒（60 倍差）。100K~131K 之间有断崖，超过后注意力计算的显存访问模式崩坏
6. **系统代理劫持 localhost**——Mac 的 urllib 把 127.0.0.1 丢给代理返回 502。ProxyHandler({}) 空 opener 直连修复

## 最终配置（RTX 4090 24G 生产版）

```
CTX=huge SPEC=dflash2 DFLASH_MAX_LEN=200000 \
KV_MEM=4500000000 PREFIX_CACHE=1
```

- 主模型 W4A16-AutoRound 16G + DFlash2 草稿（7 token 投机，接受率 65%）
- KVarN kvarn_k4v2_g128 4/2-bit KV
- 实测：空载 327 c/s 三轮零抖动、真对话 139 c/s、76K 捞针 28 秒逐字命中、62K 真实会话 turn-2 6.2 秒

## 一点心得

- 显存预算是零和游戏：chunk 大了激活吃、vision 开了 tower 吃、KV pin 死了谁都动不了——每加一样东西都要从别处抠
- prefix cache 是免费的午餐，但前提是前缀真的稳定（我们把引擎的动态时间戳挪出 system 区后，272 条消息的会话 2.7 秒首 token）
- 24G 卡的甜点区间：池 200K、单发 62K、消息条数控制在 200 内。超出就进悬崖区

## 关于 engine7

这套部署跑在我们的 AI 助手框架 engine7 上——飞书/Discord/微信/桌面多通道，200K 上下文给了它读整个项目历史的能力。上面每个数字都是真实生产负载测出来的，不是跑分。

最后能落地的两笔关键改动也在引擎侧：**把每轮变化的内容（时间戳/情绪状态）从 prompt 头部挪到尾部**——头部只剩稳定内容，prefix cache 从"每轮全量重算"变"99% 命中翻笔记"，272 条消息的会话首 token 2.7 秒；**再把 prompt 本身瘦身**（窗口归并+记忆蒸馏上限），冷启动要算的量同步变小。一个是让缓存接得上，一个是让笔记变薄——叠加才有秒回。

基于 syv-ai/qwen38-27b-rtx3090 二次开发——requantize 修复和 KVarN+DFlash2 组合配置都在本文里，可复现。
