# GitHub 上传新手指南（一步一步）

这份指南按“第一次使用 GitHub”的场景写，照做即可。

## 0. 准备

1. 注册 GitHub 账号（如果还没有）
2. 安装 Git（Windows）
3. 打开终端（PowerShell）

## 1. 进入项目目录

```powershell
cd D:\codex\GEO\GEO_Collector_Standalone
```

## 2. 初始化本地仓库

```powershell
git init
git branch -M main
```

## 3. 添加文件并提交

```powershell
git add .
git commit -m "Initial release: GEO Collector Standalone"
```

如果提示没有用户名和邮箱，先设置：

```powershell
git config --global user.name "你的GitHub用户名"
git config --global user.email "你的GitHub邮箱"
```

然后再执行一次 `git commit`。

## 4. 在 GitHub 网站创建新仓库

1. 登录 GitHub
2. 点击右上角 `+` -> `New repository`
3. 仓库名建议：`geo-collector-standalone`
4. 选择 `Public`（或按你需求选 Private）
5. 不要勾选 Initialize README（因为本地已经有）
6. 点击 `Create repository`

## 5. 关联远程仓库并推送

把下面 URL 换成你的仓库地址：

```powershell
git remote add origin https://github.com/你的用户名/geo-collector-standalone.git
git push -u origin main
```

## 6. 上传后检查

你应当能在仓库首页看到：

- `README.md`
- `README.zh-CN.md`
- `README.en.md`
- `LICENSE`
- `collector.py`
- `app.py`

## 7. 后续更新（每次改完代码）

```powershell
git add .
git commit -m "你的更新说明"
git push
```

## 常见报错

1. `fatal: not a git repository`
   - 你不在项目目录，先 `cd` 到 `GEO_Collector_Standalone`。
2. `remote origin already exists`
   - 先执行：`git remote remove origin`，再重新 `git remote add origin ...`
3. `failed to push some refs`
   - 先执行：`git pull --rebase origin main`，再 `git push`

## 安全提醒

1. 不要把真实 API Key 放进代码。
2. 提交前检查：`git status`
3. 如果不小心提交了 key：立即在平台重置，并改写历史（可再找我帮你做）。
