<p align="center">
  <b>Language / 语言:</b>
  <a href="./README.md">English</a> ·
  <a href="./README.zh-CN.md">简体中文</a>
</p>

# meralion-transcribe

通过 **MERaLiON 云端 ASR 接口**(`api.meralion.ai`)把音频 / 视频转写成文字 —— 一套完全托管的语音转写服务。无需本地模型、不占用本地 GPU / CPU:音频只会上传,绝不在你本机处理。非常适合性能较弱的笔记本(老款 Intel MacBook Air,或任何 Apple 芯片的 Mac),或当你指定的转写服务就是 MERaLiON 时。

> **Apple 芯片注意:** 本技能调用的是云端接口,所以 **服务本身在任何 Mac 上都能用**。真正可能出问题的是它周围的本地工具链。在 arm64 Mac 上,如果 `ffmpeg` 仍是 x86_64 版本、且 **未安装 Rosetta 2**,那么 `ffmpeg` 以及所有 x86_64 辅助程序都会以 `Bad CPU type in executable` 直接失败。本技能给出了四个 arm64 原生的 macOS 替代工具 —— `afconvert`、`afinfo`、`python3`、`security` —— 完全不用 `ffmpeg` 也能跑通全流程。详见下文《没有 ffmpeg?Apple 芯片替代方案》。

## 它能做什么

- **纯云端转写** —— 零本地算力,因此在老旧 / 慢速机器上也能流畅运行。
- **任意输入格式** —— 只要 `ffmpeg` 能读的格式都行(m4a、mp3、wav……)。
- **OpenAI 风格 JSON** —— `choices[0].message.content`。(说话人分离与时间戳参数虽被接受,但不会真正返回 —— 见《注意事项》。)
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

## 没有 ffmpeg?Apple 芯片替代方案

本技能通常依赖 `ffmpeg`。如果 Mac 上的 `ffmpeg` 是 x86_64 版本、且 **未安装 Rosetta 2**,它会以 `Bad CPU type in executable` 直接失败 —— 其他 x86_64 辅助程序也一样。macOS 自带的四个 arm64 原生工具足以覆盖全流程:

| 用途 | 已失效 | 原生替代 |
|---|---|---|
| 音频 → 16 kHz 单声道 WAV | `ffmpeg`(x86_64) | **`/usr/bin/afconvert`** |
| 读取时长 / 源参数 | `ffprobe`(x86_64) | **`/usr/bin/afinfo`** |
| HTTPS POST + JSON | x86_64 Python | **`/usr/bin/python3`**(通用二进制) |
| 从钥匙串读取密钥 | — | `/usr/bin/security` |

```bash
# 转成 16 kHz 单声道 16-bit WAV —— 不需要 ffmpeg。afconvert 是每台 macOS 自带的。
/usr/bin/afconvert -f WAVE -d LEI16@16000 -c 1 IN.m4a /tmp/out.wav
# 上传前务必确认时长与源文件一致
/usr/bin/afinfo /tmp/out.wav | grep duration
```

**`afconvert` 没有 MP3 编码器**,所以在这类机器上只能输出 WAV —— 上文"MP3 能让上传体积更小"的建议在此不适用。切片请用 Python 标准库 `wave` 模块,而不是 `ffmpeg -ss`。现成脚本:`scripts/test_meralion.py`。

**请用绝对路径调用真实二进制文件**(`/bin/ls`、`/usr/bin/tail`、`/usr/bin/curl`)。裸命令名可能会命中一个以错误架构执行的 shim。

## 长音频:静默漏字(必读)

在长录音上,**单次整段请求**可能返回 **HTTP 200、非空 `content`、正常的 `usage`,却依然丢失了音频的很大一部分**。实测一段 910 秒(15 分钟)的"演讲 + 观众问答"双段录音:整段转写返回了 4,298 字、覆盖了演讲部分,却 **悄悄丢掉了约一半的问答** —— 没有报错、没有重复循环、没有任何征兆。而分段转写在同一段音频上返回了约 5,000 字,覆盖了整场。

这比重复循环 **更危险**,因为重复循环一眼就能看出坏了,而静默漏字看起来"成功"了。唯一的破绽是"转写偏短",但在没有基线的情况下,"短"很难判断。

**规则:超过约 5 分钟的音频,绝不要只信单次整段转写。** 务必再跑一遍分段转写,并比对 (a) 总字数 与 (b) 会话尾部是否完整。一个可参考的经验值:普通话连续语速大约 **每分钟 250–350 字**;整段转写远低于此,应当怀疑它"简略"了,而不是"精炼"了。

快速自检 —— 数一下字数,再看一眼尾部:

```bash
python3 -c "t=open('asr_whole.txt').read(); print(len(t)); print(t[-800:])"
```

**实际后果 —— 但先判断音频类型。** 对 **嘈杂 / 人多 / 超长** 的音频,把 **分段转写** 当作主稿,把整段转写当作一致性交叉校验。**反例:** 对 **近距离麦克风的干净音频**,整段转写反而可能 **更好** —— 实测一段 526 秒普通话会议室录音,整段 **2,581** 字 vs 分段 **2,091** 字,而且切片边界还会引入叠字("减减少")和断句。两种情况都跑一遍,取读起来最连贯的那一版。

