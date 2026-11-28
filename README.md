# ChangeGuard

**Project Name:** ChangeGuard

**Full Project Title:** ChangeGuard: An Explainable Change Completeness Analysis Tool Based on Git History

当前版本为 v0.4.0：在仓库可视化、Sprint 管理/报告、changed methods、AI 引用校验与 Sprint 对比的基础上，增加**范围明确的潜在遗漏修改检查**。该检查根据目标提交的历史共同修改规则推荐需人工检查的关联文件，附原始提交依据；它不证明业务变更完整性。

基于 PyDriller 的 Git 仓库演化可视化与智能摘要工具，支持公开 GitHub 链接和本地仓库。当前版本是可运行原型，使用 Python、Streamlit、Plotly、pandas 和 SQLite。

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
5. 在「Sprint 报告」直接下载统计报告；无模型时不会伪装成 AI 摘要。
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

被分析仓库保持原分支和工作目录。采集不执行 checkout、不写入源码或仓库配置；SQLite 与演示数据写入 ChangeGuard 自己的 `data/`。

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
- 按仓库持久保存 Sprint，支持创建、编辑、删除和下拉切换。
- 按所选 Sprint 同步图表、统计、AI 摘要与 Markdown 报告。
- 独立选择两个 Sprint，对比活动指标、模块及文件变更，导出有筛选与快照依据的统计报告。
- 选择一个普通提交，学习已采集祖先中的文件共同修改规则，提示潜在遗漏路径、关联比例和历史依据；支持报告导出及独立合成演示。
- 文件详情展示 changed methods 的方法签名及变更前/后行号，报告可导出方法列表。

## Sprint 与 changed methods（v0.2）

分析仓库后，在「Sprint 工作区」展开「创建或编辑 Sprint」，填写名称与含首尾的起止日期并保存。可在「选择 Sprint」中直接切换；选择「自定义日期范围」恢复自由筛选。

Sprint 定义写入 SQLite，重启仍可恢复。GitHub 来源相同的不同下载深度共用 Sprint 定义，本地仓库按路径区分。Sprint 不绑定某条分支，统计仍采用当前分析快照的分支、作者和模块筛选。

在「Sprint 报告」中会自动带上当前 Sprint 名称和日期，可逐个切换生成/下载各自报告。报告文件名包含 Sprint 名称。配置超出采集范围或使用部分历史时会提示覆盖限制；无提交时明确显示空结果，不生成虚假的变化总结。未实现批量生成所有 Sprint 的 AI 报告。

### Sprint 对比（v0.3）

在「Sprint 对比」页选择 A（基准）和 B（对照）。两期各自按保存日期计算，使用同一分析快照、时区，以及页面上方相同的开发者/模块筛选。它们独立于「选择 Sprint」与单期自定义日期；单期日期内没有提交时仍可对比。

- 指标表展示提交数、作者标识数、文件路径数、增删行、变动行、日历天数、平均每日提交数，以及 B 相对 A 的差值和变化率。A 为 0 时变化率不计算。
- 模块柱状图比较两期增删行之和，展示合计变动量最高的 12 个模块；表格包含全部模块。
- 文件表使用两期路径并集，分别列出提交与增删行，并标记「仅 A 有变更」「仅 B 有变更」「两期均有变更」。这些标记不代表文件新增/删除，重命名前后按不同路径计数。
- 日期重叠、时长不同、空结果、浅克隆或采集截断都会提示。平均每日提交数以含首尾的日历天数为分母。
- 可下载 Markdown 对比报告，包含分支、tip、快照标识、时区、筛选和覆盖限制。导出最多列出 100 个文件并说明截断，页面表格可查看全部。
- 不需要模型/API。此功能比较两期 Git 开发活动，不进行版本间完整源码差异比较，也不推断质量、工时或贡献比例。

快速验收：载入演示仓库 → 「Sprint 对比」→ A 选 Sprint 1，B 选 Sprint 2。预期两期均 9 条提交；A 新增/删除行 38/1、B 为 24/7；时长分别为 6/8 天。尝试交换 A/B、选择同一个 Sprint、使用开发者或模块筛选，然后下载报告核对。

演示仓库自动创建两个示例 Sprint：Sprint 1（2026-11-09 至 2026-11-14）和 Sprint 2（2026-11-15 至 2026-11-22），各 9 条提交。

Changed methods 通过 PyDriller 的方法解析与 diff 增删行交集获得。文件详情列出方法签名、变更前/后源码版本及行号；方法删除可显示变更前位置。它不是方法身份追踪，同一方法可能有前后两条记录，不应简单相加当作独立方法数。模块级改动、仅路径变更、没有方法定义的文件可能没有结果。不支持的文件和解析失败会分别说明，仍保留文件统计与 diff。

