<p align="center">
  <b>Language / 语言:</b>
  <a href="./README.md">English</a> ·
  <a href="./README.zh-CN.md">简体中文</a>
</p>

# meralion-transcribe

通过 **MERaLiON 云端 ASR 接口**(`api.meralion.ai`)把音频 / 视频转写成文字 —— 一套完全托管的语音转写服务。无需本地模型、不占用本地 GPU / CPU:音频只会上传,绝不在你本机处理。非常适合性能较弱的笔记本(例如 Intel MacBook Air),或当你指定的转写服务就是 MERaLiON 时。

## 它能做什么

- **纯云端转写** —— 零本地算力,因此在老旧 / 慢速机器上也能流畅运行。
- **任意输入格式** —— 只要 `ffmpeg` 能读的格式都行(m4a、mp3、wav……)。
- **OpenAI 风格 JSON** —— `choices[0].message.content`,可选说话人分离(diarization)与字 / 句级时间戳。
- **嘈杂音频工具箱** —— 一段分段式 ASR 脚本,用于交叉验证多人对话 / 重复循环失效的情况。

## 安装

直接告诉 WorkBuddy:

> Install meralion-transcribe skill from https://github.com/greggchen308/gc-skills/tree/main/meralion-transcribe

或手动安装:

```bash
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/greggchen308/gc-skills.git
cd gc-skills
git sparse-checkout set meralion-transcribe
mv meralion-transcribe ~/.workbuddy-ai/skills/
```

## 调用

```
/meralion-transcribe
```

或者直接让 WorkBuddy"用 MERaLiON 转写 <文件>"。

## 1) 获取 MERaLiON API Key

1. 打开 MERaLiON 控制台:**https://studio.meralion.ai/api-console**
2. 切到 **"My Key"**(我的密钥)标签页。
3. **免费注册**,创建账号并生成你的 API Key。
4. (备选) 点击 **API Tiers → Custom Plan**(套餐 → 定制方案)申请测试权限。

请妥善保管密钥 —— 下一步你会把它存进 macOS 钥匙串,或通过 `MERALION_KEY` 环境变量传入。

## 2) 存放密钥(macOS 钥匙串)

```bash
security add-generic-password -s "meralion.ai" -w "PASTE_YOUR_KEY_HERE" -U
```

技能在运行时会用 `security find-generic-password -s "meralion.ai" -w` 把它读回来。

**非 macOS / 快速测试:** 改为导出环境变量 —— 技能会回退到环境读取:

```bash
export MERALION_KEY="PASTE_YOUR_KEY_HERE"
```

切勿把密钥写入文件或提交到代码仓库。

## 工作流程

1. 用 `ffmpeg` **转成 16 kHz 单声道**(MP3 能让上传体积更小;WAV 也能用,但大约大 4 倍)。
2. **POST** base64 音频到 `https://api.meralion.ai/v1/audio/transcriptions`,头部带 `Authorization: Bearer <KEY>`。
3. 服务端会对长音频(10 分钟以上)自动切片;请留出充足超时时间。
4. **分段转写(长音频 / 嘈杂音频推荐):** 在整段转写之外,再跑一遍 `scripts/chunked_asr.py` 做交叉验证 —— 见下文。

```bash
# 去噪 + 高通滤波,得到 16 kHz 单声道 WAV
ffmpeg -y -i IN -af "highpass=f=85,afftdn=nr=12:nf=-30" -ar 16000 -ac 1 -c:a pcm_s16le out.wav
# 分段转写:SRC DENOISED_WAV CHUNK_SECONDS [OUTDIR]
python3 scripts/chunked_asr.py IN out.wav 60 /tmp/meralion_asr
```

## 长音频:静默漏字(必读)

在长录音上,**单次整段请求**可能返回 **HTTP 200、非空 `content`、正常的 `usage`,却依然丢失了音频的很大一部分**。实测一段 910 秒(15 分钟)的"演讲 + 观众问答"双段录音:整段转写返回了 4,298 字、覆盖了演讲部分,却 **悄悄丢掉了约一半的问答** —— 没有报错、没有重复循环、没有任何征兆。而分段转写在同一段音频上返回了约 5,000 字,覆盖了整场。

这比重复循环 **更危险**,因为重复循环一眼就能看出坏了,而静默漏字看起来"成功"了。唯一的破绽是"转写偏短",但在没有基线的情况下,"短"很难判断。

**规则:超过约 5 分钟的音频,绝不要只信单次整段转写。** 务必再跑一遍分段转写,并比对 (a) 总字数 与 (b) 会话尾部是否完整。一个可参考的经验值:普通话连续语速大约 **每分钟 250–350 字**;整段转写远低于此,应当怀疑它"简略"了,而不是"精炼"了。

快速自检 —— 数一下字数,再看一眼尾部:

