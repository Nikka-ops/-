"""从已登录的专用 Chrome 读取 Cookie 并写入 .env — 一条命令完成重新认证。

用法（先在专用 Chrome 里登录对应站点）：
    python -m scripts.tools.refresh_cookies xhs     # 小红书（CDP 9223）
    python -m scripts.tools.refresh_cookies boss    # Boss 直聘（CDP 9222）

只更新对应站点的 Cookie 行，其余 .env 内容保持不变。
"""
from __future__ import annotations

import sys
from pathlib import Path

from scripts.config import bootstrap_env

_SITES = {
    "xhs": {
        "port": 9223,
        "domain": "xiaohongshu",
        "keys": ("a1", "web_session"),
        "env": lambda ck: [
            f"XHS_COOKIES=a1={ck.get('a1','')}; web_session={ck.get('web_session','')}",
            f"XHS_WEB_SESSION={ck.get('web_session','')}",
        ],
        "required": ("a1", "web_session"),
    },
    "boss": {
        "port": 9222,
        "domain": "zhipin",
        "keys": (),  # all cookies for the domain
        "env": lambda ck: [
            "BOSS_COOKIES=" + "; ".join(f"{k}={v}" for k, v in ck.items()),
        ],
        "required": (),
    },
}


def _read_cookies(port: int, domain: str) -> dict[str, str]:
    from DrissionPage import ChromiumOptions, ChromiumPage

    opts = ChromiumOptions()
    opts.set_address(f"127.0.0.1:{port}")
    page = ChromiumPage(addr_or_opts=opts)
    try:
        return {
            c["name"]: c["value"]
            for c in page.cookies(all_domains=True)
            if domain in (c.get("domain") or "")
        }
    finally:
        page.disconnect()


def _write_env(new_lines: list[str], prefixes: tuple[str, ...]) -> None:
    p = Path(".env")
    existing = [l.rstrip("\r") for l in p.read_text(encoding="utf-8").splitlines()] if p.is_file() else []
    keep = [l for l in existing if not any(l.strip().startswith(pre) for pre in prefixes)]
    while keep and not keep[-1].strip():
        keep.pop()
    p.write_text("\n".join(keep + [""] + new_lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    bootstrap_env()
    args = argv if argv is not None else sys.argv[1:]
    site = (args[0] if args else "").strip().lower()
    if site not in _SITES:
        print(f"用法: python -m scripts.tools.refresh_cookies [{'|'.join(_SITES)}]", file=sys.stderr)
        return 2
    cfg = _SITES[site]

    from scripts.jobs.cdp_client import cdp_port_open

    if not cdp_port_open(cfg["port"]):
        print(
            f"未检测到 CDP Chrome（端口 {cfg['port']}）。请先启动并登录该站点的专用 Chrome。",
            file=sys.stderr,
        )
        return 2

    try:
        cookies = _read_cookies(cfg["port"], cfg["domain"])
    except Exception as exc:  # noqa: BLE001
        print(f"读取 Cookie 失败: {exc}", file=sys.stderr)
        return 1

    missing = [k for k in cfg["required"] if not cookies.get(k)]
    if missing:
        print(f"缺少必要 Cookie: {missing}（请确认已登录）", file=sys.stderr)
        return 1

    new_lines = cfg["env"](cookies)
    prefixes = tuple(l.split("=", 1)[0] + "=" for l in new_lines)
    _write_env(new_lines, prefixes)
    shown = ", ".join(f"{k}={cookies[k][:10]}…" for k in (cfg["required"] or list(cookies)[:2]) if cookies.get(k))
    print(f"✓ 已更新 {site} Cookie ({shown})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
