# DataQuery Copilot v0 设计系统

## 定位

- **方向**：Modern Tool / Builder SaaS，参考 Linear 的克制工具感，但不复制其品牌。
- **叙事角色**：访问后直接进入工作台，不设置营销封面。
- **主要场景**：桌面端作品集演示，同时支持平板和手机浏览。
- **视觉温度**：冷静、专业、精确；数据和执行过程是视觉主角。

## 设计令牌

| 类别 | 取值 |
|---|---|
| Ground | `#08090A` |
| Surface 1 | `#111217` |
| Surface 2 | `#16171C` |
| Surface 3 | `#1E1F25` |
| Border | `rgba(255, 255, 255, 0.07)` |
| Primary text | `#F7F8F8` |
| Secondary text | `#9CA3AF` |
| Muted text | `#686B76` |
| Accent | `#7C86E8` |
| Success | `#55B993` |
| Warning | `#D7A55C` |
| Display font | `Inter Tight` / fallback sans-serif |
| Body font | `Inter` / fallback sans-serif |
| Mono font | `JetBrains Mono` / fallback monospace |
| Spacing | `4 / 8 / 12 / 16 / 24 / 40 / 64` |
| Radius | `6 / 12 / 16` |
| Motion | `150ms ease-out` / `400ms cubic-bezier(0.22, 1, 0.36, 1)` |

## 页面结构

桌面采用三栏工作台：

1. 左栏承载数据集、Schema 和数据质量入口。
2. 中栏承载自然语言输入、结果表格和图表。
3. 右栏承载生成 SQL、执行元信息和查询阶段。

平板收敛为两栏，执行详情移动到结果下方；手机改为单栏并使用顶部横向标签导航。

## v0 内容边界

- 健康状态、Schema 和质量报告读取真实 FastAPI 接口。
- 查询输入具备完整交互外观，但 v0 不调用 DeepSeek。
- 结果表格、SQL 和图表使用明确标记的演示快照，验证信息架构与视觉密度。
- 不实现数据上传、历史持久化、导出和图表编辑。
