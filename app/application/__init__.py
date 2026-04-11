# -*- coding: utf-8 -*-
"""
应用服务层（Application / 服务层）：用例级业务规则，可测试、副作用经端口注入。

与历史包名 app.services 区分：新「无 IO 纯规则」优先放此包；
旧 app.services 将逐步按领域拆迁至此与 adapters/output。

详见 docs/six_layer_architecture.md。
"""
