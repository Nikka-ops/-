"""Job source connectors."""
from scripts.jobs.connectors.bytedance import ByteDanceConnector
from scripts.jobs.connectors.tencent import TencentConnector
from scripts.jobs.connectors.meituan import MeituanConnector
from scripts.jobs.connectors.netease import NetEaseConnector
from scripts.jobs.connectors.xiaomi import XiaomiConnector
from scripts.jobs.connectors.kuaishou import KuaishouConnector
from scripts.jobs.connectors.boss_zhipin import BossZhipinConnector
from scripts.jobs.connectors.job_pro import JobProConnector

__all__ = [
    "ByteDanceConnector",
    "TencentConnector",
    "MeituanConnector",
    "NetEaseConnector",
    "XiaomiConnector",
    "KuaishouConnector",
    "BossZhipinConnector",
    "JobProConnector",
]
