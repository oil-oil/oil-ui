# 生图设计与还原校准

返回 [主入口](../SKILL.md)。先用生图探索或锁定界面的构图、比例、留白与色彩关系，再将设计图作为视觉基线转化为可运行、响应式的代码或接入存量项目。视觉质量与业务完整性分别验收，不能用内容齐全、对齐规整替代设计成立。

## 目录导航

- [何时探测生图能力并让用户选择](#何时探测生图能力并让用户选择)
- [参考图策略与组件素材边界](#参考图策略与组件素材边界)
- [视觉构思、视口比例与提示词组织](#视觉构思视口比例与提示词组织)
- [完整落地页与分段长图](#完整落地页与分段长图)
- [检查、测量与响应式实现](#检查测量与响应式实现)

## 何时探测生图能力并让用户选择

新建界面、多方向视觉探索或存量重塑时，按 [主入口](../SKILL.md#选择范围) 先读 `oiloil-image.mjs pref` 并探测生图能力：已有 `oiloil` 或 `host` 偏好时直接沿用（余额不足或登录失效则自动回退宿主）；仅在 `unset` 且双工具同时可用时，在确认点让用户选一次并用 `pref set` 记住；两边均不可用时静默走代码流程，不报错、不索要密钥。

确认可用且用户未指定是否先生图时，把方向方案、首次工具选择（仅 `unset` 且双工具可用时）与以下三选一合并成全流程**唯一一次确认**（走 Oil 积分时在第 1、3 项写明耗积分，选了即算本任务授权）：

1. **（推荐）先按此方案生成 UI 设计稿，并直接完成响应式代码实现**
2. **跳过生图，直接按此方案用代码实现界面**
3. **仅生成 UI 设计稿（暂不写代码）**

选第 1 项后连续完成出图、代码与真实画面验证，中途不再二次停顿；CLI 登录、回退策略、6 并发上限、单引号 `--prompt` 与 `--ref` 用法统一见 [素材](media.md#复用生成还是交给代码)。

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

### 区分逻辑视口与输出像素（工作区与快速草图的 50 词短提示词法则）

逻辑视口、文档高度和生成像素分别记录：

- 移动端 `390×844` 的逻辑视口可以生成 `1024×1536` 的图片，但不能把生成图的 `1024` 像素宽当作手机布局宽；桌面长页数千像素的高度也不是桌面视口高度。
- **后台工作台、SaaS 控制台、独立组件模块以及低成本单张草图**，生图提示词遵循「45–65 词精简法则」与下方 `85 : 10 : 5` 色彩配比（注：需要强艺术指导的多屏品牌落地页不适用把 4 屏压成 50 词的做法，应按下一节逐屏分段生成）：
  1. **控长度（45–65 词，2–3 句话）**：只定义“结构关系、比例留白、色彩角色范围与图形构件”，不写长篇逐行线框图说明书，把自然排版与构图权还给模型。
  2. **不塞具体引号文案与外部品牌配对**：在提示词中罗列十几个中文标题或具体数值，会迫使模型为了画清每个汉字而将全局字号与容器放大 1.5 倍；指定真实外部品牌配对则极易画错图标。生图阶段只写领域与界面语言（`<界面语言> interface for <产品领域>`，例如中文产品写 `Simplified Chinese`）及通用图标约束（`clean abstract icons, no third-party brand logos`），具体业务文案与真实身份素材留到代码阶段实现。
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
<1. 调性与页面形态> UI design (<输出尺寸，如 1536x1024>) inside a clean rounded desktop window, <界面语言> interface for <产品领域简述>. Delicate small-scale desktop proportions, petite typography, and generous open whitespace. <2. 画布底色范围与无彩色控件骨架> with <3. 导航与主体布局结构>, anchored by <4. 单个低明度重色锚点与 5% 单点高亮色（按产品气质在对应范围内自选，或沿用存量品牌色）>, featuring <5. 2–3 个匹配业务的图形化微组件（非核心项保持浅灰或斜纹）>, clean abstract icons, no third-party brand logos.
```

| 填空槽位 | 范围与洞察原则（不写死单一套餐） | 英文表达结构与可选范围 |
| --- | --- | --- |
| **1. `<调性与页面形态>`** | 按当前页面承担的真实角色定调；完整落地页长图须写明“从顶栏到页脚的桌面纵向长图”，防止被画成手机屏或海报 | 工作台与数据大盘：`Sleek, high-craft SaaS dashboard` / `Crisp modern analytics workspace`<br>开发与诊断工具：`Minimal, precision developer workbench`<br>品牌官网首屏：`High-taste modern landing page hero`<br>完整桌面落地页长图（`1024x1536`）：`Full-length desktop landing page UI design (1024x1536 vertical scroll view from top navbar to footer)`<br>独立模块：`Focused UI component module` |
| **2. `<画布底色范围与无彩色骨架>`** | **新建项目**按产品气质在纯净白、暖亚麻纸白、冷石白或深邃炭黑/曜石黑等低彩度底色范围内选择，并声明**哑光黑/炭灰交互控件＋中性浅灰辅助元素**；**存量项目**直接填既有底色与视觉变量 | 新建浅色／画报底色范围：`Spacious <pure-white / warm archival paper / cool stone-white / soft sand-linen> canvas with matte-black active controls and soft neutral-gray secondary elements`<br>新建深色／影院底色范围：`Deep <obsidian / carbon-slate / matte-espresso> canvas with subtle hairline borders and muted gray secondary elements`<br>存量项目继承：`Existing <存量底色描述> canvas preserving the project's <存量主辅色与组件特征> visual tokens` |
| **3. `<导航与主体布局结构>`** | 工作区按浏览顺序选结构，不默认套 Bento 卡片墙；落地页按 [说服型骨架](direction-persuasion.md) 选首屏骨架与跨屏节奏，不默认左右对半切分 | 工作区结构：`a slim icon rail and open analytical workspace` / `a compact left sidebar and asymmetric modules` / `a narrow left queue and continuous right inspection stage` / `an unboxed flow structured by 1px hairline dividers`<br>落地页多样首屏与跨屏结构：`centered sculptural hero object with generous surrounding space` / `full-bleed editorial visual stage with overlaid display typography` / `oversized architectural typography spanning the grid` / `product interface or tactile instrument as the hero stage`，向下衔接 `staggered editorial narrative flow, frameless spec list, and signature closing CTA carrier with footer` |
| **4. `<单个重色锚点与单点高亮范围>`** | 全图只设 **1 处**重色重心（哑光黑或契合产品气质的**低明度浓郁深色区块/主视觉载体**），搭配 **5% 单峰/单点强调色**；或直接沿用存量品牌色 | 单张重色聚焦卡／主视觉载体：`a single <matte-obsidian / deep low-value tone fitting the domain> spotlight card (or hero showcase stage) and subtle <contrasting or tonal modern accent> pills`<br>右侧独立面板＋单柱高亮：`a sleek dark-charcoal <virtual card / inspector> panel and a single <modern accent hue> highlighted peak column`<br>深色通栏点睛区块（长页适用）：`one deep <low-value domain hue> contrast section anchoring the vertical rhythm, with a single <accent hue> primary CTA pill`<br>存量品牌色继承：`one <存量品牌主色描述> focal card with restrained matching highlights` |
| **5. `<2–3 个图形化微组件>`** | 按页面要回答的问题任选 2–3 项；工作区图表非核心项退回浅灰或斜纹灰，落地页选用契合品类的实样、图解或专属载体 | 工作区数据构件：`one refined primary figure with muted gray decimals` / `vertical pill-shaped capsule charts where most bars are soft diagonal-hatched gray and only one peak bar is highlighted` / `a horizontal segmented capsule bar` / `a circular tick-marked radial dial` / `a clean visual node routing flow` / `compact aligned rows with subtle status pills`<br>落地页叙事与实证构件：`staggered editorial photography and anatomical diagram callouts` / `frameless hairline specification ledger` / `tactile interactive product micro-cards or audio/hardware controls` / `a signature closing CTA block drawn from the product's own world, with a footer in the same visual language` |

- 类比应描述体验或组织方式，而非堆叠风格名。若“杂志”“生活方式”带入无关静物、纸纹或口号，移除歧义，不继续堆修饰词。
- 参考字体拆成字形、字重、比例与间距，不把英文字体类别直接翻译为中文宋体或手写字。没有既有规范时选择少量自洽规则，不把某一套配色、材质或字体固定为所有产品的套餐。
- **存量项目局部改版或新增页面时**：
  - **无参考图（延续既有品牌规范新建页面）**：直接在上方 5 槽位模板的槽位 2 与槽位 4 中填入存量项目的真实底色与品牌主色。
  - **带 `--ref` 传入存量截图（改图模式）**：以明确的变化指令开头——`Keep the reference image's exact <保留的侧栏/顶栏与小比例规范> and <存量主辅色描述> palette, but completely replace <目标区域> with a new <界面语言> subpage for <新页面领域>. Feature <槽位 4 重心锚点> and <槽位 5 图形微组件>, clean abstract icons, no third-party brand logos.`

隐藏交互与其他状态保留在设计说明中，不要求全部画进一张图。

## 完整落地页与分段长图

完整桌面落地页保持桌面内容宽度，向下展开至页脚；用户明确只要首屏或独立区块时才缩小范围。**竖向长图（`1024x1536`）是桌面端完整网页的纵向滚动全貌，绝不是移动端 App 页面，也不是把所有模块挤进一张竖版海报或套用千篇一律的 SaaS 卡片墙。**

1. **先定产品气质、首屏骨架与 4 段纵向节奏**：
   - 按 [说服型骨架](direction-persuasion.md) 选择与产品匹配的**首屏构图**（如居中器物/实样、满版影像压字、画面即界面/乐器/硬件、跨栏巨型排字、瑞士网格拼贴、左文右图特写等），不同产品绝不重复同一种首屏套路。
   - 安排从顶栏到页脚的 **4 个左右的纵向区块**，每个区块长什么样从这个产品的内容和方向里推，相邻两屏不共用同一种构图，结尾的行动区和页脚不退回默认表单。
2. **正式多屏落地页优先「逐屏 `1536×1024` + 星型 `--ref`」，单张 `1024×1536` 仅作低成本快草图**：
   - **正式多屏落地页（推荐）**：按模块逐屏生成 `--size 1536x1024` 横图，避免单张竖图把微缩 UI 压糊。先生成并验收第一屏（`M1`），锁定品牌标、字体分轨、按钮圆角、色域与左右版心；生成 `M2`、`M3`、`M4` 等后续每一屏时，**全部直接把同一张 `M1` 作为 `--ref`（星型参考）**，不要采用 `M1 → M2 → M3` 链式接力（会造成字体与色温漂移）。每次提示写清本屏包含哪些区块、是否含导航或页脚、禁止重复顶栏，并确保相邻两屏不重复同一种地平线构图。
   - **低成本整页快草图（约 3 积分）**：仅在快速验证整体结构、预算极紧或只要概览草图时，用单张纵向画布（`--size 1024x1536`）一次生成，并在提示词开头明确声明 `Full-length desktop landing page UI design (1024x1536 vertical scroll view from top navbar to footer), wide desktop layout proportions, NOT a mobile screen`，同时锁死 `delicate small-scale desktop proportions, petite body typography contrasted with expressive display headlines, generous open whitespace`。

## 检查、测量与响应式实现

生成后实际打开图片，在目标逻辑视口尺度检查范围与内容、视觉构思、层级与可读性、一致性及实现边界。每轮指出一个主要问题、应保留的特色与要改变的变量；纹理、颗粒和光晕只在明确风格需要时使用，不作为提升设计感的通用补丁。

将生图设计稿转化为 HTML/CSS 或接入存量前端项目时，**生图稿是“风格、配色与排版骨架参考”，不是需要一比一像素描红的死板图纸**。严禁拿整张位图当页面背景，也严禁用大量任意定位（`position: absolute`）锁死像素去复刻生图被压缩的纵向间距或畸形小字：

1. **纯净底图净板重绘与比例锁（严禁凭纯文字画跑偏，也严禁裁切模糊背景）**：
   - **不要从画满文字/UI 的设计稿硬裁模糊局部当背景，也不要只靠文字提示词凭空另画底图**（纯文字另画极易导致主体缩水、光影色温漂移、和原设计稿判若两图）。正确做法是把已验收的单屏设计稿作为 `--ref` 传入生图工具，指令为**「严格保留参考图的主体造型、尺幅、机位、光影与色彩科学，仅彻底清除全部文字、顶栏、按钮、微缩控制台与图表，并在原位自然补全干净背景」**，产出高分辨率、构图 100% 忠于原稿的无字纯净底图（clean art plate）；所有文字、按钮、表单、图表与微缩控制台一律由代码实现为真实可交互 HTML/CSS/SVG。
   - **锁定 5 项硬比例，防止设计感被比例失真吃掉**：
     - **图字纵向占比**：若原稿上幅艺术区占首屏 `50–56%`（如 `H2` 上画下字），真实页面在 `1440×900` 下必须保住相近高度（`450–504px`），绝不压扁成 `320px` 窄条；地平线高度百分比与原稿对齐。
     - **主体尺幅与边缘出血**：若原稿主体（植物、雕塑、硬件、建筑）占首屏 `50–60%` 高度并从底边或右边干净出血，代码容器必须保持同等大尺幅并贴边出血，绝不缩成中间一块周围空荡荡的小贴纸。
     - **底图与容器同比例**：按卡片真实容器宽高比（如竖卡 `3:4`、宽卡 `4:3` 或 `16:10`）准备对应比例的纯净底图，避免 `object-fit: cover` 把主体关键轮廓裁残。
     - **明亮天空不压脏暗渐变**：浅色/晴空首屏为了顶栏可读，优先用高对比深墨字或高质感胶囊按钮，不要整条拉厚重的深灰/深蓝顶渐变把画面涂暗涂脏。
     - **保留前后景遮挡关系（三层空间深度）**：凡是原稿中存在前景草叶、花瓣、云雾、岩缘或器物压在 UI 窗口/大字前方的构图，严禁把 UI 死板平贴在背景图之上；应基于原稿生成一张**真透明背景的前景遮挡层**（顶部透明留空、仅底部/边缘保留自然不规则轮廓的实体前景），在页面中按「远景底图 `z-index: 0` → 真实 UI 层 `z-index: 2` → 透明前景层 `z-index: 3; pointer-events: none`」叠放并配合多速视差滚动，让 UI 真正“长进”画面里。
   - 使用 `measure_reference.py` 采样主辅色板（`--color`）与横向分栏比例；`--extract` 仅用于像素充足、完全干净无字的独立物件素材（可配 `--white-to-alpha` 或 `--key-color`），绝不照搬单张竖图草图里被压缩的纵向模块间距：
   ```bash
   python3 <skill>/scripts/measure_reference.py <设计图.png> \
     --color bg=20,20,100,40 --box main=40,120,960,640 --css-width 1440
   ```
2. **按真实桌面 UI 尺度主动舒展上下内边距与对比度护栏**：
   - **完整落地页／品牌长页**：首屏给足舒适的桌面视口尺度（如 `min-height: clamp(640px, 82vh, 880px)`），后续每个模块必须主动放大上下内边距（`padding-block: clamp(88px, 9vw, 136px)`），模块标题与内容区之间保持 `40px–64px` 间距，让整页在 `1440px` 视口下自然展开到 `3200px–4800px` 的真实网页高度，消除生图模块挨得过近的局促感。
   - **图文叠加护栏**：浅色文字或微组件叠在摄影/艺术底图上时，必须用克制的渐隐暗层（subtle bottom/top scrim）保证小号正文对比度达到 WCAG AA（`>= 4.5:1`）；现代画廊页脚保持无边框留白，不强加刺眼通栏硬分割线；状态圆点跟随页面主强调色，不默认硬塞无关绿点。
   - **后台与产品工作区**：去掉生图外围的窗口外框与画布留边，让界面自然铺满视口；主画布与卡片间距保持 `20px–28px`，卡片内边距保持 `22px–28px`，表格与列表单行高度保持 `44px–56px` 的真实可点击尺度。
   - **存量项目**：默认在现有路由、组件树、样式系统与设计变量内实现；现有组件能表达时只调整布局和设计变量，不因参考图复杂就重建整套组件库。
3. **文案重写，清掉伪字与假品牌**：
   生图中的小字常有笔画粘连的乱码伪字、用错的字形或生硬词句，偶发还会混入真实第三方品牌名。实现代码时，**只沿用原图的字号层级对比与段落节奏，允许自由微调、润色和补全具体文案**：乱码伪字、杂乱符号和真实第三方 Logo/品牌名全部替换为自然通顺的产品文案与虚构合作方名。
4. **真实画面与「原稿 vs 还原」并排复验**：
   按 [工具](tools.md) 用 `shoot.mjs` 在桌面与窄屏视口检查实际渲染并操作主要流程；**有生图参考稿时，额外用 `shoot.mjs --stitch 原设计稿.png --label 原稿 --stitch 还原首屏.png --label 还原` 生成并排对比图亲自看一眼**，重点核对主体尺幅、图字纵向占比、边缘出血、画面明暗色温与微缩 UI 比例是否忠于原稿，发现主体缩水或天空发脏立即修齐再交付。
