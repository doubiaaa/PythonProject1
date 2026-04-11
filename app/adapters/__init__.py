# -*- coding: utf-8 -*-
"""
接口层（Adapter）：外部数据源与外部服务统一收口。

行情、日历、新闻、LLM HTTP、SMTP 等实现放于此包或子模块；
领域层不依赖具体实现，仅通过端口（Protocol）由编排/应用层注入。

详见 docs/six_layer_architecture.md。
"""
