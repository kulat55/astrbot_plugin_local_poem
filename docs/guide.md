# 古诗插件制作指导手册

> 项目：`astrbot_plugin_local_poem`（本地古诗：接对句 / 考诗）
> 制作日期：2026-10-26
> 适用环境：Windows + AstrBot 4.29.3（后台走 aiocqhttp 接入 QQ）

本文记录从需求到发布的完整制作过程，任何人照着本文可以完整复现。

---

## 1. 需求

用户希望机器人具备古诗双向互动能力：

1. **我出上句，它接出下句**（附作者与出处）；
2. **它出上句考我，我答下句，它判定对错**；
3. 倾向**本地知识库**方案（不依赖在线接口）。

## 2. 技术方案决策

| 方案 | 优劣 |
| --- | --- |
| AstrBot 自带向量知识库（kb + Ollama bge-m3） | 适合"模糊问诗"（找写思乡的诗）；但对句是唯一确定答案，用向量检索又慢又不准 |
| **本地 JSON 诗库 + 精确匹配（采用）** | 对句唯一、毫秒级命中、免费、离线；`/诗考` 随机抽联出题，判定用规范化字符串比对 |

结论：本地精确库为主。向量知识库作为可选叠加，本次不做。

## 3. 数据获取

### 3.1 数据源

- 仓库：`chinese-poetry/chinese-poetry`（最全中华古诗词数据库，MIT，Copyright 2016 JackeyGao）
- 本机网络 GitHub 直连不通，使用镜像代理：`https://gh-proxy.com/<原URL>`

### 3.2 定位数据文件

用 GitHub API 经镜像列出目录（API 可用，直连 raw 不可用）：

```
GET https://gh-proxy.com/https://api.github.com/repos/chinese-poetry/chinese-poetry/contents/蒙学
```

确认文件（均位于仓库内）：

| 文件 | 路径 | 说明 |
| --- | --- | --- |
| `shuimotangshi.json` | `水墨唐诗/shuimotangshi.json` | 176 首，简体，带白话译文 |
| `tangshisanbaishou.json` | `蒙学/tangshisanbaishou.json` | 唐诗三百首，繁体，按体裁分卷 |
| `qianjiashi.json` | `蒙学/qianjiashi.json` | 千家诗，繁体 |

### 3.3 下载

```
https://gh-proxy.com/https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/水墨唐诗/shuimotangshi.json
https://gh-proxy.com/https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/蒙学/tangshisanbaishou.json
https://gh-proxy.com/https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/蒙学/qianjiashi.json
```

PowerShell 中文件名含中文需先 `[uri]::EscapeDataString()` 编码；GitHub API 路径同理。

### 3.4 数据结构（两个典型形态）

诗（水墨唐诗）：

```json
{"author": "王建", "title": "新嫁娘",
 "paragraphs": ["三日入厨下，洗手作羹汤。", "未谙姑食性，先遣小姑尝。"],
 "prologue": "译文……"}
```

选集（唐诗三百首 / 千家诗）：顶层 `{"title": "唐诗三百首", "content": [{"type": "五言绝句", "content": [{"chapter": "...", "author": "...", "paragraphs": [...]}]}]}`，均为**繁体**。

## 4. 数据处理（`tools/build_poems.py`）

处理管线：

1. **展平**：三个源归一为 `{title, author, dynasty, genre, paragraphs[], translation?}`
2. **简繁转换**：`pip install zhconv`，`convert(text, "zh-cn")` 转简体（正文、标题、作者统一转）
3. **对联切分**：每条 `paragraphs` 项按全角 `，。？！` 切分，**两两成对**取 (上句, 下句)，跳过不足两段的项；相同 (上句,下句) 全局去重
4. **诗去重**：按 (标题, 作者) 合并
5. **产出** `poems.json`：

```json
{
  "meta": {"count_poems": 612, "count_couples": 2284, "source": [...]},
  "poems":  [{"title", "author", "dynasty", "genre", "translation", "paragraphs", "couples"}],
  "couples": [{"up", "down", "title", "author"}]
}
```

### 处理中的两个真实坑（记录）

- **问号没参与切分**：初版切分只用了 `，。`，导致"红豆生南国，春来发几枝？愿君多采撷，此物最相思。"被切成 `["红豆生南国", "春来发几枝？愿君多采撷", "此物最相思"]`，下句错位成"春来发几枝？愿君多采撷"。修复：分隔符加入 `？！`，并按步长 2 成对取值。
- **标题作者漏转简体**：初版只转正文，标题/作者保留繁体（如"李白《靜夜思》"）。修复：入口处统一 `clean()`。

### 数据范围说明

库只包含三部选集收录的诗句。《使至塞上》"大漠孤烟直，长河落日圆"不在三部选集中，属于数据范围问题而非缺陷；范围外的句子会提示"不在库中"。

## 5. 插件开发

### 5.1 目录结构

```
astrbot_plugin_local_poem/
├── metadata.yaml
├── main.py
├── README.md
└── data/
    └── poems.json
```

### 5.2 metadata.yaml（AstrBot 4.29 规范）

```yaml
name: astrbot_plugin_local_poem   # 唯一标识，英文
display_name: 本地古诗
short_desc: 本地古诗库：/诗接 对句、/诗考 考你古诗、/诗答 判定，离线可用
desc: 详细描述……（支持多行/Markdown）
help: 使用说明
version: v1.0.0
author: kulat55
repo: https://github.com/kulat55/astrbot_plugin_local_poem
support_platforms:
  - aiocqhttp
```

### 5.3 main.py 关键点（AstrBot 4.29.3 实测）

- **import 规范**（与社区插件的兼容写法）：

