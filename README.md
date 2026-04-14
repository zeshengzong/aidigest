# 🤖 AIDigest

**每日 AI 资讯自动聚合** — 从 7 个数据源抓取最新 AI 动态，通过 LLM 生成中文摘要和趋势概览，以整洁的 Markdown 报告形式保存，并由 GitHub Actions 每天早晨 8 点（北京时间）自动执行。

[查看示例报告 →](DIGEST.md)

---

## ✨ 功能特性

- **7 大数据源** — Hacker News、GitHub Trending、Hugging Face、ArXiv、Reddit、Product Hunt、官方 AI 博客
- **主题自动分类** — 基于关键词将文章归类为 LLM / Agent / CV / RAG / MLOps 等 12 个主题
- **LLM 智能摘要** — 支持 OpenAI 和 Anthropic 双后端，默认生成中文摘要
- **每日核心总结** — 由 LLM 生成约 200 字的当日核心内容概述，置于报告最顶端
- **每日趋势概览** — 由 LLM 综合当天所有资讯，生成一段趋势分析段落
- **中英文双语模板** — 模板标题、表头、页脚等所有静态文本根据 `SUMMARY_LANGUAGE` 自动切换中/英文
- **容错设计** — 单个爬虫或 LLM 失败不影响其他来源正常运行
- **每日自动化** — GitHub Actions 定时执行，结果自动提交到仓库

---

## 📰 数据源说明

| 数据源 | 内容 | 采集方式 | 需要 Key |
|--------|------|---------|---------|
| **Hacker News** | 技术社区热帖 | 官方 Firebase API | 否 |
| **GitHub Trending** | 今日热门开源项目 | HTML 解析 | 否 |
| **Hugging Face** | 热门模型 + 每日论文 | 官方 API + HTML | 否 |
| **ArXiv** | cs.AI/CL/CV/LG/ML 最新论文 | Atom API | 否 |
| **Reddit** | r/MachineLearning 等社区热帖 | 公开 JSON API | 否 |
| **Product Hunt** | 每日 AI 产品发布 | HTML 解析 | 否 |
| **官方 AI 博客** | OpenAI / Anthropic / Google / Meta | RSS Feed | 否 |

> 所有数据源均无需额外 API Key，开箱即用。

---

## 🚀 快速开始

### 1. 克隆并安装依赖

```bash
git clone https://github.com/zeshengzong/aidigest.git
cd aidigest
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写 LLM API Key
```

### 3. 运行

```bash
python main.py                        # 生成今日报告
python main.py --date 2026-04-01      # 指定日期
```

报告保存至 `archives/YYYY-MM-DD.md`，索引文件为 `DIGEST.md`。

---

## ⚙️ 配置说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `openai` | LLM 后端：`openai` 或 `anthropic` |
| `OPENAI_API_KEY` | — | OpenAI API Key（使用 OpenAI 时必填）|
| `OPENAI_MODEL` | `gpt-4o` | OpenAI 模型名 |
| `ANTHROPIC_API_KEY` | — | Anthropic API Key（使用 Anthropic 时必填）|
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Anthropic 模型名 |
| `SUMMARY_LANGUAGE` | `zh` | 摘要及模板语言：`zh`（中文）或 `en`（英文）|
| `HN_MAX_STORIES` | `30` | Hacker News 最大抓取数 |
| `GITHUB_MAX_REPOS` | `20` | GitHub Trending 最大抓取数 |
| `HF_MAX_ITEMS` | `20` | Hugging Face 最大抓取数 |
| `ARXIV_MAX_PAPERS` | `15` | ArXiv 最大抓取数 |
| `REDDIT_MAX_POSTS` | `15` | Reddit 最大抓取数 |
| `PH_MAX_PRODUCTS` | `10` | Product Hunt 最大抓取数 |
| `BLOG_MAX_POSTS` | `10` | 官方博客最大抓取数 |
| `BLOG_DAYS_LOOKBACK` | `2` | 博客仅收录最近 N 天的文章 |

> 未配置 LLM API Key 时，摘要将自动降级为原始描述文本，其余功能不受影响。

---

## 🤖 GitHub Actions 自动化

