# 招聘 JD 数据源配置

InterviewRadar 默认通过开源 **[job-pro](https://github.com/HA7CH/job-pro)** 批量拉取约 50 家互联网大厂官网 API（腾讯、字节、阿里、美团等），无需自己维护每家适配器。也可选用内置 **字节连接器** 或 **Boss直聘**（需 Cookie）。

## 依赖

- **Node.js 18+**（`npx job-pro@latest` 自动拉包），或全局安装：`npm i -g job-pro`
- Boss 可选：`BOSS_ZHIPIN_COOKIE`

## 命令行

```bash
# 默认：job-pro（5 家默认大厂）+ Boss（若配 Cookie）
interview-radar-jobs --role-id ai_app --companies 腾讯 字节跳动

# 指定 job-pro 渠道
interview-radar-jobs --role-id ai_app --companies 腾讯 --job-pro-scope campus

# 拉完整 JD 正文（较慢，逐条 detail）
interview-radar-jobs --role-id ai_app --companies 腾讯 --job-pro-details

# 不用 job-pro，仅用内置字节 API
interview-radar-jobs --sources bytedance --no-job-pro --keywords "AI"

# 仅官方站，跳过 Boss
interview-radar-jobs --role-id backend --companies 字节跳动 --no-boss

# 指定来源
interview-radar-jobs --sources bytedance --keywords "AI 应用" --max-per-query 5

# 列出缓存
interview-radar-jobs --list
```

## Boss直聘 Cookie

1. 浏览器登录 [zhipin.com](https://www.zhipin.com)
2. 导出 Cookie 字符串（开发者工具 → Network → 任意请求 → Cookie）
3. 写入环境变量：

```bash
export BOSS_ZHIPIN_COOKIE='lastCity=101010100; ...'
```

或使用 `.env`（勿提交到 Git）。

未配置时 Boss 连接器会 **降级** 并提示，不影响字节等官方站。

详细配置见 **[docs/setup/boss-zhipin-cookie.md](boss-zhipin-cookie.md)**（Chrome 导出步骤 + 验证命令）。

## 已接入来源

| 来源 id | 说明 | 状态 |
|---------|------|------|
| `job_pro` | 开源 job-pro，约 50 家公司 | **默认**，需 Node.js |
| `bytedance` | 内置字节 jobs.bytedance.com | `--sources bytedance --no-job-pro` |
| `boss_zhipin` | Boss直聘聚合 | 需 Cookie |

规划中的官方站（腾讯、阿里、美团等）已在 `/api/jobs/sources` 目录中列出，后续按 ATS API 逐个接入。

## API

```bash
GET  /api/jobs/sources
GET  /api/jobs
GET  /api/jobs/{slug}
POST /api/jobs/fetch
```

`POST /api/jobs/fetch`  body 示例：

```json
{
  "role_id": "ai_app",
  "companies": ["字节跳动"],
  "max_per_query": 10,
  "no_boss": false
}
```

## 缓存位置

```
corpus_cache/jobs/<slug>/
├── jobs.json    # 岗位列表 + is_new 标记
└── meta.json    # 抓取元数据
```

## 合规

仅用于个人求职调研；遵守各平台 robots / 用户协议；不要高频爬取或商用分发。
