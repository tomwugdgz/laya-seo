"""Laya 本地推理引擎：System One 判别模型的离线封装。

Laya (convaiinnovations/laya) 与 Jev 共用同一套 System One 原语：
choice / noul / score，输入 (state, questions)，返回带概率与置信度的 typed answer。
因此本引擎对上层暴露与 jevseo.jev.Jev 相同的 ask() 契约，
让级联编排器可以无差别地调度两者。

与 Jev 的关键差异（决定了级联策略，见 references/cascade.md）：
1. Jev 是生成式云端 LLM，按 token 计费；Laya 是本地判别模型，零成本、离线、毫秒级。
2. Laya 输出**额外**携带 action.act_probability（System One 原生字段）。
3. 实测（2026-10-04，4 个已知答案的 SEO 中文页面）：page_type 准确率 2/4，
   且错误与高置信度正相关——文章页被判为 homepage 时置信度仍达 0.962。
   因此 Laya **不能单独充当权威**，只能做置信度闸门。
4. 权重在金融交易语料上训练，state 上限约 1024 token。

离线守卫：必须在 import laya / transformers 之前设置环境变量，
否则 transformers 会尝试联网并卡死在代理上。本模块在模块导入时即完成设置。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: 默认权重根目录（与 PA_Agent 保持一致，避免重复占用 600MB）
DEFAULT_MODEL_DIR = Path.home() / "laya-models" / "laya"
DEFAULT_SUBFOLDER = "multilingual"

#: 权重完整性校验清单，与 PA_Agent 的 check_weights 一致
REQUIRED_WEIGHTS = (
    "rl_agent_config.json",
    "model.safetensors",
    "tokenizer/tokenizer.json",
    "tokenizer/tokenizer_config.json",
    "encoder/config.json",
)


class LayaUnavailable(RuntimeError):
    """Laya 运行时或权重不可用。message 面向终端用户，可直接展示。"""


def prepare_offline_env() -> None:
    """在 import laya / transformers 之前调用。

    USE_TF=0 / TRANSFORMERS_NO_TF=1：跳过 TensorFlow 探测（慢且可能死锁）。
    HF_HUB_OFFLINE=1 / TRANSFORMERS_OFFLINE=1：权重已本地化，
    任何联网尝试都应立即报错而非静默等待代理超时。
    """
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


# 模块导入即设防：任何在此之前发生的 transformers 导入都会尝试联网
prepare_offline_env()


def check_runtime() -> str | None:
    """预检 laya 包是否可导入。返回 None 表示可用，否则为失败原因。"""
    try:
        import laya  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return f"Laya 库未安装或导入失败：{type(exc).__name__}: {exc}"
    return None


def check_weights(model_dir: str | Path, subfolder: str) -> str | None:
    """校验本地权重完整性。返回 None 表示可用。"""
    root = Path(model_dir)
    if not root.is_dir():
        return f"权重目录不存在：{root}"
    sub = root / subfolder if subfolder else root
    missing = [name for name in REQUIRED_WEIGHTS if not (sub / name).exists()]
    if missing:
        return f"权重目录 {sub} 缺少文件：{', '.join(missing)}（重跑 D:\\PA_Agent\\tools\\download_laya.py）"
    return None


def doctor(model_dir: str | Path = DEFAULT_MODEL_DIR, subfolder: str = DEFAULT_SUBFOLDER) -> dict:
    """诊断信息，供 CLI doctor 使用。绝不打印密钥或权重内容。"""
    info: dict[str, Any] = {
        "engine": "laya",
        "model_dir": str(model_dir),
        "subfolder": subfolder,
        "weights": "missing",
        "runtime": "unknown",
        "device": None,
        "reason": None,
    }
    reason = check_runtime()
    if reason:
        info["runtime"] = "unavailable"
        info["reason"] = reason
        return info
    info["runtime"] = "ok"

    reason = check_weights(model_dir, subfolder)
    if reason:
        info["reason"] = reason
        return info
    info["weights"] = "ok"

    # 只探测设备，不加载权重：加载 600MB 权重只为报一个设备名不值
    try:
        import torch

        info["device"] = "cuda" if torch.cuda.is_available() else "cpu"
        info["torch"] = torch.__version__
        if torch.cuda.is_available():
            info["gpu"] = torch.cuda.get_device_name(0)
    except Exception:  # noqa: BLE001
        info["device"] = "unknown"
    return info


class LayaEngine:
    """单实例封装。权重约 1.6GB 内存，禁止重复加载。

    predict() 串行化：并发调用同一份模型既无收益也有风险。
    """

    _lock = threading.Lock()
    _instance: "LayaEngine | None" = None

    def __init__(self, *, model_dir: str | Path, subfolder: str, device: str = "auto") -> None:
        self.model_dir = str(model_dir)
        self.subfolder = subfolder
        self.device_req = device
        self._agent: Any = None
        self._infer_lock = threading.Lock()
        self.load_ms: float = 0.0
        self.device: str = ""

    @classmethod
    def get(cls, *, model_dir: str | Path = DEFAULT_MODEL_DIR, subfolder: str = DEFAULT_SUBFOLDER,
            device: str = "auto") -> "LayaEngine":
        """按配置取单例；配置变化时重建。"""
        with cls._lock:
            inst = cls._instance
            if (inst is not None and inst.model_dir == str(model_dir)
                    and inst.subfolder == subfolder and inst.device_req == device):
                return inst
            cls._instance = cls(model_dir=model_dir, subfolder=subfolder, device=device)
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    @property
    def loaded(self) -> bool:
        return self._agent is not None

    def ensure_loaded(self, log=print) -> Any:
        """加载权重并返回 Agent。线程安全、幂等。"""
        if self._agent is not None:
            return self._agent
        with self._infer_lock:
            if self._agent is not None:
                return self._agent

            reason = check_runtime()
            if reason:
                raise LayaUnavailable(reason)
            reason = check_weights(self.model_dir, self.subfolder)
            if reason:
                raise LayaUnavailable(reason)

            prepare_offline_env()
            t0 = time.perf_counter()
            try:
                import laya

                # device=None 让 laya 自己解析：cuda > mps > xpu > cpu
                device = None if self.device_req in ("", "auto") else self.device_req
                agent = laya.load(self.model_dir, subfolder=self.subfolder or None, device=device)
            except Exception as exc:  # noqa: BLE001
                raise LayaUnavailable(f"Laya 权重加载失败：{type(exc).__name__}: {exc}") from exc
            self.load_ms = (time.perf_counter() - t0) * 1000
            self.device = str(getattr(agent, "device", ""))
            log(f"Laya 权重加载完成（{self.load_ms / 1000:.1f}s，设备 {self.device or '?'}）")
            self._agent = agent
            return agent

    def predict(self, state: dict, questions: dict, *, lang: str = "zh") -> dict:
        """同步推理。返回 jevseo.jev.validate() 可直接消费的 raw answers。"""
        agent = self.ensure_loaded()
        with self._infer_lock:
            try:
                return agent.predict(state, questions, lang=lang)
            except Exception as exc:  # noqa: BLE001
                raise LayaUnavailable(f"Laya 推理失败：{type(exc).__name__}: {exc}") from exc

    def ask(self, state: dict, questions: dict, *, log=print) -> dict | None:
        """与 Jev.ask 同签名。失败返回 None（记录进 ledger），绝不抛出。"""
        try:
            raw = self.predict(state, questions)
        except LayaUnavailable as err:
            logger.warning("Laya 不可用：%s", err)
            return None
        except Exception as err:  # noqa: BLE001  任何异常都是一次记录的失败，不是崩溃
            logger.warning("Laya 推理异常：%s", err)
            return None
        answers = raw.get("answers") or {}
        missing = set(questions) - set(answers)
        if missing:
            logger.warning("Laya 答案缺失：%s", sorted(missing))
            return None
        return answers
