# 生图设计与还原校准

返回 [主入口](../SKILL.md)。先用生图探索或锁定界面的构图、比例、留白与色彩关系，再将设计图作为视觉基线转化为可运行、响应式的代码或接入存量项目。视觉质量与业务完整性分别验收，不能用内容齐全、对齐规整替代设计成立。

## 目录导航

- [何时探测生图能力并让用户选择](#何时探测生图能力并让用户选择)
- [参考图策略与组件素材边界](#参考图策略与组件素材边界)
- [视觉构思、视口比例与提示词组织](#视觉构思视口比例与提示词组织)
- [完整落地页与分段长图](#完整落地页与分段长图)
- [检查、测量与响应式实现](#检查测量与响应式实现)

## 何时探测生图能力并让用户选择

当任务属于**新建界面（说服型页面、产品工作区与后台管理界面、存量项目新增子页面）、多方向视觉探索或存量重塑**时，先生成 UI 效果图能有效锁定构图、比例、留白与色彩张力。进入任务时，先静默检查当前环境是否具备生图能力：

1. **宿主原生生图工具**：检查当前环境是否已挂载可直接调用的图像生成工具。
2. **Oil 生图脚本**：若无宿主生图工具，静默调用 `oiloil-image.mjs` 的 `balance` 子命令检查积分状态；退出码为 `0` 且输出余额 `>= 2` 积分时，视为生图能力可用。
3. **无生图能力时静默回退**：若两者均不可用（未登录、积分不足或离线环境），不报错、不索要密钥、不中断任务，直接按常规代码流程推进。

确认生图能力可用、且用户尚未明确指定“先生图”或“直接写代码”时，**将步骤 1 的三四行方案推荐与是否生图合并为全流程唯一一次确认**（不在方案确认前额外提问，也不在生图完成后再次停顿等确认）：

1. **（推荐）先按此方案生成 UI 设计稿，并直接完成响应式代码实现**
2. **跳过生图，直接按此方案用代码实现界面**
3. **仅生成 UI 设计稿（暂不写代码）**

用户选择第 1 项后，直接生成 UI 设计稿并紧接着完成响应式代码与真实画面验证，中途不再停下来二次确认。用户一开始就说了“你定”“直接做”或处于无人值守模式时，不等待确认，直接先生成设计稿再转响应式代码；用户只要设计稿时交付图片与简短设计说明。并发调用 `oiloil-image.mjs` 时最多同时运行 **2 个进程**；命令行中的 `--prompt` 一律使用**单引号 `'...'`** 包裹。

## 参考图策略与组件素材边界

先区分借鉴风格、保留固定框架与精准还原。风格参考提取业务焦点、字体对比、留白、比例和图像用途，按当前业务重组内容；不要复制无关营销模块或作品展示外框。

| 参考用途 | 使用方式 |
| --- | --- |
| 自由探索 | 无参考也可执行，从任务与领域入口选择视觉方向 |
| 只保留导航、侧边栏或现有页面框架 | 先用 [工具](tools.md) 的 `shoot.mjs` 截取当前页面真实画面作为参考图传入（`--ref`），写清固定范围与允许变化的区域 |
| 借鉴风格 | 传入实际参考图，说明借鉴的设计关系与允许变化的内容；未实际传入图片时只能称为文字提炼参考 |
| 精准还原 | 完整截图用于测量与整体对照；只有确需素材重绘时才将相应图片送入生图工具 |

在生成或实现前明确组件与素材边界：

- **代码负责**：布局、文字、控件、普通图标和动态图表由代码实现；正文、数据标签和操作保持可编辑。
- **独立素材负责**：摄影、原创插画和特殊品牌视觉使用独立素材放入明确容器。优先复用质量足够的原始素材、项目资源和干净裁图；缺失或不合格时才生成或重绘，不默认重画品牌标识。

## 视觉构思、视口比例与提示词组织

先理解用户的浏览与操作顺序，结合已选领域入口确定视觉手法，再组织内容：

| 界面 | 设计重点 |
| --- | --- |
| 品牌官网与说服型页面 | 主视觉与文字的关系，跨区块节奏和一致的品牌表达 |
| 后台与产品工作区 | 核心判断与操作突出，主分析、辅助指标、待办和记录有不同分量；特色来自信息组织与组件细节 |
| 移动产品 | 内容、导航与主操作比例适当，小空间中仍保留清楚的字体和状态层级 |
| 游戏与游玩界面 | 世界观通过插画、配色和图标进入界面，任务、数值与控件保持可读可操作 |

展示数据可用表格或图表，反复浏览同类对象用稳定列表，需要比较时才并列。不要把“侧栏＋指标卡＋折线＋表格”当成默认答案，也不为避开模板禁用合理组件。允许有目的的大小对比、非对称、错位、重叠与特殊裁切，说明它们如何通过布局、遮罩、字体或独立素材实现，以及窄屏如何处理。

### 区分逻辑视口与输出像素（50 词填空式短提示词与色彩范围洞察）

逻辑视口、文档高度和生成像素分别记录：

- 移动端 `390×844` 的逻辑视口可以生成 `1024×1536` 的图片，但不能把生成图的 `1024` 像素宽当作手机布局宽；桌面长页数千像素的高度也不是桌面视口高度。
- **生图提示词遵循「45–65 词精简法则」，依靠以下 5 条设计洞察释放模型上限**：
  1. **控长度（45–65 词，2–3 句话）**：只定义“结构关系、比例留白、色彩角色范围与图形构件”，不写长篇逐行线框图说明书，把自然排版与构图权还给模型。
  2. **不塞具体引号文案与外部品牌配对**：在提示词中罗列十几个中文标题或具体数值，会迫使模型为了画清每个汉字而将全局字号与容器放大 1.5 倍；指定真实外部品牌配对则极易画错图标。生图阶段只写领域与语言（`Simplified Chinese interface for <产品领域>`）及通用图标约束（`clean abstract icons, no third-party brand logos`），具体业务文案与真实身份素材留到代码阶段实现。
  3. **用「小比例底盘＋充裕留白」锁死清爽度**：固定声明 `delicate small-scale desktop proportions, petite typography, and generous open whitespace`。严禁使用 `oversized`、`giant`、`thick`（会连带放大侧栏与按钮），也不用机械的“每张卡片留白 50%”（会导致均质空洞白框）。
  4. **色彩不写死固定色号，按「存量继承」或「无彩色骨架＋低明度重色锚点＋单峰高亮」的范围法则动态调配**：
     - **为什么生图容易缺乏现代高级感？** 当提示词未区分“界面骨架色”与“数据焦点色”时，模型会把导航、主按钮、整排图表柱和状态栏全部刷成同一种高饱和度亮色，瞬间沦为传统报表。
     - **存量项目（有既有界面、设计系统或指定品牌色）**：直接沿用存量项目的真实底色、主色与辅助色（配合 `--ref` 传入现状截图），仅用下方的主次比例关系组织新增内容。
     - **新建项目（无指定品牌色时）的色彩范围与比例（85 : 10 : 5）**：
       - **80–85% 无彩色画布与交互骨架**：浅色模式选自**高明度、极低彩度的纯净白或微冷/微暖浅中性色范围**（深色模式选自极低明度的深邃炭黑/暗岩色范围）；全局导航选中态、主操作按钮以及图表中的非核心基准项（历史对比柱、背景轨道、次要分段）统一交由**哑光深黑/炭灰与柔和中性浅灰（或斜纹灰）**承担（`matte-black active controls and soft neutral-gray inactive elements`）。
       - **10–15% 单个低明度重色锚点**：全图只设 **1 处高反差视觉重心**（单张聚焦卡、右侧独立工具/卡包面板或底部日志抽屉）。色相随行业与产品气质自由选择，但明度须压入**沉稳深色区间**（如哑光曜石黑，或低明度、低荧光感的深林绿、深海青、深靛蓝、暗酒红、深岩灰等），不拉通栏高饱和亮色大横幅。
       - **5% 单点信号高亮**：在整排灰色图表柱、分段条或状态胶囊中，**只点亮最关键的 1 根峰值柱或少量焦点胶囊**（色相在与重色锚点呼应或形成克制冷暖/明暗反差的现代点缀色范围内自选），其余同级数据项一律退回浅灰或斜纹灰。
  5. **用「2–3 个具象图形微组件」替代干瘪的大表格与细折线**：根据当前页面的真实数据关系，从下方槽位中挑选 2–3 个图形构件组合，不拘泥于 Bento 网格。

### 通用填空式生图母模板与开放槽位指南

编写生图提示词时，按以下 **5 槽位填空模板** 组装（整段控制在 45–65 词，按具体产品在对应范围内灵活填空，不照抄固定配色或固定组件）：

```text
<1. 调性与页面形态> UI design (<输出尺寸，如 1536x1024>) inside a clean rounded desktop window, Simplified Chinese interface for <产品领域简述>. Delicate small-scale desktop proportions, petite typography, and generous open whitespace. <2. 画布底色范围与无彩色控件骨架> with <3. 导航与主体布局结构>, anchored by <4. 单个低明度重色锚点与 5% 单点高亮色（按产品气质在对应范围内自选，或沿用存量品牌色）>, featuring <5. 2–3 个匹配业务的图形化微组件（非核心项保持浅灰或斜纹）>, clean abstract icons, no third-party brand logos.
```

| 填空槽位 | 范围与洞察原则（不写死单一套餐） | 英文表达结构与可选范围 |
| --- | --- | --- |
| **1. `<调性与页面形态>`** | 按当前页面承担的真实角色定调；完整落地页长图须写明“从顶栏到页脚的桌面纵向长图”，防止被画成手机屏或海报 | 工作台与数据大盘：`Sleek, high-craft SaaS dashboard` / `Crisp modern analytics workspace`<br>开发与诊断工具：`Minimal, precision developer workbench`<br>品牌官网首屏：`High-taste modern landing page hero`<br>完整桌面落地页长图（`1024x1536`）：`Full-length desktop landing page UI design (1024x1536 vertical scroll view from top navbar to footer)`<br>独立模块：`Focused UI component module` |
| **2. `<画布底色范围与无彩色骨架>`** | **新建项目**按产品气质在纯净白、暖亚麻纸白、冷石白或深邃炭黑/曜石黑等低彩度底色范围内选择，并声明**哑光黑/炭灰交互控件＋中性浅灰辅助元素**；**存量项目**直接填既有底色与视觉变量 | 新建浅色／画报底色范围：`Spacious <pure-white / warm archival paper / cool stone-white / soft sand-linen> canvas with matte-black active controls and soft neutral-gray secondary elements`<br>新建深色／影院底色范围：`Deep <obsidian / carbon-slate / matte-espresso> canvas with subtle hairline borders and muted gray secondary elements`<br>存量项目继承：`Existing <存量底色描述> canvas preserving the project's <存量主辅色与组件特征> visual tokens` |
| **3. `<导航与主体布局结构>`** | 工作区按浏览顺序选结构，不默认套 Bento 卡片墙；落地页按 [说服型骨架](direction-persuasion.md) 选首屏骨架与跨屏节奏，不默认左右对半切分 | 工作区结构：`a slim icon rail and open analytical workspace` / `a compact left sidebar and asymmetric modules` / `a narrow left queue and continuous right inspection stage` / `an unboxed flow structured by 1px hairline dividers`<br>落地页多样首屏与跨屏结构：`centered sculptural hero object with generous surrounding space` / `full-bleed editorial visual stage with overlaid display typography` / `oversized architectural typography spanning the grid` / `product interface or tactile instrument as the hero stage`，向下衔接 `staggered editorial narrative flow, frameless spec list, and signature closing CTA carrier with footer` |
| **4. `<单个重色锚点与单点高亮范围>`** | 全图只设 **1 处**重色重心（哑光黑或契合产品气质的**低明度浓郁深色区块/主视觉载体**），搭配 **5% 单峰/单点强调色**；或直接沿用存量品牌色 | 单张重色聚焦卡／主视觉载体：`a single <matte-obsidian / deep low-value tone fitting the domain> spotlight card (or hero showcase stage) and subtle <contrasting or tonal modern accent> pills`<br>右侧独立面板＋单柱高亮：`a sleek dark-charcoal <virtual card / inspector> panel and a single <modern accent hue> highlighted peak column`<br>深色通栏点睛区块（长页适用）：`one deep <low-value domain hue> contrast section anchoring the vertical rhythm, with a single <accent hue> primary CTA pill`<br>存量品牌色继承：`one <存量品牌主色描述> focal card with restrained matching highlights` |
| **5. `<2–3 个图形化微组件>`** | 按页面要回答的问题任选 2–3 项；工作区图表非核心项退回浅灰或斜纹灰，落地页选用契合品类的实样、图解或凭据载体 | 工作区数据构件：`one refined primary figure with muted gray decimals` / `vertical pill-shaped capsule charts where most bars are soft diagonal-hatched gray and only one peak bar is highlighted` / `a horizontal segmented capsule bar` / `a circular tick-marked radial dial` / `a clean visual node routing flow` / `compact aligned rows with subtle status pills`<br>落地页叙事与实证构件：`staggered editorial photography and anatomical diagram callouts` / `frameless hairline specification ledger` / `tactile interactive product micro-cards or audio/hardware controls` / `a ticket-style or terminal-command closing CTA block and monumental wordmark footer` |

- 类比应描述体验或组织方式，而非堆叠风格名。若“杂志”“生活方式”带入无关静物、纸纹或口号，移除歧义，不继续堆修饰词。
- 参考字体拆成字形、字重、比例与间距，不把英文字体类别直接翻译为中文宋体或手写字。没有既有规范时选择少量自洽规则，不把某一套配色、材质或字体固定为所有产品的套餐。
- **存量项目局部改版或新增页面时**：
  - **无参考图（延续既有品牌规范新建页面）**：直接在上方 5 槽位模板的槽位 2 与槽位 4 中填入存量项目的真实底色与品牌主色。
  - **带 `--ref` 传入存量截图（改图模式）**：以明确的变化指令开头——`Keep the reference image's exact <保留的侧栏/顶栏与小比例规范> and <存量主辅色描述> palette, but completely replace <目标区域> with a new Simplified Chinese subpage for <新页面领域>. Feature <槽位 4 重心锚点> and <槽位 5 图形微组件>, clean abstract icons, no third-party brand logos.`

隐藏交互与其他状态保留在设计说明中，不要求全部画进一张图。

## 完整落地页与分段长图

完整桌面落地页保持桌面内容宽度，向下展开至页脚；用户明确只要首屏或独立区块时才缩小范围。**竖向长图（`1024x1536`）是桌面端完整网页的纵向滚动全貌，绝不是移动端 App 页面，也不是把所有模块挤进一张竖版海报或套用千篇一律的 SaaS 卡片墙。**

1. **先定产品气质、首屏骨架与 4 段纵向节奏**：
   - 按 [说服型骨架](direction-persuasion.md) 选择与产品匹配的**首屏构图**（如居中器物/实样、满版影像压字、画面即界面/乐器/硬件、跨栏巨型排字、瑞士网格拼贴、左文右图特写等），不同产品绝不重复同一种首屏套路。
   - 安排从顶栏到页脚的 **4 个异构纵向区块**（例如：① 顶栏＋首屏主舞台 → ② 高低错落画报叙事或剖面图解 → ③ 无框细线规格台账或可交互产品实样 → ④ 专属行动载体如凭据卡/终端命令卡＋大字标页脚），相邻两屏不共用同一种构图。
2. **按接口能力选整张或分段（同样遵循 45–65 词精简法则）**：
   - 画布在可读字号下能容纳本次区块时，直接用纵向画布（`--size 1024x1536`）一次生成，并在提示词开头明确声明 `Full-length desktop landing page UI design (1024x1536 vertical scroll view from top navbar to footer), wide desktop layout proportions, NOT a mobile screen`，同时锁死 `delicate small-scale desktop proportions, petite body typography contrasted with expressive display headlines, generous open whitespace`。
   - 页面极长、一次生成会让正文过小时，在区块边界分段（如 `--size 1536x1024`）。先生成并检查第一段，把统一规则和第一段参考（`--ref`）用于后续片段；每次提示明确本段包含哪些区块、是否含导航或页脚，接缝处不重复标题或顶栏。

## 检查、测量与响应式实现

生成后实际打开图片，在目标逻辑视口尺度检查范围与内容、视觉构思、层级与可读性、一致性及实现边界。每轮指出一个主要问题、应保留的特色与要改变的变量；纹理、颗粒和光晕只在明确风格需要时使用，不作为提升设计感的通用补丁。

将生图设计稿转化为 HTML/CSS 或接入存量前端项目时，**生图稿是“风格、配色与排版骨架参考”，不是需要一比一像素描红的死板图纸**。严禁拿整张位图当页面背景，也严禁用大量任意定位（`position: absolute`）锁死像素去复刻生图被压缩的纵向间距或畸形小字：

1. **只采样色板与横向比例，不照搬生图被压缩的纵向间距**：
   AI 生图（尤其是 `1024×1536` 多区块落地页长图）为了在单张图片高度内塞下 4–6 个模块，必然会把模块之间的上下内边距压缩到真实网页的 1/3～1/2。用 `measure_reference.py` 时，**只采样主辅色板（`--color`）、参考横向分栏比例，或裁出确实需要的独立摄影/插画素材（`--extract`，可配 `--white-to-alpha` 或 `--key-color`）**，绝不照搬生图里的纵向区块高度与上下间距：
   ```bash
   python3 <skill>/scripts/measure_reference.py <设计图.png> \
     --color bg=20,20,100,40 --box main=40,120,960,640 --css-width 1440
   ```
2. **按真实桌面 UI 尺度主动舒展上下内边距（拉开纵向呼吸感）**：
   - **完整落地页／品牌长页**：首屏给足舒适的桌面视口尺度（如 `min-height: clamp(640px, 82vh, 880px)`），后续每个模块必须主动放大上下内边距（`padding-block: clamp(88px, 9vw, 136px)`），模块标题与内容区之间保持 `40px–64px` 间距，让整页在 `1440px` 视口下自然展开到 `3200px–4800px` 的真实网页高度，消除生图模块挨得过近的局促感。
   - **后台与产品工作区**：去掉生图外围的窗口外框与画布留边，让界面自然铺满视口；主画布与卡片间距保持 `20px–28px`，卡片内边距保持 `22px–28px`，表格与列表单行高度保持 `44px–56px` 的真实可点击尺度。
   - **存量项目**：默认在现有路由、组件树、样式系统与设计变量内实现；现有组件能表达时只调整布局和设计变量，不因参考图复杂就重建整套组件库。
3. **文案合理润色与彻底清除非汉字伪字**：
   生图中的小字常有笔画粘连的“伪汉字/非汉字乱码”、繁体字或生硬词句。实现代码时，**只沿用原图的字号层级对比与段落节奏，允许自由微调、润色和补全具体文案**：所有伪造乱码字符、非汉字杂乱符号与繁体字必须 100% 替换为自然通顺的规范简体中文（仅在确有需要时保留 `VCO`、`AUV`、`HRV`、`USD` 等标准英文缩写），绝不死板照抄图内文字。
4. **真实画面与操作复验**：
   按 [工具](tools.md) 用 `shoot.mjs` 在桌面与窄屏视口检查实际渲染并操作主要流程：确认真正用于字符渲染的字体、行高、模块上下留白、对比度和换行符合真实 UI 标准，长文本、列表增长与窄屏切换均不破坏布局。
