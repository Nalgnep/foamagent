# 成都冰箱工厂 B 线 · 发泡工艺智能体管理系统

正式可运行的管理系统骨架（非静态演示页）：Python FastAPI 后端 + SQLite +
静态前端 SPA（由后端挂载提供），含真实后端逻辑：追溯异常队列、下发 8 项安全校验、
回退、审计、模型生命周期、灯塔运营与多线复制包。

> **状态说明**：本仓库为可运行的系统骨架，数据均为演示模拟数据，PLC、相机、MES/IoT 均为模拟/待对接，优化规则为本地确定性规则而非训练模型，不可直接用于真实产线控制，详见 LIMITATIONS.md。

## 快速运行（本地）

```bash
cd foaming-agent-system
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m backend.seed
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

然后打开 http://127.0.0.1:8000

等价命令（任务要求记录的运行方式）：

```bash
python -m pip install -r requirements.txt
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

## Docker 运行

```bash
docker compose up --build
# 打开 http://127.0.0.1:8000
```

## 演示登录

前端右上角选择演示用户，并随请求以 `X-User` 头传递（演示用，非生产鉴权）：

| 用户名 | 角色 | 可做 |
|---|---|---|
| process_engineer | 工艺工程师 | 优化、审批、下发、回退、知识、模型 |
| quality_inspector | 质检复核员 | 热成像复核、知识 |
| equipment_engineer | 设备/自动化工程师 | 下发、回退、模型 |
| team_leader | 班组长 | 审批、下发、回退 |
| admin | 系统管理员 | 全部（含模式切换、权重、异常修正） |

## 闭环

在线感知 → 质量判定 → 工艺分析 → 参数建议/受控下发 → 效果验证 → 知识沉淀

## API 摘要

| 方法与路径 | 说明 |
|---|---|
| GET /api/health | 健康检查 |
| GET /api/dashboard | KPI 与闭环、协议基线 |
| POST /api/boxes · GET /api/boxes | 箱体上线 |
| POST /api/process-records | 工艺参数记录 |
| POST /api/thermal-results · GET /api/thermal-results | 热成像 A/B/C/D 分级，NG 拦截 |
| POST /api/thermal-results/{id}/review | 人工复核（质检角色） |
| POST /api/trace/bind · GET /api/trace/exceptions | 多条件绑定；异常进队列不硬绑 |
| POST /api/trace/exceptions/{id}/resolve | 人工修正（管理员，审计留痕） |
| POST /api/optimize · GET /api/suggestions | 参数优化：缺陷概率、置信度、可行域、转 LLM 分流 |
| GET /api/system/state · POST /api/system/mode | 分级模式：关闭 / 人工确认 / 受控自动 |
| POST /api/system/stop · POST /api/system/resume | 异常停止 / 人工恢复 |
| POST /api/issuance · GET /api/issuances | 8 项安全校验 + 模拟 PLC 回执 |
| POST /api/issuance/{id}/rollback | 一键回退至安全基线 |
| POST /api/llm/diagnose · GET/POST /api/knowledge | 本地知识检索诊断（不控线）与专家沉淀 |
| GET /api/models · POST /api/models/{id}/promote · POST /api/models/{id}/rollback · GET /api/models/drift | 模型版本、影子晋升、回退、漂移代理指标 |
| GET /api/lighthouse · POST /api/lighthouse/weights · POST /api/changeovers | 权重、换产爬坡、9 包复制与放行门 |
| GET /api/audit · GET /api/users | 审计日志（只读）与演示用户 |

## 安全要点（代码可审计）

- LLM 工作台没有任何调用下发/PLC 的代码路径；诊断只返回证据与报告。
- 下发前必做 8 项校验：白名单、参数范围、单次步长、置信度与可行域、
  联锁与急停、数据完整性、通信状态、模式与审批；任一不通过即阻断。
- 系统停止（急停/报警/数据异常/通信异常）后一切新下发均被阻断，须人工恢复。
- 追溯异常（重复/缺失/冲突/乱序）只进异常队列，禁止凭时间相近硬绑。
- 审计日志无修改/删除接口。

## 测试

```bash
.venv/bin/python -m pytest tests/ -q
```

覆盖：追溯异常不硬绑、安全校验阻断、回退与审计、LLM 不控线。

## 目录

```
backend/app/main.py       # FastAPI 应用与全部业务端点
backend/app/models.py     # SQLite 模型（含追加式审计表）
backend/app/rules.py      # 本地确定性规则（非训练模型，见 LIMITATIONS.md）
backend/app/database.py   # 数据库连接
backend/seed.py           # 演示种子数据
frontend/                 # SPA：index.html / app.js / style.css
tests/test_smoke.py       # 冒烟测试
Dockerfile                # 容器化
docker-compose.yml        # 一键启动
```

## 局限

见 [LIMITATIONS.md](LIMITATIONS.md)。简言之：这是可运行的系统骨架，
PLC、相机、MES/IoT 均为模拟/待对接，优化规则为本地确定性规则而非训练模型，
不可直接用于真实产线控制。