工作流每天 **北京时间早上 8:00**（UTC 00:00）自动运行，也支持手动触发。

### 启用步骤

1. 将仓库推送到 GitHub
2. 进入 **Settings → Secrets and variables → Actions**
3. 添加以下 Secrets：

   | Secret | 说明 |
   |--------|------|
   | `LLM_PROVIDER` | `openai` 或 `anthropic` |
   | `OPENAI_API_KEY` | OpenAI Key（二选一）|
   | `ANTHROPIC_API_KEY` | Anthropic Key（二选一）|
   | `SUMMARY_LANGUAGE` | `zh`（可选，默认中文）|

4. 在 **Actions** 标签页点击 **Run workflow** 手动测试一次

每次执行后，工作流自动将 `archives/YYYY-MM-DD.md` 和 `DIGEST.md` 提交到仓库。

---

## 🔄 工作流程

```
Hacker News ──┐
GitHub Trends ─┤
Hugging Face  ─┤
ArXiv         ─┤──► 关键词过滤 ──► 主题分类 ──► LLM 摘要 ──► 核心总结 + 每日概览
Reddit        ─┤                  (classifier)  (summarizer)   (tagline + overview)
Product Hunt  ─┤                                                        │
AI Blogs      ─┘                                                        │
                                                                         ▼
                                                                Jinja2 模板渲染
                                                               (中/英文自动切换)
                                                                         │
                                                                         ▼
                                                          archives/YYYY-MM-DD.md
                                                                DIGEST.md 索引
```

**Pipeline 各步骤：**

1. **Scrape** — 7 个爬虫并行抓取，单个失败不影响整体
2. **Classify** — 基于规则的主题分类（LLM / Agent / CV / RAG / NLP 等 12 类）
3. **Summarise** — LLM 为每篇文章生成一句话摘要，Top Story 生成段落摘要
4. **Tagline** — LLM 生成约 200 字的当日核心内容概述，放在报告最顶端
5. **Overview** — LLM 综合所有资讯生成当日 AI 领域趋势概述
6. **Render** — Jinja2 模板渲染为 Markdown（根据语言设置自动切换中/英文），包含统计面板和主题分布

---

## 📁 项目结构

```
aidigest/
├── main.py                        # 入口：串联完整 pipeline
├── requirements.txt               # Python 依赖
├── .env.example                   # 环境变量模板
├── .github/
│   └── workflows/
│       └── daily_digest.yml       # GitHub Actions 定时工作流
├── src/
│   ├── config.py                  # Pydantic 配置管理
│   ├── models.py                  # Article / Digest 数据模型
│   ├── classifier.py              # 基于规则的主题分类器
│   ├── summarizer.py              # LLM 摘要（OpenAI / Anthropic）
│   ├── generator.py               # Jinja2 → Markdown 渲染
│   ├── templates/
│   │   └── digest.md.j2           # 报告 Markdown 模板
│   └── scrapers/
│       ├── __init__.py            # run_all_scrapers() 编排器
│       ├── hackernews.py          # Hacker News API 爬虫
│       ├── github_trends.py       # GitHub Trending 爬虫
│       ├── huggingface.py         # Hugging Face 模型 + 论文爬虫
│       ├── arxiv.py               # ArXiv 论文 API 爬虫
│       ├── reddit.py              # Reddit 社区爬虫
│       ├── producthunt.py         # Product Hunt 产品爬虫
│       └── ai_blogs.py            # 官方 AI 博客 RSS 聚合
└── archives/                      # 生成的每日报告（Git 跟踪）
    ├── DIGEST.md                  # 归档索引
    └── YYYY-MM-DD.md              # 每日报告
```

---

## 📦 依赖

```
requests        # HTTP 请求
beautifulsoup4  # HTML 解析
lxml            # XML / HTML 解析器
feedparser      # RSS / Atom feed 解析
pydantic        # 数据模型与校验
pydantic-settings
python-dotenv   # .env 加载
jinja2          # 模板渲染
openai          # OpenAI API 客户端
anthropic       # Anthropic API 客户端
tenacity        # 请求重试
```

---

## 📄 License

MIT — see [LICENSE](LICENSE).
