"""dbf — 元数据层游戏内直提正典（dbf.unity3d → UnityPy）。

CARD / CARD_SET / CARD_SET_TIMING / CARD_TAG / CARD_RACE / KEYWORD_TEXT /
CARD_HERO / EventMap 直读 ``Data/Win/dbf.unity3d``——直提态比冻结快照更贴
现行客户端（上游裁决：本模块为元数据权威）。

语义注记（上游实证保留项）：

- ``m_locValues[12]`` = zhCN（``card`` / ``card_hero`` 折叠口径；v1 固定 zhCN，
  ``locale`` 只影响资产变体，不改 dbf 文本——已知限制，文档写明）；
- ``card_set_offline`` = 离线 GetCardSet 正典（tag 183 缺省 → CARD_SET_TIMING
  首条 ALWAYS(203) 行；离线口径仅 203 判活，表序即优先序）；
- ``card_set_pre`` = pre* 事件 timing 视图（发行口径），非离线正典；
- ``card_tag`` = plain + power_keyword（reference 排除口径）；
- ``keyword_text`` 的 ``m_name``/``m_text`` 存 GameStrings **键名**（非本地化
  文本），译文消费时经 ``Strings/<locale>/GLOBAL.txt`` 查；表内无 ``m_locValues``，
  CARD 表的 zhCN 口径对本表不适用；
- ``card_race``：race_id → is_race_tag id（第二种族起每种族一行独立布尔 tag，
  数值不在 GAME_TAG 名册，语义由本表承载）；含 race 0 等无效行，消费侧
  ``HasTag(0)`` 恒假自然跳过。

会话面：``DbfModule`` 显式路径/容器（``dbf_path`` 构造参数；``container``
优先于惰性装载——fake container 测试不得触游戏文件）。进程级 default 会话由
``install_default`` 安装（provider ``bind`` / 渲染入口调用）；``default_dbf()``
只返回已安装实例，未安装 raise（不懒建）。多批次测试必须 ``reset_default()``。

坏盘防护：``_container`` 走 ``bundle_guard.load_defended`` 进惰性层——坏块炸 =
``BundleBlockCorruptError`` 全上下文 + 恰一次瞬时重试；非 UnityFS 显式退老路并
留账。内容哈希轴（route 轴）不接——ensure 建库是重型副作用，dbf 消费面不该触发。

解析失败一律包装 ``EnvironmentUnavailable(Problem(ENVIRONMENT, "dbf_unreadable",
path=<dbf>, cause=类型+消息))``；**空表不在本模块报**（provider 的 bind 做空表守卫）；
文件不存在由 provider 先发 ``dbf_missing``。
"""
from __future__ import annotations

import os
import warnings
from functools import cached_property
from pathlib import Path

import UnityPy
from UnityPy import config as unitypy_config
from UnityPy.exceptions import UnityVersionFallbackWarning

from eidolon.contracts import EnvironmentUnavailable, Problem, ProblemKind

# Hearthstone dbf 的 header 版本本就吃 UnityPy 兜底（上游实测口径；只做解析
# 兜底，不当游戏版本闸）。
FALLBACK_UNITY_VERSION = "6000.3.11f1"


def _dbf_unreadable(dbf_path: Path, exc: Exception) -> EnvironmentUnavailable:
    """统一包装：dbf 装载/解析失败 → EnvironmentUnavailable(dbf_unreadable)。"""
    cause = f"{type(exc).__name__}: {exc}"
    return EnvironmentUnavailable(Problem(
        ProblemKind.ENVIRONMENT,
        "dbf_unreadable",
        str(dbf_path),
        f"dbf_unreadable: dbf 装载/解析失败（{cause}）",
        cause=cause,
    ))