```python
from astrbot.api.event import AstrMessageEvent, filter   # filter 在 api.event，不在 api.star！
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr   # 接整句参数
```

- **不写 `@register` 装饰器**：4.29.3 的 `astrbot.api.star` 不导出 `register`/`filter`，直接写 `class LocalPoemPlugin(Star)` 即可，元信息从 metadata.yaml 读取。初版踩坑：`cannot import name 'filter' from 'astrbot.api.star'`。
- **命令**：

```python
class LocalPoemPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 加载 data/poems.json，建 by_up / by_down 两个索引（键为去标点规范化串）

    @filter.command("诗接")
    async def poem_join(self, event, text: GreedyStr):
        # 精确查索引；命中返回对句 + 出处，未命中提示"不在库中"

    @filter.command("诗考")
    async def poem_quiz(self, event):
        # random.choice(couples) 出题，记录到 self.quiz[session_id]

    @filter.command("诗答")
    async def poem_answer(self, event, text: GreedyStr):
        # 规范化比对（去标点去空白），答对给全文出处，答错给正确答案
```

- **规范化函数**：`re.sub(r"[\s，。、；：！？·…]", "", s)`，判定规则 = 完全相等 **或** 正确答案包含在用户输入中（容忍多打几个字）。
- 所有逻辑只依赖标准库，无第三方依赖。

## 6. 测试与修复记录

独立逻辑测试（不启动 AstrBot，直接加载 poems.json 复刻索引与判定）：

| 用例 | 结果 |
| --- | --- |
| 床前明月光 → 疑是地上霜（含反向） | ✔ |
| 白日依山尽 → 黄河入海流 | ✔ |
| 春眠不觉晓 → 处处闻啼鸟 | ✔ |
| 红豆生南国 → 春来发几枝（修复切分后） | ✔ |
| 判定：答"疑是地上霜。"（带句号）算对 | ✔ |
| 判定：答"地上霜"算错 | ✔ |

修复项：切分分隔符、标题作者简体、zip 打包相对路径（`data/poems.json` 不能展平到根目录）。

## 7. 安装到 AstrBot

### 7.1 打包

zip 顶层必须是一个目录，目录内为插件文件；**不要**把 `__pycache__`、`.git` 打进去：

```
astrbot_plugin_local_poem.zip
└── astrbot_plugin_local_poem/
    ├── metadata.yaml
    ├── main.py
    ├── README.md
    └── data/poems.json
```

打包命令（Python zipfile 写法，注意相对路径）：

```python
import zipfile, os
src = r"...\astrbot_plugin_local_poem"
dst = r"...\astrbot_plugin_local_poem.zip"
z = zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED)
for r, _, fs in os.walk(src):
    for f in fs:
        if "__pycache__" in r or "__pycache__" in f:
            continue
        z.write(os.path.join(r, f),
                os.path.join("astrbot_plugin_local_poem",
                             os.path.relpath(r, src), f).replace("\\", "/"))
z.close()
```

### 7.2 上传安装（后台 API）

```
POST /plugins/install/upload        # multipart/form-data，字段名 file
POST /plugins/reload  {"plugin_id": "astrbot_plugin_local_poem"}
```

安装后验证（后台日志 `/logs/history`）：

```
Loading plugin astrbot_plugin_local_poem ...
Plugin astrbot_plugin_local_poem (v1.0.0) by <author>: 本地古诗库（612 首、2284 联对句……）
Installed plugin astrbot_plugin_local_poem.zip successfully.
```

## 8. 发布到 GitHub

1. 在 GitHub 新建公开仓库 `astrbot_plugin_local_poem`；
2. 推送内容：`metadata.yaml`、`main.py`、`README.md`、`data/poems.json`、`docs/guide.md`（本文档）、`LICENSE`（MIT）、`.gitignore`（排除 `__pycache__/`、`.git/`）；

## 9. 发布到 AstrBot 插件市场（让市场可搜索）

官方文档：<https://docs.astrbot.app/dev/star/plugin-publish.html>

流程（官方）：

1. **先把插件代码推送到 GitHub 仓库**（市场从 GitHub 拉取）；
2. 前往 **AstrBot 插件发布页面**，用 **AstrBot Cloud 账号** 登录提交（需先注册 AstrBot Cloud）；
3. 系统自动解析 `metadata.yaml`（name / display_name / short_desc / desc / version / author / repo 等字段）；
4. 通过审核后，市场即可按插件名/标签搜索到。

发布限制与建议：

- zip 包 ≤ **16MB**（本插件约 200KB，无压力）；
- 清理 `__pycache__`、`.git`、`node_modules` 等非必要文件；
- 图片等静态资源尽量压缩；
- 提交后留意 CI 校验结果，失败按提示修改重提。

## 10. 文件清单

| 文件 | 位置 | 说明 |
| --- | --- | --- |
| 插件工程 | `astrbot_plugin_local_poem/` | metadata / main.py / data/poems.json / README |
| 重建脚本 | `tools/build_poems.py` | 数据处理管线（本文第 4 节） |
| 本文档 | `docs/guide.md` | 制作全流程 |

## 附录：常用镜像（本机实测）

| 镜像 | 用途 | 实测结果 |
| --- | --- | --- |
| `gh-proxy.com/https://github.com/...` | raw / API / codeload zip | ✔ 可用 |
| `ghproxy.net/...` | raw 文本、archive zip | ✔ 可用（codeload 403） |
| ghfast.top / gh.ddlc.top / github.moeyy.xyz 等 | — | ✘ 不可用 |
| `cdn.jsdelivr.net/gh/<user>/<repo>@<branch>/...` | raw 文件 | 本机网络 ✘ |
