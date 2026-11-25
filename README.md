# RepoLens

当前上传版本为最初的 v0.1 MVP 基线，提供按日期范围的基础统计与变化报告；不包含独立 Sprint 创建/编辑/切换、Sprint 报告联动或 changed methods 展示。

基于 PyDriller 的 Git 仓库演化可视化与智能摘要工具，支持公开 GitHub 链接和本地仓库。当前版本是可运行 MVP，使用 Python、Streamlit、Plotly、pandas 和 SQLite。

## 启动

需要 Python 3.11+ 和已加入 PATH 的 Git。推荐 Python 3.12。

在项目目录内打开 Windows PowerShell：

```powershell
.\setup.ps1
.\run.ps1
```

如果系统策略阻止脚本执行，可以对这一次进程执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

浏览器访问 http://localhost:8501 。在启动终端按 Ctrl+C 停止。端口被占用时可运行 `.\run.ps1 --server.port 8502`。

跨平台手动启动：

```bash
python -m venv .venv
# 激活该虚拟环境，然后运行：
python -m pip install -r requirements.lock
python -m streamlit run app.py
```

`requirements.lock` 固定本次验证使用的运行依赖；`requirements.txt` 保留直接依赖范围。

## 第一次体验

1. 点击左侧「载入演示仓库」。首次点击会创建 `data/demo_repository`，包含 18 条合成提交、3 名作者、两个分支和两个标签。
2. 在概览查看时间线、模块变动与文件排行。
3. 选择日期、开发者、模块，所有页面使用同一组筛选结果。
4. 在「文件与提交」查看提交说明、文件修改类型和文本 diff。
5. 在「变化报告」直接下载统计报告；无模型时不会伪装成 AI 摘要。
6. 使用自己的仓库时，输入绝对路径，点击「读取仓库」，选择分支与采集上限，再点击「分析仓库」。

## 直接分析别人的 GitHub 仓库

无需是仓库作者，也不需要手动 clone：

1. 左侧「仓库来源」选择「GitHub 链接」。
2. 输入仓库首页链接，例如 `https://github.com/ishepard/pydriller`，带 `.git` 后缀也可以。
3. 分支留空使用默认分支，或输入具体分支名。不要粘贴 `/tree/`、`/blob/`、issue 或 PR 页面链接。
4. 设置下载历史深度，建议第一次用 50–100。
5. 点击「下载并分析」，完成后直接浏览图表、筛选和报告。

只支持公开仓库，不需要 GitHub Token。分析公开历史不需要 AI API；生成 AI 摘要才需要另行配置模型。

工具使用 Git HTTPS 下载，保存到自己的 `data/github_repositories/`，不会上传修改，也不会执行仓库中的程序或安装其依赖。缓存不 checkout 工作文件，只保存分析所需的 Git 对象。相同地址、分支和深度可复用下载；勾选「从 GitHub 更新已有下载」后再点击按钮，会更新该工具缓存，原有分析快照仍保留。

下载历史深度限制从远端获取的历史范围，「最多采集提交数」限制从已下载历史中分析多少条。两者不同；图表只代表本次已采集范围。首次只下载指定或默认分支，其他分支需要在下载分支字段中填写后重新下载。

浅克隆中缺少父提交的边界已排除，否则 Git 可能把整个文件误算成新增。因此浅克隆的可分析提交数可能小于下载深度。界面和报告会明确显示部分历史的限制。要分析更早的历史，可增大下载深度，或使用已完整 clone 的本地仓库。

首次下载耗时取决于仓库大小与本机连接 GitHub 的网络。网络错误或 120 秒超时会显示提示，失败的临时目录会清理，不会缓存半成品，也不会弹出登录窗口。

下载时自动检测并使用 Windows 已启用的手动系统代理，页面无需配置代理。未检测到受支持的系统代理时，使用 Git 原有网络配置。代理仅通过当前 Git 命令的临时配置生效，不修改系统或全局 Git 设置，也不影响 AI 接口。暂不自动解析 PAC 脚本，也不处理带账号密码的代理。

被分析仓库保持原分支和工作目录。采集不执行 checkout、不写入源码或仓库配置；SQLite 与演示数据写入 RepoLens 自己的 `data/`。

## 已实现

- 本地仓库校验、分支选择、固定 tip 快照。
- 公开 GitHub 仓库 URL 下载、指定分支、浅克隆深度、缓存复用与更新。
- 最多采集 1–2,000 条提交，可选择是否将 merge 计入提交数。
- SQLite 快照缓存与最近分析恢复。
- 按含首尾日期、作者和首级目录筛选。
- 每日提交趋势、代码增删趋势、模块变化量。
- 开发者提交数、涉及文件、参与模块和增删行数。
- 文件修改排行，提交 message、文件列表与 diff。
- 明确标注的程序统计报告、Markdown 导出。
- 可选的真实模型调用、结构化摘要、commit/file 引用校验、摘要缓存。
- 一键载入的合成演示仓库。

## 配置 AI（可选）

从左侧「AI 模型设置」输入：

- **API Base URL**：兼容 Chat Completions 的接口基础路径，例如 `https://api.openai.com/v1`；不要重复添加 `/chat/completions`。
- **模型名称**：填写账号可用的实际模型 ID，不预设某个模型。
- **API Key**：服务商密钥；本机服务可留空。