## 模型与接口要点(踩坑总结)

- **接口地址:** `POST https://api.meralion.ai/v1/audio/transcriptions`。OpenAPI 文档里写的 `/audio/transcription` 在生产环境会返回 **404** —— 务必用 `/v1/...` 路径。
- **模型:** 用 `MERaLiON/MERaLiON-3-3B-ASR-CTM`。文档默认的 `MERaLiON/MERaLiON-ASR-EXP` 会返回 **422**;`MERaLiON-3-10B` 会 **静默回退到 3B** —— 返回体里的 `model` 字段会回显 `MERaLiON-3-3B-ASR-CTM`,且不报任何错,所以指定 10B 没有任何意义。在采信结果前,务必断言返回文本非空,**同时** 检查是否存在 `error` 键:一个合法的零采样 WAV 会返回 **HTTP 200,但响应体里带 `code: 400`**,只看状态码会把被拒绝的请求当成成功。
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
3. **跨多次转写交叉验证 —— 比对"语义锚点",绝不要逐字比对文本。** 这个模型返回的是 **改写**,不是复述:同一段 75 秒音频重跑一次,意思相同但用字不同。实测整段与分段两次结果之间的 12-gram 重合度只有 **约 55%(粤语)/ 约 72%(普通话)**,而两者字数却相差不到 0.4%。因此逐字比对会报出大量"分歧" —— 其实什么都没漏;而"只保留一致内容"的规则几乎会把全部内容都丢掉。正确做法是比对 **数字、日期、拉丁字母词与专有名词**:只在其中一次出现、另一次缺失的,才是真正的漏字或错误候选;共享锚点周围的用词差异属于模型不确定性,忽略即可。取读起来最连贯的那一版为主稿,把另一版独有的锚点记为待确认项。

不要悄悄把 ASR 的废话"抹平"。如果某个词反复出现但明显错了,请 **重建它并注明** 置信度。一份简短但诚实的文档,胜过一份流畅却编造的文档。

## 改名字前,先核实

一个看起来很有把握的"纠错",本身可能就是错误 —— 而且它比乱码更难发现,因为它读起来合情合理。**在"修正"某个 ASR 转出的产品名 / 品牌名之前,请先用原话逐字搜索。**

真实案例:一份转写写的是 "MiniMax H3"。因为讲话人当时在聊"声音",这段被当成了 MiniMax 的 `speech-2.6-hd` 语音模型的误转,并照此发布。但原话是 **对的** —— MiniMax H3 是真实存在的产品(他们的全模态视频模型)。讲话人比较的是视频生成方案,而不是 TTS。只要搜一下这个名字的原文字面,就能发现。

**规则:如果"原话"能对应到一个真实产品,就保留它。** 只有查无此物时才去重建。而且要警惕那些"需要讲话人恰好处于你预设的那个领域"的重建 —— 那往往是你自己先入为主的投射。

## 文件结构

- `SKILL.md` —— 完整触发条件、接口 / 模型坑点、用量限制,以及修复方案。
- `scripts/chunked_asr.py` —— 针对嘈杂 / 长音频的分段转写与交叉验证脚本。
  用法:`python3 chunked_asr.py SRC DENOISED_WAV CHUNK_SECONDS [OUTDIR]`。
- `scripts/test_meralion.py` —— 端到端冒烟测试,只用 macOS 原生工具(不需要 `ffmpeg`,不需要 pip)。
  用法:`/usr/bin/python3 scripts/test_meralion.py AUDIO [CHUNK_SECONDS]`。
- `CHANGELOG.md` —— 本技能的修订记录(按日期)。

## 注意事项

- MERaLiON 主打东南亚语言,但实测对普通话与中国香港粤语的转写效果都不错。对电话音质、强背景噪声、多人抢话,以及它主打的东南亚语言,尚无实测数据 —— 不要拿会议室录音的经验去外推。普通话质量优于粤语。
- **说话人分离与时间戳都不生效。** `return_diarization` / `return_timestamps` 参数会被接受,但永远不会出现在返回体里 —— 返回结构中既没有说话人标签,也没有分段时轴。时间戳请用你自己切片的 `-ss` 偏移推算。不要向用户承诺说话人分离。
- **粤语输出的字形默认是错的** —— 模型会输出粤语词汇,但夹杂简体 / 繁体两种字形(实测在必须用繁体的转写中,**24% 的汉字是简体独有字形**)。需要再过一遍 `s2hk` 转换;转换配方见 `dashscope-qwen-asr` 技能。
- **专有名词是最大的短板**(两种语言都一样)—— 某机构自己的名字在不同批次里出现过六种写法。请务必用独立材料(照片、幻灯片、官网)交叉核实。
- 通常依赖 `ffmpeg` / `ffprobe` 在 `PATH` 中,以及 Python 3(用于脚本)。在未安装 Rosetta 2 的 Apple 芯片 Mac 上,请改用上文的原生替代方案 —— 不需要 `ffmpeg`。

## 许可证

按"原样"提供,仅供个人与学习教育用途。如需再分发,请在本仓库中添加 LICENSE 文件。
