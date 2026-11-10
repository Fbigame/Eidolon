"""游戏 "名字:GUID" AssetReference 解析器（渲染链资产定位正典）。

复现游戏定位链（上游逆向定案，语义照抄
AssetLoader.GetRuntimeAssetVariant / ScriptableAssetManifest.TryResolveAsset）：

    代码常量 "Card_Hand_Ally.prefab:d00eb..."   (AssetReference，名字:GUID)
      → asset_manifest.unity3d 变体解析（locale 覆盖查 asset_manifest_{locale}.unity3d；
        平台覆盖查主包 asset_catalog_platform_phone；默认 base/enUS，与 PC 运行时一致）
      → base_assets_catalog: GUID → bundle 文件名（392,791 条，一次性载入缓存）
      → 打开 bundle → env.container[GUID] = 对象（container 键即裸小写 GUID）

用法（import 面）：
    from eidolon.core.infra.resolve_asset_ref import Resolver, resolve
    result = resolve("Card_Hand_Ally.prefab:d00eb...", locale="zhcn")

内部形态（批2c 拆分）：Resolver=组合门面——ManifestIndex（定位半程，manifest 纯表，
不持 bundle env）+ BundleStore（打开半程，bundle env 零驱逐驻留）；locate()=定位半程
显式接口（全程不开 bundle），warm()=批量预热；对外 API 与拆分前一致。

内置一致性检查（每项独立输出 pass/fail，不静默通过）：
    ① name-consistency   三源名称一致：引用名 stem == 对象 m_Name；
                          container 键 == 解析 GUID（本游戏 container 无路径只有 GUID，
                          故"路径 basename"退化为 GUID 恒等，见实验 findings）
    ② type-vs-extension  类型符合后缀预期（.prefab→GameObject / .mat→Material /
                          .psd→Texture2D / .asset→MonoBehaviour …；未知后缀记 skipped）
    ③ registration       登记一致：catalog 指向的 bundle == 对象实际所在 bundle 且文件
                          存在；locale 变体时另查：变体 GUID 在变体 bundle 命中、
                          变体 GUID 与 base catalog 的交叉登记

另附跨包 PPtr 解析（resolve_pptr；定位序 v6：进程内 CAB 归属 → route 全局 cabs 表
（命中只开 owner 包）→ bundle_deps 依赖闭包扫描兜底）。
只读游戏目录：Data/Win 由 GameContext 流入（契约 D；缺省=ctx.data_win，无硬编码默认）。
「无 bundle / 无 guid / 无对象」一律 ``GameAssetMissing``（设计 §5.3 边界），不再裸
assert / 返回 None。上游的 bundle 遥测 / 访问统计 / legacy 老路 A/B 开关已随去 env
删除（缺省行为=route → 惰性 → UnityPy.load 固化）。

注意：quality/region 变体在当前 asset_manifest.unity3d 中无对应 catalog 资产
（仅 platform_phone + 各语言包），resolve(..., quality=...) 为保留参数、当前 no-op。
变体叠加顺序按游戏 Load 次序近似为 platform → locale（locale 最后生效）；
CompositeAssetCatalog 未反编译到，本工具的叠加语义是近似，单层覆盖时与游戏一致。
"""
from __future__ import annotations

from collections import Counter, OrderedDict
from pathlib import Path

import UnityPy

import eidolon.core.infra.bundle_guard as bundle_guard
import eidolon.core.infra.bundle_lazy as bundle_lazy
import eidolon.core.infra.object_cache as object_cache
import eidolon.core.infra.route as route
from eidolon.core.infra import context   # 契约 D：Data/Win 缺省=GameContext（入口显式 install）
from eidolon.core.infra.errors import GameAssetMissing

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.11f1"

# bundle 缓存不驱逐（批2b-3 2026-10-14 定案）：全语料累计工作集实测 1035 包/2887MB 盘面
# （≈10-13GB 实驻，3.7× 膨胀标定），j≤2 配对下 32GB 机器全装得下，且顺序 full 实证
# cold=1045≈首触地板（重访=10）——零抖动。预算驱逐机制整体拆除（j8 多 worker 形态
# 弃用：6 worker 循环实证冷开 4.85×+峰值 26.8GB，账见 consumer-arch 实验档 NOTES 批2b-2/2b-3）。
# （上游的 env 预算旋钮随该机制退役。）

# 惰性路退回账（判据 3：退回必须显式且入账，不得静默）
_LAZY_FALLBACKS: list[tuple[str, str]] = []

def _default_win() -> Path:
    """缺省 Data/Win=GameContext（契约 D：ctx.data_win 流入；未安装=raise fail-loud）。"""
    return context.current().data_win

# 后缀 → 允许的 Unity 对象类型名（类型不匹配即 check ② fail）
EXT_EXPECTED_TYPES: dict[str, set[str]] = {
    "prefab": {"GameObject"},
    "mat": {"Material"},
    "psd": {"Texture2D"},
    "png": {"Texture2D"},
    "tif": {"Texture2D"},
    "tiff": {"Texture2D"},
    "tga": {"Texture2D"},
    "jpg": {"Texture2D"},
    "jpeg": {"Texture2D"},
    "exr": {"Texture2D"},
    "asset": {"MonoBehaviour"},
    "wav": {"AudioClip"},
    "ogg": {"AudioClip"},
    "mp3": {"AudioClip"},
    "mesh": {"Mesh"},
    "controller": {"AnimatorController"},
    "playable": {"PlayableAsset"},
    "shader": {"Shader"},
    "font": {"Font"},
    "ttf": {"Font"},
    "otf": {"Font"},
}