新版本采集缓存版本已更新，旧分析需重新采集以补充方法信息；已有 GitHub 下载可复用，不必重新从网络下载。Markdown 最多列出 200 条方法位置记录并明确截断，完整记录可在提交详情中查看。

## 潜在遗漏修改检查（v0.4）

点击左侧「载入遗漏检测演示」，再进入「遗漏修改检查」页。独立演示仓库包含 15 条合成提交，不改变原有 18 条提交的演示与 Sprint 指标。

默认目标 `demo: auth-only change (missing test update)` 只改 `src/auth.py`。更早的历史中它与 `tests/test_auth.py` 共同修改了 4 次；默认阈值下页面建议检查测试文件，并提供 4 条历史提交及 diff。选择 `complete auth and test change` 或 `unrelated cache-only change` 可查看无建议的对照案例。

使用真实仓库时，先采集足够的历史，然后在该页选择当前筛选中的目标提交并点击「检查潜在遗漏」。检测不调用 AI，也不重新下载历史。

规则与范围：

- 默认历史窗口 500、最少共同修改 3 次、最低关联比例 60%、每提交最多 20 个路径。
- 规则为 A → B；共同修改次数为 count(A,B)，历史关联比例为 count(A,B)/count(A)。计数只来自有效历史事务，比例不是缺陷概率。
- 通过 Git 祖先关系取目标以前的提交，并与当前已采集快照取交集；不用目标本身、未来提交、同级分支或单纯日期排序推断先后。
- 历史不随页面作者/模块/日期筛选缩小；当前提交使用完整触及路径，避免把已修改但被筛选隐藏的文件误报为遗漏。
- 只学习稳定路径的文本 MODIFY；新增、删除、重命名、二进制不作为触发记录。窗口内出现重命名/删除的路径整体排除，不追踪文件身份。
- 跳过 merge、大规模提交、常见锁文件、依赖/生成目录和压缩资源。阈值可调，界面/导出保存具体参数。
- 候选必须存在于目标提交的文件树，并且没有被该提交触及。检查只读 Git 对象，不 checkout、不修改被分析仓库。
- 结果包含候选、触发文件、共同修改次数、分母、关联比例、原始依据和完整口径。无建议分为“历史证据不足”“不适用”和“当前阈值下未发现”，不宣称变更完整。

### 检测评估

```powershell
.venv/Scripts/python.exe scripts/evaluate_completeness.py --demo
.venv/Scripts/python.exe scripts/evaluate_completeness.py --repository D:/path/to/repo --limit 300 --cases 20 --top-k 5
```

结果保存为 `work/completeness-evaluation/evaluation.json` / `evaluation.txt`。合成模式检查三个功能对照，并对完整控制提交分别遮蔽源码/测试文件。真实仓库模式按采集顺序选择多文件 MODIFY 提交，每个案例遮蔽按路径排序的最后一个文件。两种模式都只用目标祖先训练，并与同一有效历史下的文件修改频率基线比较。

报告给出 Top-1 / Top-K 找回数、遮蔽找回率、平均倒数排名和未给建议的案例数。**遮蔽找回率衡量模拟的文件推荐任务，不能当作真实遗漏或缺陷准确率。** 合成案例用于功能验证，真实有效性还需实际仓库评估与人工核查。

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
- v0.2.1 起模型使用输入文件的固定 evidence_id 返回依据，由程序还原完整 commit hash 与文件路径，避免手写引用配错。旧格式仍严格校验。
- 服务端验证引用确实存在且 commit/file 配对正确。**引用合法不代表结论正确**，仍需人工核查。
- 校验失败时不保存该 AI 结果，页面保留统计报告并明确说明本次生成或校验失败；不会再误提示为“未调用 AI”。模型接口地址两端的粘贴空白会自动清理，内部控制字符会显示格式错误。
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
repolens/methods.py     方法签名与变更前后行号提取
repolens/sprints.py     Sprint 仓库标识与覆盖范围检查
repolens/comparison.py  两期统计、差值、文件并集与对比报告
repolens/comparison_ui.py Sprint 对比页面
repolens/completeness.py 祖先历史关联规则、候选解释和导出
repolens/completeness_ui.py 遗漏检查页面与依据核查
repolens/completeness_demo.py 独立的合成对照仓库
repolens/completeness_eval.py 遮蔽回放及频率基线评估
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
.venv/Scripts/python.exe scripts/smoke_sprints.py
.venv/Scripts/python.exe scripts/smoke_comparison.py
.venv/Scripts/python.exe scripts/smoke_completeness.py
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
- [Zimmermann et al., Mining Version Histories to Guide Software Changes, ICSE 2004](https://st.cispa.saarland/papers/icse2004/)：历史关联推荐的相关研究；本原型采用文件级计数和受限检查流程，没有复现 ROSE 的完整实现或实验结果。

PyDriller 是上游依赖；本项目的演示记录为合成数据。提交课程报告时应分别说明上游能力与本项目新增实现。
