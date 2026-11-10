"""text_codec — text 域 codec（本包 UnityPy-free 面；P2 车2）。

两物（任务书口径）：
- fontdefs：字体定义全表 JSON（enUS/zhCN 双侧；FontDefinition 8 字段+Font 对象
  元数据）→ canonical JSON blob（车1 JSON 口径：content=canonical 字节 sha）；
- font TTF：Font.m_FontData 文件字节 → **文件 sha=内容身份**（TTF 文件字节本身
  即产物，不踩 resS 坑——字体无流式外置，字节面完整自含）。

域定性：text=**卡不变全域供给**（fontdefs 表+字体文件全语料共用；26MB 级 TTF 面
per-card 挂 plan=每卡装配重复拖运，架构错位）——item 落库（domain='text'），warm
走域访问器 text() 供货（缓存一次/进程），不 per-card 进 plan_items（记账显式，
冷侧 _link_shared_items 同口径注）。

提取配方转写锚（cold 侧 text_extract.py；此处只放 codec/键/重组面）：
- font_table 裸字节 struct 解析=本仓 eidolon/core/supply/text.py:font_table；
- fontdefs 双侧解析=本仓 eidolon/core/supply/text.py:fontdefs；
- TTF locale 生效侧（zhcn 变体缺位跟 base）=本仓 eidolon/core/supply/text.py:_font_data。
"""
from __future__ import annotations

from eidolon.core.supply_index import kit_codec as KC
from eidolon.core.supply_index import schema as S

TEXT_CODEC_VERSION = 1

# FontDefinition 保留字段（本仓 eidolon/core/supply/text.py _FONTDEF_FIELDS 逐字）
FONTDEF_FIELDS = ("m_Name", "m_LineSpaceModifier", "m_SingleLineAdjustment",
                  "m_FontSizeModifier", "m_CharacterSizeModifier", "m_OutlineModifier",
                  "m_UnboundCharacterSizeModifier", "m_Font")

# blob role 词（item_blobs.role / blob_bytes 键面）
ROLE_FONTDEFS = "fontdefs"
ROLE_TTF = "ttf"


# ---------------------------------------------------------------------------
# 内容身份 + 编码（cold 调用）
# ---------------------------------------------------------------------------

def fontdefs_content_sha(fontdefs: dict) -> str:
    """fontdefs 值身份=canonical 字节 sha（车1 JSON 面口径）。"""
    return KC.json_face_sha(fontdefs)


def encode_fontdefs(fontdefs: dict) -> bytes:
    """fontdefs 落盘字节=canonical JSON（读回 json.loads 即还原）。"""
    return KC.encode_json_face(fontdefs)


def ttf_content_sha(data: bytes) -> str:
    """TTF 内容身份=**文件字节 sha**（文件即产物；任务书口径）。"""
    return S.sha256_hex(bytes(data))


def fontdefs_blob_key(payload_sha: str) -> str:
    return S.blob_key_generic(domain="text/fontdefs", content_sha=payload_sha,
                              codec="json")


def ttf_blob_key(ttf_sha: str) -> str:
    return S.blob_key_generic(domain="text/ttf", content_sha=ttf_sha, codec="ttf")


# ---------------------------------------------------------------------------
# decode（warm 调用；零 UnityPy 零游戏文件）
# ---------------------------------------------------------------------------

class TextContentError(RuntimeError):
    """text blob 内容失配（fail loud；派生物可删重建但不许坏）。"""


def decode_fontdefs(data: bytes, *, want_sha: str | None = None) -> dict:
    """canonical JSON bytes → fontdefs dict（payload sha 校验可选——warm 面恒开）。"""
    if want_sha is not None and S.sha256_hex(data) != want_sha:
        raise TextContentError("fontdefs: canonical bytes sha 失配")
    return json_loads(data)


def json_loads(data: bytes):
    import json

    return json.loads(data.decode("utf-8"))


def decode_ttf(data: bytes, *, want_sha: str | None = None) -> bytes:
    """TTF blob bytes → bytes（文件 sha 校验——内容身份面）。"""
    if want_sha is not None and S.sha256_hex(data) != want_sha:
        raise TextContentError("ttf: 文件 sha 失配")
    return data


def compare_text(cold_fontdefs: dict, warm_fontdefs: dict,
                 cold_ttfs: dict[str, bytes], warm_ttf_shas: dict[str, str]) -> dict:
    """cold 重提取 vs warm 重组 逐域比对（冷暖一致判据 text 面）：
    - fontdefs：canonical 字节 sha 相等（整面单射=逐字段相等）；
    - TTF：逐 fontdef 名文件 sha 相等（文件字节身份）。"""
    bad: list[str] = []
    if fontdefs_content_sha(cold_fontdefs) != fontdefs_content_sha(warm_fontdefs):
        bad.append("fontdefs: canonical sha mismatch")
    names = sorted(set(cold_ttfs) | set(warm_ttf_shas))
    for name in names:
        c = cold_ttfs.get(name)
        w = warm_ttf_shas.get(name)
        if c is None or w is None:
            bad.append(f"ttf {name}: 单侧缺席（cold={'有' if c is not None else '无'} "
                       f"warm={'有' if w else '无'}）")
        elif ttf_content_sha(c) != w:
            bad.append(f"ttf {name}: 文件 sha mismatch")
    return {"ok": not bad, "mismatches": bad,
            "fontdefs": 1, "ttfs": len(names)}
