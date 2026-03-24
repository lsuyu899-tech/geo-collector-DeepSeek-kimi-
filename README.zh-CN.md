# GEO Collector Standalone（发布版说明）

一个可独立运行、可直接上传 GitHub 的 AI 来源采集工具：

- 批量提问（CSV/TXT）
- 支持 Kimi / 豆包（方舟）/ DeepSeek
- 自动提取引用链接并标注来源渠道
- 自动输出渠道统计汇总
- 提供 GUI 和 CLI 两种运行方式

## 目录结构

- `collector.py`：核心采集脚本（CLI）
- `app.py`：图形界面（GUI）
- `run_app.bat`：GUI 启动器
- `run_cli.bat`：CLI 启动器
- `questions.csv`：示例问题文件
- `LICENSE`：MIT 许可证
- `.gitignore`：Git 忽略规则

## 环境要求

- Windows
- Python 3.6+
- 无第三方依赖（仅标准库）

## 快速开始（GUI，推荐）

1. 双击 `run_app.bat`
2. 配置：
   - 问题文件（如 `questions.csv`）
   - 输出文件（如 `results.csv`）
   - API Key（MOONSHOT/ARK/DEEPSEEK）
   - 模型参数（Kimi 模型、豆包模型/接入点、并发 Workers）
3. 点击“开始运行”

## 快速开始（CLI）

双击 `run_cli.bat`，按提示输入参数即可。

## GitHub 新手上传指南

请看：[GITHUB_UPLOAD_GUIDE.zh-CN.md](./GITHUB_UPLOAD_GUIDE.zh-CN.md)

## 输入格式

支持两种：

1. `questions.txt`：每行一个问题
2. `questions.csv`：默认问题列名为 `question`

示例：

```csv
question
期货培训哪家好
做期货总是亏钱怎么办
期货新手入门从哪里开始学
```

## 输出文件

运行后会生成：

1. 主结果表：你设置的输出文件（如 `results.csv`）
2. 渠道汇总表：`<输出文件名>_渠道统计汇总.csv`

主结果包含：

- 三个平台回答
- 来源链接、来源渠道、渠道标注链接
- 平台状态（成功/跳过/报错）
- 耗时、采集时间

## 安全建议

1. 不要把真实 API Key 写入代码或提交到 GitHub。
2. `settings.json` 不保存 API Key，但也建议加入 `.gitignore`（已处理）。
3. 若 key 泄露，请第一时间在平台控制台重置。

## 常见问题

1. Kimi 报 temperature 限制：脚本已支持自动适配指定温度重试。
2. 豆包报 `ToolNotOpen`：需先在方舟开通联网内容插件。
3. DeepSeek 来源较少：API 侧和 App 联网能力机制不同，属预期现象。

## 许可证

[MIT License](./LICENSE)
