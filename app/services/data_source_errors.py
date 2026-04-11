# -*- coding: utf-8 -*-
"""数据源异常分级，供上层捕获与日志。"""


class DataSourceError(Exception):
    """数据源基类。"""


class DataSourceTimeoutError(DataSourceError):
    """请求超时或长时间无响应。"""


class DataSourceInvalidError(DataSourceError):
    """返回结构缺失关键字段或无法解析。"""


class DataSourceExhaustedError(DataSourceError):
    """重试耗尽仍失败。"""


class DataSourceCircuitOpenError(DataSourceError):
    """熔断打开：短时不再请求该数据源。"""