class DbfModule:
    """dbf.unity3d 直读会话（scalar 直通、LocalizedString 取 zhCN）；显式路径/容器。"""

    def __init__(self, dbf_path: Path, *, container=None) -> None:
        self._dbf_path = Path(dbf_path)
        if container is not None:
            # 显式容器优先：预占 cached_property 槽位，惰性装载（触盘）永不发生
            # （fake container 测试不得触游戏文件）。
            self.__dict__["_container"] = container

    @cached_property
    def _container(self):
        unitypy_config.FALLBACK_UNITY_VERSION = FALLBACK_UNITY_VERSION
        # 坏盘读防护接缝（dbf.unity3d 是上游实证的第二事故位——1 B 坏整批红的那个
        # 文件）：走 load_defended 进惰性层。内容哈希轴（route 轴）不接。
        from eidolon.core.infra import bundle_guard

        with warnings.catch_warnings():
            # header 版本兜底的告警是常态路径，不应污染 stderr；其他 warning 不吞。
            warnings.simplefilter("ignore", UnityVersionFallbackWarning)
            return bundle_guard.load_defended(self._dbf_path).container

    def _read(self, name: str):
        key = f"Assets/Game/DBF-Asset/{name}.asset"
        try:
            return self._container[key].read_typetree()
        except EnvironmentUnavailable:
            raise
        except Exception as exc:                        # noqa: BLE001 —— 统一包装 dbf_unreadable
            raise _dbf_unreadable(self._dbf_path, exc) from exc

    def _read_records(self, name: str) -> list[dict]:
        try:
            return self._read(name)["Records"]
        except EnvironmentUnavailable:
            raise
        except Exception as exc:                        # noqa: BLE001 —— 同上
            raise _dbf_unreadable(self._dbf_path, exc) from exc

    @cached_property
    def event_map(self) -> dict:
        """EventMap 表（timing event id → 事件名；card_set_pre 的过滤源）。"""
        data = self._read("EventMap")
        return dict(zip(data["m_Values"], data["m_Keys"]))

    @cached_property
    def card(self) -> dict:
        """CARD 表直读（dbf id → 行 dict；LocalizedString 折叠取 ``m_locValues[12]``
        = zhCN，v1 固定口径）。"""
        out = {}
        for u in self._read_records("CARD"):
            out[u["m_ID"]] = {
                k: (v["m_locValues"][12] if isinstance(v, dict) and "m_locValues" in v else v)
                for k, v in u.items()
            }
        return out

    @cached_property
    def card_set_dict(self) -> dict:
        """CARD_SET 词典全集（set_id → 行 dict 全字段）——水印纹理与 set 过滤
        事件的正典源。"""
        return {u["m_ID"]: u for u in self._read_records("CARD_SET")}

    @cached_property
    def watermark_override(self) -> dict:
        """CARD.m_watermarkTextureOverride 非空全集（值=资产实名:GUID，迷你集
        图标为主）——水印链第一优先级。"""
        return {u["m_ID"]: u["m_watermarkTextureOverride"]
                for u in self._read_records("CARD") if u["m_watermarkTextureOverride"]}

    @cached_property
    def card_set_offline(self) -> dict:
        """离线 GetCardSet 正典：CARD_TAG 183 缺省 → CARD_SET_TIMING 首条
        ALWAYS(203) 行（离线口径仅 203 判活；表序即优先序）。mini_set 等窗口
        事件离线判不活——在线态水印行为另案。"""
        out: dict = {}
        for u in self._read_records("CARD_SET_TIMING"):
            if u["m_eventTimingEvent"] == 203 and u["m_cardId"] not in out:
                out[u["m_cardId"]] = u["m_cardSetId"]
        return out

    @cached_property
    def card_set_pre(self) -> dict:
        """pre* 事件 timing 视图（发行口径），非离线 GetCardSet 正典。"""
        return {
            u["m_cardId"]: u["m_cardSetId"]
            for u in self._read_records("CARD_SET_TIMING")
            if not self.event_map.get(u["m_eventTimingEvent"], "").startswith("pre")
        }

    @cached_property
    def card_tag(self) -> dict:
        """plain + power_keyword（reference 排除口径）：card id（str）→
        {tag id → tag value}。"""
        result: dict[str, dict] = {}
        for u in self._read_records("CARD_TAG"):
            if u["m_isPowerKeywordTag"] == 0 and u["m_isReferenceTag"] == 1:
                continue
            result.setdefault(str(u["m_cardId"]), {})[u["m_tagId"]] = u["m_tagValue"]
        return result

    @cached_property
    def card_race(self) -> dict:
        """CARD_RACE 表直读（race_id → is_race_tag id）。

        GetRaces 常规路数据面：第二种族起每种族一行独立布尔 tag（tag id=
        IsRaceTag，值=1）挂在卡自身 CARD_TAG 上；数值不在 GAME_TAG 名册
        （语义由本表承载）。表内含 race 0 等无效行——消费侧 HasTag(0) 恒假
        语义自然跳过。"""
        return {u["m_ID"]: u["m_isRaceTagId"] for u in self._read_records("CARD_RACE")}

    @cached_property
    def keyword_text(self) -> dict:
        """KEYWORD_TEXT 表直读（tag_id → 行 dict 全字段）。

        **键名表非本地化文本**：m_name/m_text 存 GameStrings 键
        （GLOBAL_KEYWORD_*），译文消费时经 Strings/<locale>/GLOBAL.txt 查
        （miss 回退=键名原串=缺译的游戏真值）。表内无 m_locValues——CARD 表的
        zhCN 口径（m_locValues[12]）对本表不适用。下游非 pythonnet 消费者经本
        property 直接查，不必起 CLR。"""
        return {u["m_tagId"]: u for u in self._read_records("KEYWORD_TEXT")}

    @cached_property
    def card_hero(self) -> dict:
        """CARD_HERO 表直读（行主键 m_ID → 记录 dict；渲染面消费
        m_cardId/m_heroType 两列）。

        判据语义：GetHeroType 终点=CardHeroDbfRecord.HeroType——
        BATTLEGROUNDS_HERO(3) → Card_Play_Bacon_Hero、BATTLEGROUNDS_GUIDE(4) →
        Card_Play_Bacon_Guide。非 GAME_TAG 判据（皮肤变体/GUIDE 明登不入）。
        m_locValues 折叠同 card 行口径。"""
        out: dict = {}
        for u in self._read_records("CARD_HERO"):
            out[u["m_cardId"]] = {
                k: (v["m_locValues"][12] if isinstance(v, dict) and "m_locValues" in v else v)
                for k, v in u.items()
            }
        return out

    @cached_property
    def card_id_to_dbf(self) -> dict[str, int]:
        """``m_noteMiniGuid``（casefold）→ ``m_ID``；空 guid 跳过；重复先到先得。

        ``CardRef(kind="card")`` 的解析面（大小写不敏感键）。"""
        out: dict[str, int] = {}
        for dbf_id, row in self.card.items():
            guid = row.get("m_noteMiniGuid")
            if not guid:
                continue
            key = str(guid).casefold()
            if key not in out:
                out[key] = dbf_id
        return out


