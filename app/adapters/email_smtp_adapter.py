# -*- coding: utf-8 -*-
"""邮件投递：SMTP 实现，封装 `send_report_email`。"""

from __future__ import annotations

from typing import Any, Optional

from app.domain.ports import EmailDeliveryPort
from app.services.email_notify import send_report_email


class SMTPEmailDeliveryAdapter:
    __slots__ = ()

    def send_markdown_report(
        self,
        smtp_cfg: dict[str, Any],
        subject: str,
        body_md: str,
        *,
        extra_vars: Optional[dict[str, Any]] = None,
        inline_images: Optional[list[tuple[str, str]]] = None,
    ) -> tuple[bool, str]:
        return send_report_email(
            smtp_cfg,
            subject,
            body_md,
            extra_vars=extra_vars,
            inline_images=inline_images,
        )
