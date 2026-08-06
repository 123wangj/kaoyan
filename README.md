# 计算机考研 408 AI 辅导项目

这是一个面向计算机考研的 AI 项目骨架，核心目标是把“主智能体意图分析 + 多子智能体 + RAG + Skill 提示词 + MCP 工具层 + 用户画像分析”串成可扩展后端。

## 已实现能力

- Agent Runtime：结构化规划、复合任务拆解、受控工具调用、结果验证和有限重规划。
- 主智能体：识别用户的一个或多个意图，并按原始目标顺序执行。
- 题目解答：限定 408 考研范围，输出答案、思路、踩分点和生动解释。
- 相似题训练：从题库/RAG 中召回，并可让大模型补充同难度题。
- 个性化分析：基于错题、作答记录、聊天摘要输出掌握度、错误原因分类和图表数据。
- 知识点带背：用形象类比、口诀和自测问题辅助记忆。
- 每日知识点推送：结合近期记录，按知识点去重。
- 院校专业分数预测：保留“仅供参考”声明，关注复试逆袭/高分被刷风险。
- 学习计划生成：根据薄弱点和剩余天数生成日/周/月计划。
- MCP：提供一个工具服务器示例，方便给其他客户端调用题库检索和分析能力。
- 长期记忆：只提取用户明确表达的目标、偏好和学习证据，并记录来源与置信度。
- 自适应学生模型：兼容原掌握分，同时计算 BKT 掌握概率、记忆稳定性和复习时间。
- 教学闭环：作答后自动更新画像、复习队列，并调整未来计划中的相关任务。
- 可观测性：持久化脱敏 Agent 轨迹，记录计划、工具、耗时、校验和置信度。

## Agent 运行机制

```text
理解目标 → 拆解计划 → 读取画像/记忆 → 调用专业工具
    ↑                                  ↓
有限重规划 ← 结果验证/置信度检查 ← 汇总证据
                                           ↓
                                  更新记忆与学习计划
```

内部工具采用显式白名单，当前包括题库检索、知识检索、画像读取、复习队列、
可执行学习计划生成，以及七类专业辅导能力。每次运行受 `AGENT_MAX_ITERATIONS`
限制，默认最多 12 步。

复合请求会启用受约束的 LLM 规划器；模型只能从已声明的意图枚举中排序和选择，
不能自行发明工具。JSON 解析或模型服务失败时自动回退到确定性多意图规划器。

流式和非流式聊天均使用同一个 Agent Runtime。SSE 除兼容原有 `chunk` 和
`done` 事件外，还会返回：

- `plan_created`
- `tool_started`
- `tool_finished`
- `replan`
- `validated`

前端可以用这些事件展示“正在读取画像”“正在生成计划”等真实进度。

## 数据与学习闭环

学习计划中的任务绑定日期、知识点、题目 ID、预计时长和完成状态。用户作答后，
系统会更新：

- 兼容原前端的 0～100 掌握分；
- `mastery_probability`；
- `confidence`；
- `stability_days`；
- `memory_difficulty`；
- `next_review_at`；
- 受影响计划任务的优先级、时长和调整原因。

本地检索采用字符 TF-IDF、BM25 和科目/知识点元数据联合重排，模型回答仍携带
原始题库或知识库证据。

如需加入神经语义向量通道，先离线构建索引，再启用开关，避免在用户请求中为整库
临时生成向量：

```powershell
python scripts/build_embedding_index.py --collection knowledge_points
python scripts/build_embedding_index.py --collection question_bank
```

随后设置 `RAG_ENABLE_EMBEDDINGS=true`。检索会自动融合 TF-IDF、BM25、Embedding
与元数据得分；索引或服务不可用时自动退回本地混合检索。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
Copy-Item .env.example .env
uvicorn kaoyan_ai.api:app --reload --port 8000
```

然后访问：

- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/health

没有配置 `OPENAI_API_KEY` 时，项目会返回规则化的占位答案，方便先调通流程；配置后会调用 LangChain/OpenAI 兼容接口。
如果本机已有 API 环境变量但只想离线调试，可以在 `.env` 中设置 `DISABLE_LLM=true`。

Agent 相关配置：

```dotenv
AGENT_MAX_ITERATIONS=12
AGENT_TRACE_ENABLED=true
AGENT_LLM_PLANNER_ENABLED=true
```

## 数据库升级

新部署会通过 `db/init.sql` 创建 Agent 表。已有数据库执行安全的增量脚本：

```powershell
psql $env:DATABASE_URL -f db/agent_upgrade.sql
```

该脚本只创建不存在的表，不删除现有数据。

## Agent 调试与评测

- `GET /agent/capabilities`：查看当前工具、记忆层和循环上限。
- `GET /agent/runs/recent`：查看当前用户最近的脱敏运行轨迹。
- `python scripts/evaluate_agent.py`：汇总成功率、置信度、工具失败率和平均循环次数。
- 轨迹默认写入 `data/agent_runs/YYYY-MM-DD.jsonl`。

## 示例请求

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/chat `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"user_id":"u1","message":"请讲一下操作系统中页表和快表的区别，并出两道相似题"}'
```

## 目录结构

```text
kaoyan_ai/
  agents/        子智能体
  rag/           题库和知识库检索
  skills/        Skill 文件加载器
  mcp/           MCP 工具服务器
  api.py         FastAPI 入口
  graph.py       LangGraph 编排
  schemas.py     状态与数据模型
data/            示例题库、知识点和用户记录
skills/          408 约束、讲解风格、踩分点等 Skill 提示词
tests/           核心规则测试
```

## 重要产品约束

- 题目解答必须限定在 408 考研范围：数据结构、计算机组成原理、操作系统、计算机网络。
- 不讲超纲知识，不把工程细节、论文知识、竞赛技巧当作考研答题要求。
- 讲解需要明确阅卷踩分点，帮助学生知道“写什么能得分”。
- 相似题难度与 408 真题/常规模拟题对齐，避免偏题怪题。
- 院校预测必须标注“仅供参考”，并说明复试导致名次变化的风险。