# ----------------------------------------------------------------------------
# 进程级 default 会话（provider.bind / 渲染入口安装；测试 reset）
# ----------------------------------------------------------------------------

_DEFAULT_DBF: DbfModule | None = None


def _norm_dbf_path(p: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(p)))


def install_default(module: DbfModule) -> DbfModule:
    """安装进程级 default dbf 会话。同 dbf_path（或同实例）幂等 no-op，
    返回已装实例；异路径 raise（一进程一个 dbf 会话，与渲染身份同前提）。"""
    global _DEFAULT_DBF
    if _DEFAULT_DBF is not None:
        if module is _DEFAULT_DBF or (
                _norm_dbf_path(_DEFAULT_DBF._dbf_path) == _norm_dbf_path(module._dbf_path)):
            return _DEFAULT_DBF
        raise RuntimeError(
            f"dbf default 会话重复安装且路径不同：已装 {_DEFAULT_DBF._dbf_path}，"
            f"新值 {module._dbf_path}——一个进程只许一个 dbf 会话"
            "（跨 dbf 渲染请开新进程）")
    _DEFAULT_DBF = module
    return module


def installed_default() -> DbfModule | None:
    """已装 default 会话或 None（preflight 判「无 dbf 会话则跳过 Card 级校验」用）。"""
    return _DEFAULT_DBF


def default_dbf() -> DbfModule:
    """读进程级 default 会话；未安装 raise（不懒建——装配是 provider/入口的职责）。"""
    if _DEFAULT_DBF is None:
        raise RuntimeError(
            "dbf default 会话未安装：provider.bind / 渲染入口必须先 "
            "`dbf.install_default(DbfModule(ctx.dbf_path))` 再取用；"
            "测试用 install_default(fake_module) / reset_default()")
    return _DEFAULT_DBF


def reset_default() -> None:
    """仅测试：清掉进程级 default 会话（生产路径不得调用）。"""
    global _DEFAULT_DBF
    _DEFAULT_DBF = None