class PPtrError(Exception):
    """PPtr 解析失败。reason ∈ {empty_slot, builtin, no_external, missing_cab, missing_pathid, error}

    分类不变量（consumer-arch 批9a，2026-10-12）：builtin=引擎内建资源引用（unity
    default resources/builtin_extra，游戏包不发货）——查表成功的正确结论，容忍不记账；
    其余 reason=未知外部依赖 miss——**恒为零**的渲程不变量，出现即 unknown 台账+
    门红（语义：游戏新版本把某真依赖挪出了本仓依赖闭包）。"""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


# 未知 miss 台账（进程级；builtin 不入账——批9a 分类不变量）
_UNKNOWN_MISSES: list[str] = []
_MISS_MARK: int = 0


def record_pptr_miss(exc: "PPtrError", ctx: str = "") -> None:
    """catch 点统一上账：builtin 静默容忍，未知入台账。"""
    if exc.reason == "builtin":
        return
    line = f"{exc.reason}: {exc.detail}" + (f" ({ctx})" if ctx else "")
    if line not in _UNKNOWN_MISSES:
        _UNKNOWN_MISSES.append(line)


def unknown_misses_since(mark: int) -> list[str]:
    """mark 之后的未知 miss 明细（渲染会话增量；mark=unknown_miss_count() 快照）。"""
    return _UNKNOWN_MISSES[mark:]


def unknown_miss_count() -> int:
    return len(_UNKNOWN_MISSES)


def _iter_serialized(env):
    """深度优先枚举 env 里全部 SerializedFile（bundle 内多个 CAB）。"""
    from UnityPy.files import SerializedFile

    def walk(file):
        if isinstance(file, SerializedFile):
            yield file
            return
        subs = getattr(file, "files", None)
        if isinstance(subs, dict):
            for sub in subs.values():
                yield from walk(sub)

    for f in env.files.values():
        yield from walk(f)


