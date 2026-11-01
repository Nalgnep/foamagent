# S7CommPlus 符号网关（第二条方案）

**不重写 S7CommPlus 协议栈。** 本网关封装现成的 `s7commplus`
库（Python，0.3.0），只做网关该做的事：点表、批量读、类型转换、
断线重连、写安全、审计。经典 S7（Snap7）按绝对地址读写，访问
不了优化块；S7CommPlus 按符号名读写，所以优化块不用关优化访问
也能采，前提是变量在 CPU 上可访问、且符号名与 `browse()` 返回
的一致。

## 目录

```
gateway/
  __init__.py   # 导出 Gateway / GatewayConfig / Point
  config.py     # 点表与连接配置（密码只走环境变量，绝不进 git）
  types.py      # S7 类型转换（大端；Bool/数值/String）
  client.py     # S7CommPlusPLCClient（懒加载）+ MockPLCClient
  gateway.py    # 批量读、写安全、审计、轮询
  cli.py        # 命令行：读 / 写 / 轮询 / 浏览
  points.json   # 成都 B 线发泡示例点表（符号名需按实机替换）
  test_gateway.py
  requirements.txt
  README.md     # 本文件
```

## 快速上手（无 PLC，模拟）

```bash
python -m gateway.cli --mock --read-all
python -m gateway.cli --mock --poll --cycles 3
python -m gateway.cli --mock --write interface_material_temp_setpoint 33.5 --approved --actor process_engineer
```

模拟写被拒绝的例子（超出范围）：

```bash
python -m gateway.cli --mock --write interface_material_temp_setpoint 50 --approved
# error: interface_material_temp_setpoint=50.0 above max 45.0
```

## 接真实 PLC

```bash
pip install -r gateway/requirements.txt   # s7commplus==0.3.0
export S7_HOST=192.168.1.10 S7_PORT=102 S7_RACK=0 S7_SLOT=1
export S7_PASSWORD='...'                  # 只走环境变量，不要写进配置文件
export GATEWAY_WRITES_ENABLED=true        # 默认关闭；只读采集不需要开
python -m gateway.cli --config gateway/points.json --browse   # 先浏览，核对符号名
python -m gateway.cli --config gateway/points.json --read-all
```

注意事项：

1. **先浏览再采。** `points.json` 里的符号名是示例，必须用
   `--browse` 返回的真实符号名替换，否则读会报 unknown tag。
2. **固件与认证。** 不同固件的 S7CommPlus 认证方式不同
   （P1/P2/P3，含 TLS），以实机固件和 `s7commplus` 的支持矩阵
   为准；先在实验室 CPU 上跑通，再上产线。
3. **写只走接口 DB。** 本网关的写点表只包含接口 DB 点位，
   控制 DB 一律只读。PLC 程序必须先校验接口 DB 的值（范围、
   白名单、联锁），再应用到控制参数；网关的校验是第二道防线，
   不是唯一防线。
4. **写不重试。** 传输失败后 PLC 是否已执行是未知的，网关
   只记一条 `status="unknown"` 的审计，不会重发。人工核对
   后再决定是否重发。
5. **读可重连，写不可重连后重发。** 读失败按指数退避重连
   （默认 3 次）；写只在发送前可重连，发送后失败不重试。
6. **审计只追加。** `AuditLog` 没有修改/删除接口；生产部署
   建议把审计落到文件（`AuditLog(path=...)`）或现有审计系统。

## 写安全顺序（缺一不可）

1. 网关写开关开启（`GATEWAY_WRITES_ENABLED`）
2. 点位存在且为 `read_write`
3. 类型合法
4. 范围检查（min/max）
5. 步长检查（|新值 - 上次读值| <= max_step，有上次读值时才查）
6. 审批检查（`requires_approval` 的点位必须传 `approved=True`）
7. 单次发送，不重试；失败记 `unknown` 审计

## 与主系统的关系

主系统（`backend/`）目前用模拟数据；接线时把网关的读结果
（点名 -> 值 -> 时间戳 -> 质量戳）作为北向 JSON，喂给主系统
的工艺记录接口即可。网关本身不直接写主系统的控制参数，
也不绕过主系统的 8 项下发校验。

## 局限

- 未在真实 CPU 上验证；`s7commplus` 为较年轻的开源项目，
  使用前须按实机固件核对支持矩阵。
- Struct/UDT/数组建议拆成标量点位采；整结构点位须先确认
  布局再用。
- 本网关不是生产鉴权：`actor` 只是审计字段，生产须接
  IAM/SSO，写操作须与主系统的审批流绑定。
