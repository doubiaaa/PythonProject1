# -*- coding: utf-8 -*-
"""
基础设施层（Infra）：配置、日志、缓存、监控、时钟等横切能力。

与 app.utils 并存：新代码优先放此包以便与「领域/应用」边界清晰；
config、logger、disk_cache 等可逐步迁入或在此包提供门面。

详见 docs/six_layer_architecture.md。
"""