class ManifestIndex:
    """定位半程（纯表）：manifest 侧全部表载入与查询——catalog / catalog_duplicate_guids
    / bundle_deps / platform_catalog / locale_catalog / cards_map / card_def_ref。
    不持有 bundle env、不打开任何游戏 bundle；asset_manifest.unity3d 的 env 在四张
    manifest 表全部载入后释放引用（locale 表来自独立 asset_manifest_{locale}.unity3d，
    逐次读表即弃）。"""

    # manifest 主包背书的四张表（全载入后可释放主包 env 引用）
    _MANIFEST_TABLES = ("catalog", "bundle_deps", "platform_catalog", "cards_map")

    def __init__(self, game_win: str | Path):
        self.win = Path(game_win)
        self._manifest_env = None
        self._catalog: dict[str, str] | None = None
        self._catalog_dup_guids: set[str] | None = None
        self._bundle_deps: dict[str, list[str]] | None = None
        self._cards_map: dict[str, str] | None = None
        self._platform_catalog: dict[str, tuple[str, str]] | None = None
        self._locale_catalogs: dict[str, dict[str, tuple[str, str]]] = {}

    # ---------- manifest 侧 ----------

    def _route_used_hash(self, path: Path) -> None:
        """manifest/locale 包若已入航线库，则消费前做 used-hash（P0 同路）。

        只读现有库（不因一次 manifest 读取触发全量建库）；内容失配 → 单次自动
        重建后重试，仍失配 → ``BundleContentMismatch``（ENV 3）。无已装 ctx /
        route off / 库不存在 / 行不存在 → 零行为。
        """
        ctx = context.installed()
        if ctx is None:
            return
        tables = route.peek_existing(root=ctx.route_cache, mode=ctx.route_mode,
                                     data_win=self.win, version=ctx.version)
        if tables is None:
            return
        try:
            if not tables.has(path.name):
                return
            if route.verify_used(path.name, tables, self.win):
                return
            new = route.heal_content_mismatch(
                path.name, tables, root=ctx.route_cache, mode=ctx.route_mode,
                data_win=self.win, version=ctx.version)
            tables = new
            if not route.verify_used(path.name, new, self.win):
                raise route.content_mismatch(path.name, "manifest/locale 重建后仍失配")
        finally:
            try:
                tables.close()
            except Exception:                          # noqa: BLE001
                pass

    def _manifest(self):
        if self._manifest_env is None:
            # 坏盘读防护收口（2026-11-08 判据卡覆盖面）：manifest 主包是门路径每跑必读
            # 的 UnityFS bundle，直连 UnityPy.load 坏块无上下文 → load_defended 惰性层。
            path = self.win / "asset_manifest.unity3d"
            self._route_used_hash(path)               # P0：有行则 used-hash（同路）
            self._manifest_env = bundle_guard.load_defended(path)
        return self._manifest_env

    def _read_manifest_asset(self, suffix: str) -> dict:
        for key, obj in self._manifest().container.items():
            if key.lower().endswith(suffix.lower()):
                return obj.read_typetree()
        raise KeyError(f"asset_manifest.unity3d 无 {suffix}")

    def _maybe_release_manifest(self) -> None:
        """纯表化（批2c）：四张 manifest 表全部在内存后释放 asset_manifest.unity3d 的
        env 引用（表已抽干，env 不再被需要；万一要重读走 _manifest() 懒重载）。"""
        if self._manifest_env is not None and all(
                getattr(self, f"_{t}") is not None for t in self._MANIFEST_TABLES):
            self._manifest_env = None

    @property
    def catalog(self) -> dict[str, str]:
        """base_assets_catalog：GUID → bundle 文件名。"""
        if self._catalog is None:
            data = self._read_manifest_asset("/base_assets_catalog.asset")
            names = data["m_bundleNames"]
            pairs = [(a["guid"], names[a["bundleId"]]) for a in data["m_assets"]]
            dup = {g for g, c in Counter(g for g, _ in pairs).items() if c > 1}
            self._catalog_dup_guids = dup
            self._catalog = dict(pairs)
            self._maybe_release_manifest()
        return self._catalog

    @property
    def catalog_duplicate_guids(self) -> set[str]:
        self.catalog  # 触发载入
        assert self._catalog_dup_guids is not None
        return self._catalog_dup_guids

    @property
    def bundle_deps(self) -> dict[str, list[str]]:
        """bundle_deps：bundle → 依赖 bundle 列表（allDependencies，含传递闭包）。"""
        if self._bundle_deps is None:
            data = self._read_manifest_asset("/bundle_deps.asset")
            names = data["allBundleNames"]
            self._bundle_deps = {
                n: [names[i] for i in d["allDependencies"] if names[i] != n]
                for n, d in zip(names, data["bundles"])
            }
            self._maybe_release_manifest()
        return self._bundle_deps

    @property
    def platform_catalog(self) -> dict[str, tuple[str, str]]:
        """asset_catalog_platform_phone：baseGuid → (变体 guid, bundle)。"""
        if self._platform_catalog is None:
            data = self._read_manifest_asset("/asset_catalog_platform_phone.asset")
            names = data["m_bundleNames"]
            self._platform_catalog = {
                a["baseGuid"]: (a["guid"], names[a["bundleId"]]) for a in data["m_assets"]
            }
            self._maybe_release_manifest()
        return self._platform_catalog

    def locale_catalog(self, locale: str) -> dict[str, tuple[str, str]]:
        """asset_manifest_{locale}.unity3d：baseGuid → (变体 guid, bundle)。"""
        code = locale.lower()
        if code in ("enus", "enus", "", "global", "none"):
            return {}
        if code not in self._locale_catalogs:
            path = self.win / f"asset_manifest_{code}.unity3d"
            if not path.is_file():
                raise FileNotFoundError(f"无 {path.name}（可用 locale 见 Data/Win 下 asset_manifest_*）")
            self._route_used_hash(path)               # P0：有行则 used-hash（同路）
            env = bundle_guard.load_defended(path)   # 坏盘读防护收口（2026-11-08 覆盖面）
            data = None
            for key, obj in env.container.items():
                if key.lower().endswith(f"asset_catalog_locale_{code}.asset"):
                    data = obj.read_typetree()
                    break
            if data is None:
                raise KeyError(f"{path.name} 内无 asset_catalog_locale_{code}.asset")
            names = data["m_bundleNames"]
            self._locale_catalogs[code] = {
                a["baseGuid"]: (a["guid"], names[a["bundleId"]]) for a in data["m_assets"]
            }
        return self._locale_catalogs[code]

    @property
    def cards_map(self) -> dict[str, str]:
        """cards_map：cardId → "名字.prefab:GUID"（CardDef 引用）。"""
        if self._cards_map is None:
            m = self._read_manifest_asset("/cards_map.asset")["map"]
            self._cards_map = dict(zip(m["keys"], m["values"]))
            self._maybe_release_manifest()
        return self._cards_map

    def card_def_ref(self, card_id: str) -> str | None:
        return self.cards_map.get(card_id)

    def card_working_set(self, card_ids, *, locale: str | None = None,
                         platform: str | None = None) -> dict:
        """卡集 → bundle 工作集（定位半程；全程不开任何 bundle）。

        每卡：cards_map → "名字.prefab:GUID" → 变体叠加（platform → locale，
        与 :meth:`Resolver.locate` 同判据）→ bundle + `bundle_deps[bundle]`
        传递闭包（allDependencies 已含闭包）。B 案 route scoped 建库
        （``route.prewarm``）的工作集权威面。

        返回 ``{"bundles": sorted(union), "missing": [card_id...],
        "per_card": {card_id: bundle}}``——missing = cards_map/manifest 查无
        （该卡不进工作集；渲染时照旧解析报错，不静默扩大覆盖面）。
        """
        bundles: set[str] = set()
        per_card: dict[str, str] = {}
        missing: list[str] = []
        for card_id in card_ids:
            ref = self.card_def_ref(card_id)
            if not ref:
                missing.append(card_id)
                continue
            guid = ref.rsplit(":", 1)[-1].lower()
            resolved_guid = guid
            variant_bundle = None
            if platform == "phone" and resolved_guid in self.platform_catalog:
                vguid, vbundle = self.platform_catalog[resolved_guid]
                resolved_guid, variant_bundle = vguid, vbundle
            if locale:
                lc = self.locale_catalog(locale)
                if resolved_guid in lc:
                    resolved_guid, variant_bundle = lc[resolved_guid]
            bundle = self.catalog.get(resolved_guid) or variant_bundle
            if not bundle:
                missing.append(card_id)
                continue
            bundles.add(bundle)
            bundles.update(self.bundle_deps.get(bundle, []))
            per_card[card_id] = bundle
        return {"bundles": sorted(bundles), "missing": missing, "per_card": per_card}