也可以复制 `.env.example` 为 `.env`，填写对应环境变量后重启。`.env` 已被 Git 忽略。项目不会读取或复用 Codex 登录凭据。

在报告页面，确认发送范围并勾选同意后，点击「生成 AI 摘要」。只有这个动作会调用模型。报告输入包含统计、提交说明、文件路径、增删行数及部分 diff；独立作者姓名和 email 字段不发送，但原始 message 或代码中仍可能包含这些内容。

接口需要支持 `POST /chat/completions` 和 `response_format: {"type":"json_object"}`。本机服务允许 HTTP；其他地址要求 HTTPS。密钥仅在当前进程/会话使用，不写入 SQLite。模型错误不会影响图表及统计报告。

MVP 使用一次有输入预算的模型请求：

- 最多提供 40 条包含文件变化的提交；更多时按时间跨度均匀采样。
- 每条最多选 8 个变动量较大的文件；提交说明与 diff 均有长度限制。
- diff 总预算 48,000 字符。输入预览与报告注明覆盖范围。
- 模型必须为每条结论返回完整 commit hash 和对应文件路径。
- 服务端验证引用确实存在且 commit/file 配对正确。**引用合法不代表结论正确**，仍需人工核查。
- 缓存键包含输入、接口地址、模型与提示词版本。未实现逐提交的多阶段摘要。

## 统计口径和限制

- 只分析已提交的 Git 历史，不包含未提交修改、issues、PR、会议记录或测试执行结果。
- 采集按分支固定 tip 的拓扑遍历取最近 N 条；日期筛选只作用于已采集数据。截断范围会在界面及报告中提示。
- 以 **committer date** 作为时间依据，存储为 UTC；默认按 Asia/Shanghai 展示和分日，可切换 UTC。
- 作者默认按小写 email 分组，email 缺失时使用姓名；尚未实现别名合并或 co-author 分摊。
- 模块是路径首级目录，根目录文件归为 `(root)`；尚未实现业务模块映射。
- 模块筛选后，只统计选中模块内的文件和行数；提交数为触及选中模块的提交数。
- 文件按路径计数；重命名前后不合并为同一文件生命周期。
- 默认排除 merge；开启后只增加提交计数，不统计 merge 的逐文件差异，避免重复和误导。
- 文本 diff 每个文件最多存储 12,000 字符，截断不影响程序读取的行数统计。
- 无文本 diff 会明确标记，可能是纯重命名、空文件或二进制变更，不生成虚假的文本解释。
- 提交次数、变更行数只描述可观察活动，不能代替工时、质量或课程贡献比例。
- 支持本地工作仓库与公开 GitHub HTTPS 下载；不支持 bare 仓库、私有仓库登录、多用户部署或后台任务队列。
- 采集是同步执行；第一版优先选择小型仓库或较小采集上限。

## 项目结构

```text
app.py                  Streamlit 页面与交互
repolens/mining.py      只读 Git 适配、PyDriller 提取、固定快照
repolens/remote.py      GitHub URL 校验、下载与缓存更新
repolens/storage.py     SQLite 分析结果与摘要缓存
repolens/analytics.py   统一筛选和确定性统计
repolens/reports.py     统计报告、模型接口、引用校验、Markdown 导出
repolens/demo.py        合成演示仓库生成器
tests/                 Git 集成、统计、存储与 AI 接口测试
scripts/               可选浏览器验收脚本
data/                  本机生成的数据（Git 忽略）
```

PyDriller 当前版本的默认初始化会设置仓库 blame 配置。`ReadOnlyGit` 仅覆盖其打开步骤，继续使用 PyDriller 的 commit/diff 能力，避免该写入；测试验证 `.git/config`、HEAD 和工作区保持不变。升级 PyDriller 时需要保留这项回归检查。

## 验证

安装开发依赖：

```powershell
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
```

没有 uv 时，使用虚拟环境中的 pip。自动测试只使用临时合成仓库和本机 HTTP 测试服务，不调用付费模型。

浏览器验收需要先启动应用，然后运行：

```powershell
.venv/Scripts/python.exe scripts/smoke_browser.py --channel msedge
```

该命令使用已安装的 Edge；也可以使用 `--channel chrome`。检查演示数据、页面、筛选、diff 与报告下载。浏览器截图与下载文件保存在 `work/browser/`，不会修改被分析的实际项目。

公开 GitHub 下载的可选联网验收（需要本机 Git 能连接 GitHub）：

```powershell
.venv/Scripts/python.exe scripts/smoke_github.py --channel msedge
```

自动测试使用本地 Git 传输替代网络，以真实浅克隆验证下载、缓存更新、分支和差异准确性，并验证网络错误处理；它们不代表当前互联网连接一定可用。

## 后续迭代

优先考虑多阶段摘要、作者别名映射、业务模块配置、文件重命名链追踪及用户任务评估。GitHub PR/issue 集成放到后续阶段。

## 参考

- [PyDriller](https://github.com/ishepard/pydriller)
- [PyDriller Commit / ModifiedFile](https://pydriller.readthedocs.io/en/latest/modifiedfile.html)
- [Streamlit](https://docs.streamlit.io/)
- [Plotly Python](https://plotly.com/python/)

PyDriller 是上游依赖；本项目的演示记录为合成数据。提交课程报告时应分别说明上游能力与本项目新增实现。
