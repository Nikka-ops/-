"""
Tech-stack frequency analysis across job postings.

Scans titles + descriptions + tags from one or two role snapshots,
counts keyword hits, and returns a structured summary per category.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

# ── Keyword catalogue ────────────────────────────────────────────────────────
# Each entry: (display_label, [search_patterns])
# Patterns are matched case-insensitively against the full job blob.

_CATALOGUE: list[tuple[str, str, list[str]]] = [
    # ── 计算引擎 ─────────────────────────────────────────────────
    ("计算引擎", "Spark",           ["spark"]),
    ("计算引擎", "Flink",           ["flink"]),
    ("计算引擎", "Hive",            ["hive"]),
    ("计算引擎", "Hadoop",          ["hadoop"]),
    ("计算引擎", "MapReduce",       ["mapreduce", "map reduce", "map-reduce"]),
    ("计算引擎", "Presto / Trino",  ["presto", "trino"]),
    ("计算引擎", "Hbase",           ["hbase"]),

    # ── 存储 / 数据库 ──────────────────────────────────────────
    ("存储与数据库", "Doris",           ["doris"]),
    ("存储与数据库", "StarRocks",       ["starrocks", "star rocks"]),
    ("存储与数据库", "ClickHouse",      ["clickhouse", "click house"]),
    ("存储与数据库", "Iceberg",         ["iceberg"]),
    ("存储与数据库", "Delta Lake",      ["delta lake", "delta table"]),
    ("存储与数据库", "HDFS",            ["hdfs"]),
    ("存储与数据库", "MySQL / PG",      ["mysql", "postgresql", "postgres"]),
    ("存储与数据库", "Redis",           ["redis"]),
    ("存储与数据库", "Elasticsearch",   ["elasticsearch", "elastic search", "es索引"]),
    ("存储与数据库", "Kylin",           ["kylin"]),

    # ── 消息队列 ────────────────────────────────────────────────
    ("消息队列", "Kafka",           ["kafka"]),
    ("消息队列", "Pulsar",          ["pulsar"]),
    ("消息队列", "RocketMQ",        ["rocketmq", "rocket mq"]),
    ("消息队列", "RabbitMQ",        ["rabbitmq"]),

    # ── 调度 / 数据集成 ─────────────────────────────────────────
    ("调度与集成", "Airflow",           ["airflow"]),
    ("调度与集成", "DolphinScheduler",  ["dolphinscheduler", "dolphin scheduler", "海豚调度"]),
    ("调度与集成", "DataX",             ["datax"]),
    ("调度与集成", "Sqoop",             ["sqoop"]),
    ("调度与集成", "Flume",             ["flume"]),
    ("调度与集成", "Canal",             ["canal"]),
    ("调度与集成", "Debezium",          ["debezium"]),

    # ── AI / LLM 框架 ───────────────────────────────────────────
    ("AI 框架", "LangChain",        ["langchain"]),
    ("AI 框架", "LlamaIndex",       ["llamaindex", "llama index", "llama_index"]),
    ("AI 框架", "LangGraph",        ["langgraph"]),
    ("AI 框架", "AutoGen",          ["autogen"]),
    ("AI 框架", "CrewAI",           ["crewai", "crew ai"]),
    ("AI 框架", "Dify",             ["dify"]),
    ("AI 框架", "FastAPI",          ["fastapi"]),

    # ── AI 技术方向 ─────────────────────────────────────────────
    ("AI 技术方向", "RAG",              ["rag", "检索增强", "retrieval augmented"]),
    ("AI 技术方向", "Agent / 智能体",   ["agent", "智能体", "agentic"]),
    ("AI 技术方向", "MCP",              ["mcp", "model context protocol"]),
    ("AI 技术方向", "Function Call",    ["function call", "工具调用", "tool use", "tool call"]),
    ("AI 技术方向", "Embedding",        ["embedding", "文本嵌入"]),
    ("AI 技术方向", "Rerank",           ["rerank", "re-rank", "重排"]),
    ("AI 技术方向", "Prompt 工程",      ["prompt engineering", "提示词工程", "prompt优化"]),
    ("AI 技术方向", "Fine-tuning",      ["fine-tuning", "finetune", "微调", "lora", "rlhf"]),
    ("AI 技术方向", "多模态",           ["多模态", "multimodal", "vision language"]),

    # ── 向量数据库 ──────────────────────────────────────────────
    ("向量数据库", "Milvus",         ["milvus"]),
    ("向量数据库", "Chroma",         ["chroma"]),
    ("向量数据库", "Weaviate",       ["weaviate"]),
    ("向量数据库", "Qdrant",         ["qdrant"]),
    ("向量数据库", "FAISS",          ["faiss"]),
    ("向量数据库", "pgvector",       ["pgvector"]),

    # ── 大模型 ──────────────────────────────────────────────────
    ("大模型", "GPT / OpenAI",    ["gpt", "openai", "chatgpt"]),
    ("大模型", "DeepSeek",        ["deepseek"]),
    ("大模型", "Qwen / 通义",     ["qwen", "通义", "千问"]),
    ("大模型", "LLaMA / Meta",    ["llama", "meta llm"]),
    ("大模型", "Claude",          ["claude"]),
    ("大模型", "Gemini",          ["gemini"]),
    ("大模型", "文心 / ERNIE",    ["ernie", "文心"]),

    # ── 编程语言 ────────────────────────────────────────────────
    ("编程语言", "Python",         ["python"]),
    ("编程语言", "Java",           ["java"]),
    ("编程语言", "Scala",          ["scala"]),
    ("编程语言", "SQL",            ["sql"]),
    ("编程语言", "Go",             [r"\bgo\b", "golang"]),
    ("编程语言", "Rust",           ["rust"]),
    ("编程语言", "C++",            [r"c\+\+", "cpp"]),
    ("编程语言", "Shell",          ["shell", "bash script"]),

    # ── 云 / 平台 ───────────────────────────────────────────────
    ("云与平台", "阿里云 / MaxCompute", ["阿里云", "maxcompute", "odps", "oss"]),
    ("云与平台", "腾讯云",              ["腾讯云", "tke", "tcos"]),
    ("云与平台", "AWS",                 ["aws", "s3", "emr", "glue"]),
    ("云与平台", "Kubernetes",          ["kubernetes", "k8s"]),
    ("云与平台", "Docker",              ["docker", "container"]),
    ("云与平台", "Spark on K8s",        ["spark on k8s", "spark on kubernetes"]),

    # ── 数仓方法论 ──────────────────────────────────────────────
    ("数仓方法论", "ODS / DWD / DWS",   ["ods", "dwd", "dws", "ads", "数据分层"]),
    ("数仓方法论", "数据建模",           ["数据建模", "维度建模", "宽表", "ER模型"]),
    ("数仓方法论", "数据治理",           ["数据治理", "数据质量", "元数据", "数据目录"]),
    ("数仓方法论", "数据湖 / 湖仓",      ["数据湖", "湖仓", "lakehouse", "iceberg", "delta"]),
    ("数仓方法论", "实时数仓",           ["实时数仓", "实时计算", "流计算", "流式处理"]),
    ("数仓方法论", "离线数仓",           ["离线数仓", "离线计算", "批计算", "t+1"]),
]


def _make_patterns(terms: list[str]) -> list[re.Pattern]:
    return [re.compile(t, re.IGNORECASE) for t in terms]


_COMPILED: list[tuple[str, str, list[re.Pattern]]] = [
    (cat, label, _make_patterns(terms))
    for cat, label, terms in _CATALOGUE
]


def _job_blob(job: dict) -> str:
    parts = [
        job.get("title") or "",
        job.get("description") or "",
        " ".join(job.get("tags") or []),
    ]
    return " ".join(parts)


def analyse_tech_stack(jobs: list[dict]) -> dict:
    """
    Returns:
    {
      "total_jobs": int,
      "categories": [
        {
          "name": "计算引擎",
          "items": [
            {"label": "Spark", "count": 85, "pct": 65.4},
            ...
          ]
        },
        ...
      ]
    }
    Items sorted by count desc; categories with zero total items omitted.
    """
    n = len(jobs)
    if n == 0:
        return {"total_jobs": 0, "categories": []}

    blobs = [_job_blob(j).lower() for j in jobs]

    # count per (cat, label)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for blob in blobs:
        seen_labels: set[str] = set()
        for cat, label, patterns in _COMPILED:
            if label in seen_labels:
                continue
            for pat in patterns:
                if pat.search(blob):
                    counts[(cat, label)] += 1
                    seen_labels.add(label)
                    break

    # group by category preserving insertion order
    cat_order: list[str] = []
    cat_items: dict[str, list[dict]] = defaultdict(list)
    for cat, label, _ in _CATALOGUE:
        if cat not in cat_order:
            cat_order.append(cat)
        c = counts.get((cat, label), 0)
        cat_items[cat].append({
            "label": label,
            "count": c,
            "pct": round(c / n * 100, 1),
        })

    categories = []
    for cat in cat_order:
        items = sorted(cat_items[cat], key=lambda x: -x["count"])
        # skip categories where everything is 0
        if not any(i["count"] > 0 for i in items):
            continue
        # trim zero-count tail
        last_nonzero = max((i for i, x in enumerate(items) if x["count"] > 0), default=-1)
        items = items[: last_nonzero + 1]
        categories.append({"name": cat, "items": items})

    return {"total_jobs": n, "categories": categories}