class BundleStore:
    """打开半程：bundle env 驻留（零驱逐形态，批2b-3 定案原样）+ container_get /
    find_by_name / resolve_pptr + CAB 归属索引（_cabs_owner/_cab_unreachable）。
    resolve_pptr 的依赖闭包查表（bundle_deps）经构造注入的 ManifestIndex——纯表借用，
    本类不持有任何 manifest env。"""

    def __init__(self, game_win: str | Path, index: ManifestIndex | None = None):
        self.win = Path(game_win)
        self._index = index
        self._envs: OrderedDict[str, object] = OrderedDict()   # 驻留集（批2b-3：不驱逐，进程级常驻）
        self._envs_sizes: dict[str, int] = {}
        self._opens: dict[str, int] = {}   # 数据面：逐包累计访问数（喂 bundle 遥测报告）
        self._cabs_owner: dict[str, str] = {}
        self._cab_unreachable: set[str] = set()  # 确认找不到的 CAB，避免重扫依赖
        self._route = None                 # 航线表（ctx.route_mode 三态；懒加载，off 时为 None）
        self._route_tried = False
        self._ctx = None                   # ensure 时的 GameContext（自动重建/健康门复用）
        self._route_bundles: dict[str, object] = {}   # bundle → LazyBundle（mmap 生命周期）
        # 对象级缓存是**返回边界**的事（句柄携带 (bundle, guid)），不需要装配/补丁；
        # 开关与账见 scripts/infra/object_cache.py（v2：不 monkeypatch、无默认值兜底）。

    @property
    def bundle_deps(self) -> dict[str, list[str]]:
        """resolve_pptr 的 CAB 依赖闭包查表入口（ManifestIndex 纯表转发）。"""
        return self._index.bundle_deps

    def _lookup_cab_owner(self, target: str) -> str | None:
        """cab→bundle：route.db 全局 cabs 表（v6）；miss 显式计数。

        上游的 cabmap.db 兜底不搬：产品没有 route=off——route 表足够，miss 回
        `bundle_deps` 依赖闭包扫描（调用方 `_resolve_pptr` 负责），不静默。
        """
        owner = None
        if self._route is not None:
            owner = self._route.cab_owner(target)
        if owner is None:
            route._bump("cab_owner_miss")
        else:
            route._bump("cab_owner_hit")
        return owner

    def open_bundle(self, bundle: str):
        self._opens[bundle] = self._opens.get(bundle, 0) + 1
        env = self._envs.get(bundle)
        if env is not None:
            return env
        path = self.win / bundle
        if not path.is_file():
            raise FileNotFoundError(f"bundle 不存在: {path}")
        # 三条路，优先级：航线重建（批量产出缓存；三态/缓存根=GameContext 显式流入）
        # → 惰性解析 → 老路（上游 legacy A/B 开关已删，缺省行为固化）。
        env = None
        if self._route is None and not self._route_tried:
            self._route_tried = True
            _ctx = context.current()             # 契约 D：route 三态/缓存根/版本=ctx
            self._ctx = _ctx
            self._route = route.ensure(               # off→None；auto→命中或建库
                root=_ctx.route_cache, mode=_ctx.route_mode,
                data_win=self.win, version=_ctx.version)
        # 显式 expected / good_dir 的守卫面保留；**不**再把 route 行账交给
        # bundle_guard 的 stat 信任门——route 行消费统一走下面的 used-hash
        # （stat 相同也要哈希，失配才能触发单次自动重建）。
        path = bundle_guard.vetted_path(path)
        if self._route is not None and not self._route.has(bundle):
            # B 案 scoped 库缺行（工作集外）：lazy 补行——只对 meta.scope=cards
            # 生效（全量库缺行=游戏更新面，维持既有惰性兜底）。补行成功即走
            # 下方 route 路；失败/拒绝也惰性兜底，绝不假命中（缺行≠有库读错）。
            route._bump("route_row_missing")
            route.augment_row(self._route, path)
        if self._route is not None and self._route.has(bundle):
            br = None
            try:
                if not route.verify_used(bundle, self._route, data_win=self.win):
                    # used-hash 失配：stale 计数/日志已在 route 内落账；锁内重建一次
                    _ctx = self._ctx or context.current()
                    self._route = route.heal_content_mismatch(
                        bundle, self._route, root=_ctx.route_cache,
                        mode=_ctx.route_mode, data_win=self.win,
                        version=_ctx.version)
                br = bundle_lazy.LazyBundle(path)
                env = route.open_env(bundle, self._route, br)
                self._route_bundles[bundle] = br  # mmap 生命周期随 env
            except bundle_guard.BundleContentMismatch:
                if br is not None:                # 失败即关，别让 mmap 泄漏
                    br.close()
                raise                             # ENV 3：不吞、不退化成惰性
            except Exception as exc:              # noqa: BLE001
                route.STATS["route_rebuild_failed"] = \
                    route.STATS.get("route_rebuild_failed", 0) + 1
                _LAZY_FALLBACKS.append((bundle, f"route: {type(exc).__name__}: {exc}"))
                if br is not None:                # 失败即关，别让 mmap 泄漏（实测退出崩溃源）
                    br.close()
                env = None
        if env is None:
            try:
                env = bundle_lazy.open_env(path)
            except bundle_lazy.LazyUnsupported as exc:
                _LAZY_FALLBACKS.append((bundle, str(exc)))
                env = UnityPy.load(str(path))
        self._envs[bundle] = env
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        self._envs_sizes[bundle] = size
        for sf in _iter_serialized(env):
            name = Path(str(getattr(sf, "name", ""))).name.lower()
            if name:
                self._cabs_owner.setdefault(name, bundle)
        return self._envs[bundle]

    def container_get(self, bundle: str, guid: str):
        """container 精确 GUID 键优先，退化为 endswith 扫描（兼容带路径键的包）。
        注意 UnityPy 的 env.container 是代理对象（无 .get），值是 PPtr，需 deref。

        返回 `(ObjectHandle, container 键)`；handle 鸭子型兼容 ObjectReader，且**自带地址**
        `(bundle, guid)`——身份不靠从对象反推（v1 事故根因，见 object_cache docstring）。
        无对象（精确键与 endswith 扫描均未命中）→ ``GameAssetMissing``（设计 §5.3
        边界，不再裸 None）；bundle 文件缺失由 ``open_bundle`` 的 FileNotFoundError
        向上抛（调用方按原类型判定）。"""
        obj, key = object_cache.memo_container(bundle, guid,
                                               lambda: self._container_get(bundle, guid))
        if obj is None:
            raise GameAssetMissing(
                path=f"{bundle}::{guid}",
                message=f"asset_missing_in_game: bundle {bundle} 的 container 无对象 {guid}"
                        "（精确键与后缀扫描均未命中）")
        return obj, key

    def _container_get(self, bundle: str, guid: str):
        env = self.open_bundle(bundle)
        pptr = env.container.container_dict.get(guid)
        if pptr is not None:
            return pptr.deref(), guid
        for key, cand in env.container.items():
            if key.endswith(guid):
                return cand, key
        return None, None

    def find_by_name(self, bundle: str, name: str) -> list[tuple[str, str]]:
        """在 bundle container 里按对象名反查：返回 [(guid(container 键), 类型名)]。
        拆包资源 → manifest 反查（B 方向）用。"""
        env = self.open_bundle(bundle)
        hits = []
        for key, obj in env.container.items():
            try:
                if obj.read_typetree().get("m_Name") == name:
                    hits.append((key, obj.type.name))
            except Exception:  # noqa: BLE001
                continue
        return hits

    # ---------- PPtr（跨 bundle，bundle_deps CAB 图） ----------

    def resolve_pptr(self, cur_bundle: str, ptr: dict, owner_obj=None):
        """解 PPtr → (对象, 所在 bundle)。失败抛 PPtrError（reason 可分类统计）。

        memo 面的键 = `(owner 的 CAB 名, file_id, path_id)`：一个 bundle 内可有多个
        SerializedFile，externals 表按 CAB 各自不同，故**不得用 bundle 名冒充 CAB**。
        owner 未持有 assets_file 时（调用方未给 owner）→ 显式跳过缓存并计数（object_cache
        `skip_pptr_no_cab`），不以任何默认值继续。"""
        own = getattr(owner_obj, "assets_file", None) if owner_obj is not None else None
        cab = str(getattr(own, "name", "") or "").lower() or None
        file_id = ptr.get("m_FileID", 0)
        path_id = ptr.get("m_PathID", 0)
        if file_id is None or path_id is None:
            raise PPtrError("bad_ptr", f"PPtr 字段缺失：{ptr!r}")
        return object_cache.memo_pptr(
            cur_bundle, cab, int(file_id), int(path_id),
            lambda: self._resolve_pptr(cur_bundle, ptr, owner_obj=owner_obj))

    def _resolve_pptr(self, cur_bundle: str, ptr: dict, owner_obj=None):
        """解 PPtr → (对象, 所在 bundle)。失败抛 PPtrError（reason 可分类统计）。"""
        path_id = ptr.get("m_PathID", 0)
        if not path_id:
            raise PPtrError("empty_slot", "m_PathID == 0（空槽位）")
        file_id = ptr.get("m_FileID", 0)
        env = self.open_bundle(cur_bundle)

        if file_id == 0:  # 同 bundle 内引用
            own = getattr(owner_obj, "assets_file", None)
            if own is not None and path_id in own.objects:
                return own.objects[path_id], cur_bundle
            for sf in _iter_serialized(env):
                if path_id in sf.objects:
                    return sf.objects[path_id], cur_bundle
            raise PPtrError("missing_pathid", f"{cur_bundle} 内无 pathID {path_id}")

        # 外部引用：owner 的 serialized file externals 给出目标 CAB 名
        own = getattr(owner_obj, "assets_file", None)
        target = None
        candidates: list[str] = []
        for sf in ([own] if own is not None else []) + list(_iter_serialized(env)):
            exts = list(getattr(sf, "externals", None) or [])
            if len(exts) >= file_id:
                candidates.append(Path(exts[file_id - 1].path).name.lower())
        target = next((c for c in candidates if c), None) if candidates else None
        if target is None:
            raise PPtrError("no_external", f"externals[{file_id - 1}] 不存在")

        if "unity default resources" in target or "unity_builtin_extra" in target:
            raise PPtrError("builtin", target)

        # 查询序（v6）：进程内 `_cabs_owner` → route 全局 cabs（`_lookup_cab_owner`，
        # 命中只开 owner 包并校验 `(cab, path_id)`）→ `bundle_deps` 闭包扫描兜底。
        # 表未命中 / owner 校验失败都显式计数，不静默错。
        if target not in self._cabs_owner and target not in self._cab_unreachable:
            owner = self._lookup_cab_owner(target)
            if owner is not None:
                was_open = owner in self._envs
                try:
                    denv = self.open_bundle(owner)
                except Exception:  # noqa: BLE001
                    route._bump("cab_owner_open_failed")
                    denv = None
                if denv is not None:
                    if not was_open:
                        route._bump("cab_owner_open")
                    for sf in _iter_serialized(denv):
                        if (Path(str(getattr(sf, "name", ""))).name.lower() == target
                                and path_id in sf.objects):
                            self._cabs_owner.setdefault(target, owner)
                            return sf.objects[path_id], owner
                    route._bump("cab_owner_bad")
            # 表未命中 / owner 校验失败：退回依赖闭包扫描（不得静默错）
            deps = self.bundle_deps.get(cur_bundle, [])
            opens = 0
            depth = 0
            for i, dep in enumerate(deps, 1):
                try:
                    self.open_bundle(dep)
                except Exception:  # noqa: BLE001
                    continue
                opens += 1
                if target in self._cabs_owner:
                    depth = i
                    break
            route._bump("dep_scan_opens", opens)
            if not depth:
                depth = len(deps)
            if depth > route.STATS.get("dep_scan_depth", 0):
                route.STATS["dep_scan_depth"] = depth
            if target not in self._cabs_owner:
                self._cab_unreachable.add(target)
        owner_bundle = self._cabs_owner.get(target)
        if owner_bundle is None:
            raise PPtrError(
                "missing_cab",
                f"CAB {target} 不在 {cur_bundle} 的依赖包中（deps={len(self.bundle_deps.get(cur_bundle, []))}）",
            )
        denv = self.open_bundle(owner_bundle)
        for sf in _iter_serialized(denv):
            if Path(str(getattr(sf, "name", ""))).name.lower() == target:
                if path_id in sf.objects:
                    return sf.objects[path_id], owner_bundle
                # 目标 CAB 找到但 pathID 不在（可能同名 CAB 多包，继续扫）
        raise PPtrError("missing_pathid", f"{owner_bundle}/{target} 无 pathID {path_id}")

    def warm(self, bundles) -> dict:
        """批量预热（批2c 新接口）：逐个 open_bundle，已驻留跳过（不记 opens/cold）。
        返回 {"warmed": 新开数, "already": 已驻留数}。"""
        warmed = already = 0
        for bundle in bundles:
            if bundle in self._envs:
                already += 1
                continue
            self.open_bundle(bundle)
            warmed += 1
        return {"warmed": warmed, "already": already}


