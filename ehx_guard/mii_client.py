"""MII 上传预留接口；当前版本不发送网络请求。"""

from __future__ import annotations

import logging
from typing import Any, Mapping


class MiiClient:
    def __init__(
        self,
        *,
        enabled: bool = False,
        base_url: str = "",
        token: str = "",
        logger: logging.Logger | None = None,
    ) -> None:
        self.enabled = enabled
        self.base_url = base_url
        self.token = token
        self.logger = logger or logging.getLogger("ehx_guard.mii")

    def upload_offline_order(self, order_data: Mapping[str, Any]) -> bool:
        order_no = order_data.get("offline_order_no", "")
        if not self.enabled:
            self.logger.info("MII disabled，跳过上传 order=%s", order_no)
            return False
        self.logger.warning(
            "MII 已启用但客户接口尚未实现，未发送网络请求 order=%s base_url=%s",
            order_no,
            self.base_url,
        )
        return False