```bash
python3 -c "t=open('asr_whole.txt').read(); print(len(t)); print(t[-800:])"
```

**实际后果:** 对长音频,把 **分段转写** 当作主稿,把整段转写当作一致性交叉校验 —— 顺序不要反过来。

## 模型与接口要点(踩坑总结)

- **接口地址:** `POST https://api.meralion.ai/v1/audio/transcriptions`。OpenAPI 文档里写的 `/audio/transcription` 在生产环境会返回 **404** —— 务必用 `/v1/...` 路径。
- **模型:** 用 `MERaLiON/MERaLiON-3-3B-ASR-CTM`。文档默认的 `MERaLiON/MERaLiON-ASR-EXP` 会返回 **422**;`MERaLiON-3-10B` 会静默回退到 3B,并可能返回一段 **空白** 文本。在采信结果前,务必断言返回文本非空。
- **鉴权:** `Authorization: Bearer <KEY>`(也支持 `X-API-Key` 头或 `?api_key=` 参数)。
- **请求体:** `{"audio_url":"data:<mime>;base64,<B64>"}`,mime 取 `audio/wav|audio/mp3|audio/ogg`。音频必须是 **16 kHz 单声道**。
- **返回:** OpenAI 风格 —— `choices[0].message.content`(回退到 `text` 或 `transcript`)。
- **错误码:** 404 = 路径错误;422 = 模型枚举错误;"Broken pipe" 多半是大文件传错路径导致,而非体积问题。

## 用量限制(ASTAR SG 已审批档位)

- **已审批档位:** 5 次 / 分钟,1000 次 / 月,**音频 30 小时 / 月**(约 1800 分钟)—— 远超原先 60 分钟的默认值。
- 实时用量:`GET https://api.meralion.ai/keys/usage`;档位信息:`GET /keys/tiers`。
- **限速:** 5 rpm 是硬上限。批量 / 切片任务要控制节奏(每次调用间隔 `sleep 12–13` 秒),避免触发 429。

## 嘈杂音频:重复循环修复

在嘈杂的多人录音(人群、餐厅、互相打断)上,3B 模型可能陷入 **重复循环** —— 把同一个词或短语重复几百遍 —— 导致转写尾部变成废话。这是模型失效,不是文件问题。

**修复方法(三步全用,再做交叉验证):**

1. **上传前去噪 + 高通滤波**(命令见上文"工作流程")。
2. **切成 30–75 秒小段** 分别转写(脚本:`scripts/chunked_asr.py`);每段自带的 `-ss` 偏移还能免费拿到时间戳。
3. **跨多次转写交叉验证** —— 整段、75 秒段、30 秒段各跑一遍,逐句比对。只有多次结果一致的才进交付物;只出现一次的标记为不确定。

不要悄悄把 ASR 的废话"抹平"。如果某个词反复出现但明显错了,请 **重建它并注明** 置信度。一份简短但诚实的文档,胜过一份流畅却编造的文档。

## 改名字前,先核实

一个看起来很有把握的"纠错",本身可能就是错误 —— 而且它比乱码更难发现,因为它读起来合情合理。**在"修正"某个 ASR 转出的产品名 / 品牌名之前,请先用原话逐字搜索。**

真实案例:一份转写写的是 "MiniMax H3"。因为讲话人当时在聊"声音",这段被当成了 MiniMax 的 `speech-2.6-hd` 语音模型的误转,并照此发布。但原话是 **对的** —— MiniMax H3 是真实存在的产品(他们的全模态视频模型)。讲话人比较的是视频生成方案,而不是 TTS。只要搜一下这个名字的原文字面,就能发现。

**规则:如果"原话"能对应到一个真实产品,就保留它。** 只有查无此物时才去重建。而且要警惕那些"需要讲话人恰好处于你预设的那个领域"的重建 —— 那往往是你自己先入为主的投射。

## 文件结构

- `SKILL.md` —— 完整触发条件、接口 / 模型坑点、用量限制,以及修复方案。
- `scripts/chunked_asr.py` —— 针对嘈杂 / 长音频的分段转写与交叉验证脚本。
  用法:`python3 chunked_asr.py SRC DENOISED_WAV CHUNK_SECONDS [OUTDIR]`。
- `CHANGELOG.md` —— 本技能的修订记录(按日期)。

## 注意事项

- MERaLiON 主打东南亚语言,但实测对普通话的转写效果也不错。
- 说话人分离(`return_diarization`)仅在多人音频上追加说话人标签;单人讲话返回纯文本。
- 依赖 `ffmpeg` / `ffprobe` 在 `PATH` 中,以及 Python 3(用于脚本)。

## 许可证

按"原样"提供,仅供个人与学习教育用途。如需再分发,请在本仓库中添加 LICENSE 文件。
