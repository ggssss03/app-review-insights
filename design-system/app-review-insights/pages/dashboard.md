# Dashboard Page Override — App Review Insights

> 覆盖 MASTER.md：本页面采用「Cinema Dark × Holographic × Bento」方向。
> 依据 ui-ux-pro-max 检索：style=Modern Dark (Cinema Mobile) / Glassmorphism /
> HUD Sci-Fi FUI；motion=Complex 档；产品=AI 数据分析仪表盘。

## 方向

- 首屏为「电影感 Hero + 命令舱表单」：大标题渐变 + 全息光晕 + S0→S8 流水线条。
- 摘要页使用 Bento Grid：5 张 KPI 卡（前 3 张 span 2，后 2 张 span 3）+ 分布面板 +
  范围卡 + 溯源卡。
- 结果卡片带 3D 倾斜（pointer 跟随，5deg 内）与顶部全息高光。

## 色板（暗色，覆盖 MASTER 亮色）

| Token | 值 | 用途 |
|-------|-----|------|
| `--bg-0` | `#04060f` | 页面底色 |
| `--glass` | `rgba(255,255,255,.045)` | 卡片玻璃面 |
| `--text` | `#eef1f8` | 主文本（对比度 > 12:1） |
| `--muted` | `#9aa5b8` | 次要文本（≈7:1） |
| `--cyan` | `#22d3ee` | 主强调 / 统计徽章 |
| `--violet` | `#a78bfa` | 模型徽章 / 极光 |
| `--magenta` | `#f472b6` | 全息渐变第三色 |
| `--emerald` | `#34d399` | 成功 / OK 状态 |
| `--amber` / `--red` | `#fbbf24` / `#f87171` | 警告 / 错误 |
| `--holo` | `linear-gradient(120deg, cyan, violet, magenta, emerald)` | 标题 / 主 CTA / 数字 |

## 字体

- 展示：`Space Grotesk`（未安装则回落系统无衬线，中文走 `Microsoft YaHei`）。
- 数据/标签：等宽栈（Cascadia Code / Consolas）。
- 不引入外部字体依赖（面试离线演示安全）。

## 动效（Complex 档，纯 CSS + 原生 JS）

- 极光 blobs 漂移、网格缓动、神经星座粒子 + 流星、表单旋转渐变描边（`@property --a`）。
- Hero 标题 blur→clear 入场、流水线 chips 逐级浮现、Tab 内容 stagger。
- 卡片 3D 倾斜、主按钮磁吸、光标全息光晕。
- 全部动画在 `prefers-reduced-motion` 下关闭；粒子/倾斜/磁吸/光晕同时由 JS 检测跳过。

## 禁止项（继承 MASTER）

- 不用 emoji 当图标（全部 SVG）；点击元素 `cursor:pointer`；焦点环可见；
  hover/press 150–300ms；375/768/1024/1440 断点；无横向滚动。