class Resolver:
    """manifest + bundle 的缓存式解析器（门面：定位半程 ManifestIndex + 打开半程
    BundleStore；对外 API 与拆分前一致，现有调用方零修改）。"""

    def __init__(self, game_win: str | Path | None = None):
        if game_win is None:                       # 契约 D：缺省=GameContext.data_win
            game_win = _default_win()
        self.win = Path(game_win)
        if not (self.win / "asset_manifest.unity3d").is_file():
            raise FileNotFoundError(f"{self.win} 下没有 asset_manifest.unity3d（--game 指向 Data/Win？）")
        self._index = ManifestIndex(self.win)
        self._store = BundleStore(self.win, index=self._index)

    # ---------- manifest 侧（转发 ManifestIndex 纯表） ----------

    @property
    def catalog(self) -> dict[str, str]:
        """base_assets_catalog：GUID → bundle 文件名。"""
        return self._index.catalog

    @property
    def catalog_duplicate_guids(self) -> set[str]:
        return self._index.catalog_duplicate_guids

    @property
    def bundle_deps(self) -> dict[str, list[str]]:
        """bundle_deps：bundle → 依赖 bundle 列表（allDependencies，含传递闭包）。"""
        return self._index.bundle_deps

    @property
    def platform_catalog(self) -> dict[str, tuple[str, str]]:
        """asset_catalog_platform_phone：baseGuid → (变体 guid, bundle)。"""
        return self._index.platform_catalog

    @property
    def cards_map(self) -> dict[str, str]:
        """cards_map：cardId → "名字.prefab:GUID"（CardDef 引用）。"""
        return self._index.cards_map

    def locale_catalog(self, locale: str) -> dict[str, tuple[str, str]]:
        """asset_manifest_{locale}.unity3d：baseGuid → (变体 guid, bundle)。"""
        return self._index.locale_catalog(locale)

    def card_def_ref(self, card_id: str) -> str | None:
        return self._index.card_def_ref(card_id)

    def card_working_set(self, card_ids, *, locale: str | None = None,
                         platform: str | None = None) -> dict:
        """卡集 → bundle 工作集（转发 ManifestIndex 纯表面；不开 bundle）。"""
        return self._index.card_working_set(card_ids, locale=locale,
                                            platform=platform)

    @property
    def _cabs_owner(self) -> dict[str, str]:
        """CAB 归属索引转发（tools/asset_graph 直读本名——拆分兼容面，批2c）。"""
        return self._store._cabs_owner

    def stats(self) -> dict:
        return {
            "catalog_entries": len(self._index.catalog),
            "catalog_duplicate_guids": len(self._index.catalog_duplicate_guids),
            "bundles_in_deps": len(self._index.bundle_deps),
            "platform_phone_overrides": len(self._index.platform_catalog),
            "cached_bundles_opened": len(self._store._envs),
        }

    # ---------- bundle 侧（转发 BundleStore） ----------

    def open_bundle(self, bundle: str):
        return self._store.open_bundle(bundle)

    def container_get(self, bundle: str, guid: str):
        return self._store.container_get(bundle, guid)

    def find_by_name(self, bundle: str, name: str) -> list[tuple[str, str]]:
        return self._store.find_by_name(bundle, name)

    def resolve_pptr(self, cur_bundle: str, ptr: dict, owner_obj=None):
        return self._store.resolve_pptr(cur_bundle, ptr, owner_obj=owner_obj)

    def warm(self, bundles) -> dict:
        """批量预热（见 BundleStore.warm）。"""
        return self._store.warm(bundles)

    # ---------- 定位半程（批2c 显式化：纯 manifest 表查询，全程不开任何 bundle） ----------

    def locate(self, asset_ref: str, locale: str | None = None,
               platform: str | None = None) -> dict:
        """定位半程："名字:GUID" 解析 + platform/locale 变体叠加 + catalog 查表 →
        {"ref", "guid", "resolved_guid", "bundle", "variant", ...}。
        全程不打开任何游戏 bundle；resolve() = locate() + 打开半程（行为不变）。"""
        asset_ref = asset_ref.strip()
        if ":" in asset_ref:
            ref_name, guid = asset_ref.rsplit(":", 1)
        else:
            ref_name, guid = "", asset_ref
        guid = guid.lower()
        loc: dict = {
            "ref": asset_ref,
            "ref_name": ref_name,
            "guid": guid,
            "locale": locale,
            "platform": platform,
            "base": {"guid": guid, "bundle": self._index.catalog.get(guid)},
            "variant": None,
            "resolved": {"guid": guid, "bundle": None},
            "resolved_guid": guid,
            "bundle": None,
        }

        # ---- 变体解析（platform → locale，后者覆盖前者；单层时与游戏一致） ----
        resolved_guid = guid
        if platform == "phone" and resolved_guid in self._index.platform_catalog:
            vguid, vbundle = self._index.platform_catalog[resolved_guid]
            loc["variant"] = {"layer": "platform_phone", "guid": vguid, "bundle": vbundle}
            resolved_guid = vguid
        if locale:
            lc = self._index.locale_catalog(locale)
            if resolved_guid in lc:
                vguid, vbundle = lc[resolved_guid]
                loc["variant"] = {"layer": f"locale_{locale.lower()}", "guid": vguid, "bundle": vbundle}
                resolved_guid = vguid

        resolved_bundle = self._index.catalog.get(resolved_guid) or (loc["variant"] or {}).get("bundle")
        loc["resolved"] = {"guid": resolved_guid, "bundle": resolved_bundle}
        loc["resolved_guid"] = resolved_guid
        loc["bundle"] = resolved_bundle
        return loc

    # ---------- 主解析 ----------

    def resolve(self, asset_ref: str, locale: str | None = None,
                platform: str | None = None, quality: str | None = None) -> dict:
        """"名字.ext:GUID" → 完整解析结果 + 一致性检查（见模块 docstring）。

        「无 bundle / 无 guid / bundle 文件缺失」→ ``GameAssetMissing``；成功路径
        返回结果 dict（checks 只在可达项上记账）。"""
        del quality  # 当前 manifest 无 quality catalog，保留参数
        loc = self.locate(asset_ref, locale=locale, platform=platform)
        result: dict = {
            "ref": loc["ref"],
            "ref_name": loc["ref_name"],
            "guid": loc["guid"],
            "locale": loc["locale"],
            "platform": loc["platform"],
            "base": loc["base"],
            "variant": loc["variant"],
            "resolved": loc["resolved"],
            "object": None,
            "checks": [],
            "ok": False,
        }
        ref_name = loc["ref_name"]
        resolved_guid = loc["resolved_guid"]
        resolved_bundle = loc["bundle"]
        if resolved_bundle is None:
            # 无 bundle（catalog 未登记任何变体）→ GameAssetMissing（§5.3 边界）。
            raise GameAssetMissing(
                path=resolved_guid,
                message=f"asset_missing_in_game: GUID {resolved_guid} 不在 base_assets_catalog"
                        "（也无 platform/locale 变体 bundle）")

        # ---- 打开 bundle 取对象 ----
        # container_get 无对象已直接抛 GameAssetMissing（同边界）；bundle 文件缺失
        # 在此显式转同型（message 带 catalog 来路）。对象读不出（坏块等）原样向上
        # ——typed BundleBlockCorruptError / 其他异常按 §7.8 映射，不在本层吞。
        try:
            obj, container_key = self.container_get(resolved_bundle, resolved_guid)
        except FileNotFoundError as exc:
            raise GameAssetMissing(
                path=str(self.win / resolved_bundle),
                message=f"asset_missing_in_game: catalog 指向的 bundle 不存在 {resolved_bundle}"
                ) from exc
        tree = obj.read_typetree()

        obj_info = {
            "name": tree.get("m_Name"),
            "type": obj.type.name,
            "path_id": obj.path_id,
            "bundle": resolved_bundle,
            "cab": Path(str(getattr(obj.assets_file, "name", ""))).name,
            "container_key": container_key,
        }
        if obj.type.name == "Texture2D":
            obj_info["width"] = tree.get("m_Width")
            obj_info["height"] = tree.get("m_Height")
            obj_info["texture_format"] = tree.get("m_TextureFormat")
        elif obj.type.name == "Material":
            texenvs = tree.get("m_SavedProperties", {}).get("m_TexEnvs", [])
            obj_info["tex_slots"] = [slot for slot, _ in texenvs]
            obj_info["shader_ptr"] = tree.get("m_Shader", {})
        elif obj.type.name == "GameObject":
            obj_info["component_count"] = len(tree.get("m_Component", []))
        result["object"] = obj_info

        # ---- 检查 ①：三源名称一致 ----
        ref_stem = Path(ref_name).stem if ref_name else None
        obj_name = obj_info["name"]
        subs = []
        if ref_stem is not None:
            subs.append((f"引用名 stem({ref_stem!r}) == 对象名({obj_name!r})", ref_stem == obj_name))
        if container_key is not None:
            subs.append((f"container 键({container_key[:12]}…) == 解析 GUID",
                         container_key.lower().endswith(resolved_guid)))
        result["checks"].append(_check("name-consistency", all(p for _, p in subs),
                                       "; ".join(n for n, p in subs if not p) or "三源一致"))

        # ---- 检查 ②：类型符合后缀预期 ----
        ext = ref_name.rsplit(".", 1)[-1].lower() if "." in ref_name else ""
        expected = EXT_EXPECTED_TYPES.get(ext)
        if expected is None:
            result["checks"].append(_check("type-vs-extension", None, f"后缀 .{ext} 无预期表，跳过"))
        else:
            result["checks"].append(_check(
                "type-vs-extension", obj_info["type"] in expected,
                f".{ext} 预期 {sorted(expected)}，实际 {obj_info['type']}"))

        # ---- 检查 ③：登记一致 ----
        reg_notes = [f"catalog→{resolved_bundle} == 对象所在 {obj_info['bundle']}"]
        reg_ok = self.catalog.get(resolved_guid) == resolved_bundle or (
            result["variant"] is not None and result["variant"]["bundle"] == resolved_bundle)
        if result["variant"] is not None:
            v = result["variant"]
            base_hit = self.catalog.get(v["guid"])
            reg_notes.append(f"变体 GUID {v['guid'][:12]}… 在 base catalog 交叉登记 → {base_hit or '未登记'}")
        result["checks"].append(_check("registration", reg_ok, "; ".join(reg_notes)))

        result["ok"] = all(c["pass"] in (True, None) for c in result["checks"])
        return result


def _check(name: str, passed, note: str) -> dict:
    return {"check": name, "pass": passed, "note": note}


# ---------- 模块级便捷入口（import 用；catalog 全局缓存一次） ----------

_default: Resolver | None = None


def get_resolver(game: str | Path | None = None) -> Resolver:
    """便捷入口（缺省 Data/Win=GameContext，契约 D；进程级单例按 win 判同）。"""
    global _default
    win = _default_win() if game is None else Path(game)
    if _default is None or Path(_default.win) != win:
        _default = Resolver(win)
    return _default


def resolve(asset_ref: str, locale: str | None = None, platform: str | None = None,
            quality: str | None = None, game: str | Path | None = None) -> dict:
    """便捷入口：resolve("Card_Hand_Ally.prefab:d00eb...", locale="zhcn")。"""
    return get_resolver(game).resolve(asset_ref, locale=locale, platform=platform, quality=quality)
