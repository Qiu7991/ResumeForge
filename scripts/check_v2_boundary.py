# SPDX-License-Identifier: Apache-2.0
"""v2 边界静态守卫（Phase 4）：让"下一个人写回旧路径"在检查阶段就失败。

四类检查（**全部 AST，不用正则**——backend/app 里 `.content` 有 200+ 处，绝大多数是
`response.content` / `message.content` 之类，正则必然误伤）：

1. v1 形状消费：禁止对 ``record.content`` / ``resume.content`` / ``row.content`` /
   ``current.content`` 做下标、``.get()`` 或属性访问取 v1 字段名。
2. ``*.content`` 使用形态：每一处出现必须是 (a) 边界函数家族的实参、
   (b) 白名单文件内（每条白名单写明理由）、(c) 赋给变量后传给边界函数（一层间接）。
3. 旧版式键写入：禁止以**任何**形式把 ``hidden_sections`` / ``section_order``
   写进 dict（下标赋值 / update / setdefault / 字面量键）。
   ``validated_format_config`` 在白名单内（它只解析外部输入，落库前由
   ``persistable_format_config`` 剥离——对抗审查 L2 已核实三个落库点全部先剥离）。
4. 迁移完整性：文件名 4 位数字前缀唯一；``down_revision`` 引用必须存在；
   heads 唯一（自己解依赖图，不依赖 alembic 包）。

用法：``backend/.venv/Scripts/python.exe -I scripts/check_v2_boundary.py``
全绿 exit 0，任何失败 exit 1。只读，不写库、不改文件。
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
APP = BACKEND / "app"
VERSIONS = BACKEND / "migrations" / "versions"

#: 检查 1/2 只盯这四个属主名（方案 §1.2 的口径：其余 .content 是别的对象，不归本守卫管）。
CONTENT_OWNERS = {"record", "resume", "row", "current"}

#: v1 的形状字段清单（方案 Phase 4 检查 1）。出现即＝按 v1 形状取键。
V1_FIELDS = {
    "projects",
    "experience",
    "educations",
    "internships",
    "awards",
    "campus_experience",
    "custom_sections",
    "job_intent",
    "tech_stack",
    "hidden_points",
}

#: 旧版式键（Phase 4 检查 3）。
LEGACY_LAYOUT_KEYS = {"hidden_sections", "section_order"}

#: 边界函数家族。前七个是方案 Phase 4 点名的（含 with_report 变体）；后两个是**实测确认**
#: 的包装：``_shared.document_or_422`` 首行就转手 ensure_document_version；
#: ``document_versions.document_content`` 是历史快照路径的归一化入口。
#: 新增成员必须先核对：它内部必须立即把 content 交给边界，不得自行取键。
BOUNDARY_FUNCS = {
    "document_for_record",
    "ensure_document_version",
    "ensure_document_version_with_report",
    "coerce_document",
    "paper_document",
    "prepare_document_for_save",
    "prepare_document_for_save_with_report",
    "document_or_422",
    "document_content",
}

#: 检查 2 的文件白名单（按文件名）。**每条都必须写理由**，新增例外同此要求。
#: 口径：该文件对 ``*.content`` 的使用是"整份透传 / 哈希比较 / 快照冻结 / 对象根本
#: 不是简历记录"之一，没有任何 v1 形状取键（取键由检查 1 无例外地拦）。
FILE_WHITELIST: dict[str, str] = {
    # —— 方案 Phase 4 点名的三个（哈希/比较）——
    "document_save.py": "哈希/比较：canonical_content_sha256 对比、prune 旧正文（条件写）",
    "resume_delivery.py": "冻结快照：整份 content 复制进投递证据（frozen_content）",
    "resume_sync.py": "哈希/同步快照（方案点名的白名单文件；本守卫不修改它）",
    # —— 实测确认的哈希/快照用途 ——
    "review_annotations.py": "快照哈希：canonical_content_sha256(record.content)",
    "fact_locks.py": "旧正文比对/事实锁基线（base_content 与写入内容比较）",
    "document_versions.py": "历史快照路径：document_content/_snapshot_content 消费整份 content 存版本行",
    "document_variants.py": "变体路径：document_content 消费整份 content",
    # —— 整份 v2 dict 透传（无取键；取键由检查 1 拦）——
    "generate_routes.py": "SSE done.resume 透传落库后的 v2（Phase 2 收口的指定行为）",
    "apply.py": "招呼语上下文：整份 v2 dict json.dumps 透传",
    "job_match_context.py": "招呼语上下文：整份 v2 dict 透传",
    "resume_templates.py": "模板缩略图：整份 content 透传给渲染",
    "assistant_context.py": "AI 助手上下文：dict 副本去 photo 后整体交给模型",
    "job_tools.py": "AI 助手工具：dict 副本透传",
    "document_support.py": "AI 助手工具：deepcopy 整份 content 进 ResumeVersion 快照",
    # —— 对象不是简历记录（row.content 是消息/经历文本）——
    "assistant_conversations.py": "row 是会话消息（role/content 文本）",
    "assistant_persistence.py": "row 是会话消息",
    "chat_history.py": "row 是会话消息",
    "interview_experiences.py": "row 是面试经历文本行",
    "document_provenance_source_text.py": "record 不是简历记录（来源文本行，content 是字符串）",
}

#: 检查 3 的函数白名单：这些函数体内允许出现旧版式键的写入形式。每条写明理由：
#:
#: - ``validated_format_config``：**解析外部输入**的出口（旧导入/旧备份仍要能解析，
#:   且被 test_resume_hidden_sections 钉住输出保留该键）；落库前所有调用点都先过
#:   ``persistable_format_config`` 剥离（对抗审查 L2 已逐点核实：resume_record.py:190、
#:   manual_creation.py:102、layout_render_routes.py:105）。
#: - ``validated_style_config``：同一家族的样式模板外部输入解析（normalize 后交渲染，
#:   不直接落库）。
#: - ``default_section_order_config``：P0-5 的转换输入物化——把「我的资料」顺序构造成
#:   生成/创建请求的 format_config，v1→v2 转换消费它排 sections，落库前被
#:   persistable_format_config 剥离（save_record / manual_creation 均如此）。
#: - ``scenario_section_order``：场景顺序 → 生成请求转换输入，同上（消费后剥离）。
FUNCTION_WHITELIST = {
    "validated_format_config",
    "validated_style_config",
    "default_section_order_config",
    "scenario_section_order",
}

#: 检查 3 的文件白名单：这些文件里的旧版式键**字面量**不是对简历 format_config 的写入。
FILE_WHITELIST_CHECK3: dict[str, str] = {
    # 能力矩阵/说明表：键名是"被描述的字段名"（检查面板据此渲染说明），不是写配置值。
    "format_capabilities.py": "能力说明表：字面量键是被描述的字段名，非 format_config 写入",
    # 职业场景快照的 layout 描述：section_order 是**资料侧**（ConsumedProfile）的顺序，
    # 存进场景快照 JSON，不是简历 format_config。
    "generate_snapshot.py": "场景快照：section_order 是资料侧顺序，非简历版式键写入",
    "paper_projection.py": "快照指纹 payload：section_order 是资料侧顺序，非简历版式键写入",
    # 资料页解析结果/旧协议输出的字段名（ProfileTextParseResult / ProfileOut），
    # 资料侧 section_order 与简历 format_config 无关。
    "text_extraction_normalization.py": "资料侧解析结果的字段名，非简历版式键写入",
    "profile_service.py": "旧协议 ProfileOut 的资料侧 section_order 字段，非简历版式键写入",
    # 旧 user_profile 表的 DDL 兼容规格：section_order 是**列名**（默认值 SQL 字符串）。
    "database_compat.py": "DDL 兼容规格：section_order 是 user_profile 表的列名",
}

CHECK_NAMES = ("v1形状消费", "*.content 使用形态", "旧版式键写入", "迁移完整性")
_FAILS: dict[str, list[str]] = {name: [] for name in CHECK_NAMES}


def fail(check: str, path: Path | None, lineno: int, reason: str) -> None:
    where = "—" if path is None else f"{path.as_posix().split('backend/', 1)[-1]}:{lineno}"
    _FAILS[check].append(f"FAIL {check} — {where} — {reason}")


def _is_content_node(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "content"
        and isinstance(node.value, ast.Name)
        and node.value.id in CONTENT_OWNERS
    )


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _strip_wrapper(value: ast.AST) -> ast.AST | None:
    """``record.content or {}`` 这类直角包装：如果恰好包着一个 .content 节点就返回它。"""
    if isinstance(value, (ast.BoolOp, ast.BinOp)):
        parts = list(value.values) if isinstance(value, ast.BoolOp) else [value.left, value.right]
        content_parts = [p for p in parts if _is_content_node(p)]
        if len(content_parts) == 1:
            return content_parts[0]
    return None


class _LegacyKeyVisitor(ast.NodeVisitor):
    """检查 3：旧版式键的任何写入形式（函数白名单内放行）。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._func_stack: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _flag(self, node: ast.AST, reason: str) -> None:
        if self._func_stack and self._func_stack[-1] in FUNCTION_WHITELIST:
            return
        if self.path.name in FILE_WHITELIST_CHECK3:
            return
        fail("旧版式键写入", self.path, getattr(node, "lineno", 0), reason)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.slice, ast.Constant)
                and target.slice.value in LEGACY_LAYOUT_KEYS
            ):
                self._flag(node, "下标赋值写旧版式键")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        if name in {"update", "setdefault"} and node.args:
            first = node.args[0]
            if isinstance(first, ast.Dict):
                self._check_dict(first)
            elif isinstance(first, ast.Constant) and first.value in LEGACY_LAYOUT_KEYS:
                self._flag(node, f"{name}() 写旧版式键")
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        self._check_dict(node)
        self.generic_visit(node)

    def _check_dict(self, node: ast.Dict) -> None:
        for key in node.keys:
            if isinstance(key, ast.Constant) and key.value in LEGACY_LAYOUT_KEYS:
                self._flag(node, "字典字面量写旧版式键")


def _scan_app() -> int:
    files = sorted(APP.rglob("*.py"))
    checked = 0
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            fail("v1形状消费", path, getattr(exc, "lineno", 0) or 0, f"无法解析：{exc}")
            continue
        checked += 1

        boundary_arg_ids: set[int] = set()
        alias_names_in_boundary: set[str] = set()
        content_nodes: list[ast.Attribute] = []

        for node in ast.walk(tree):
            # 边界调用实参集合（含别名实参）
            if isinstance(node, ast.Call) and _call_name(node.func) in BOUNDARY_FUNCS:
                for arg in (*node.args, *(kw.value for kw in node.keywords)):
                    for sub in ast.walk(arg):
                        boundary_arg_ids.add(id(sub))
                        if isinstance(sub, ast.Name):
                            alias_names_in_boundary.add(sub.id)
            # 检查 1 之一：record.content.get("projects")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and _is_content_node(node.func.value)
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in V1_FIELDS
            ):
                fail("v1形状消费", path, node.lineno, f".get() 取 v1 字段 {node.args[0].value!r}")
            # 检查 1 之二：record.content["projects"]
            if (
                isinstance(node, ast.Subscript)
                and _is_content_node(node.value)
                and isinstance(node.slice, ast.Constant)
                and node.slice.value in V1_FIELDS
            ):
                fail("v1形状消费", path, node.lineno, f"下标取 v1 字段 {node.slice.value!r}")
            # 检查 1 之三：record.content.projects（属性访问）
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Attribute)
                and _is_content_node(node.value)
                and node.attr in V1_FIELDS
            ):
                fail("v1形状消费", path, node.lineno, f"按 v1 形状取键 .{node.attr}")
            # 收集 .content 出现点
            if _is_content_node(node):
                content_nodes.append(node)

        # 检查 2：.content 使用形态
        alias_defs: dict[str, ast.Attribute] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target, value = node.targets[0], node.value
                base = value if _is_content_node(value) else _strip_wrapper(value)
                if isinstance(target, ast.Name) and base is not None:
                    alias_defs[target.id] = base
        for node in content_nodes:
            if id(node) in boundary_arg_ids:
                continue  # (a) 边界函数实参
            owning_alias = next((n for n, attr in alias_defs.items() if attr is node), None)
            if owning_alias is not None and owning_alias in alias_names_in_boundary:
                continue  # (c) 一层间接：别名最终进了边界函数
            if path.name in FILE_WHITELIST:
                continue  # (b) 白名单文件（理由见 FILE_WHITELIST）
            fail(
                "*.content 使用形态",
                path,
                node.lineno,
                "不是边界函数实参也不在白名单；如属透传/比较用途，请把文件加进 FILE_WHITELIST 并写理由",
            )

        # 检查 3
        _LegacyKeyVisitor(path).visit(tree)
    return checked


def _scan_migrations() -> None:
    files = sorted(VERSIONS.glob("*.py")) if VERSIONS.is_dir() else []
    prefixes: dict[str, list[str]] = {}
    revisions: dict[str, tuple[str, ...]] = {}
    for path in files:
        match = re.match(r"^(\d{4})_", path.name)
        if match:
            prefixes.setdefault(match.group(1), []).append(path.name)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rev: str | None = None
        downs: tuple[str, ...] = ()
        for node in tree.body:
            name = ""
            value: ast.AST | None = None
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name, value = node.target.id, node.value
            elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                name = target.id if isinstance(target, ast.Name) else ""
                value = node.value
            if name == "revision" and isinstance(value, ast.Constant):
                rev = str(value.value)
            elif name == "down_revision" and value is not None:
                if isinstance(value, ast.Constant):
                    downs = () if value.value is None else (str(value.value),)
                elif isinstance(value, (ast.Tuple, ast.List)):
                    downs = tuple(
                        str(el.value) for el in value.elts if isinstance(el, ast.Constant)
                    )
        if rev:
            revisions[rev] = downs

    for prefix, names in sorted(prefixes.items()):
        if len(names) > 1:
            fail("迁移完整性", VERSIONS, 0, f"文件名前缀 {prefix} 重复：{names}")
    for rev, downs in sorted(revisions.items()):
        for down in downs:
            if down not in revisions:
                fail("迁移完整性", VERSIONS, 0, f"revision {rev} 的 down_revision {down!r} 不存在")
    parents = {parent for downs in revisions.values() for parent in downs}
    heads = sorted(rev for rev in revisions if rev not in parents)
    if len(heads) != 1:
        fail("迁移完整性", VERSIONS, 0, f"heads 应为 1 个，实际 {len(heads)}：{heads}")


def main() -> int:
    checked = _scan_app()
    _scan_migrations()

    print(f"PASS v1形状消费 — {checked} 个文件" if not _FAILS["v1形状消费"] else "")
    print(f"PASS *.content 使用形态 — {checked} 个文件" if not _FAILS["*.content 使用形态"] else "")
    print(f"PASS 旧版式键写入 — {checked} 个文件" if not _FAILS["旧版式键写入"] else "")
    migration_count = len(list(VERSIONS.glob("*.py"))) if VERSIONS.is_dir() else 0
    print(f"PASS 迁移完整性 — {migration_count} 个文件" if not _FAILS["迁移完整性"] else "")

    failed_checks = 0
    for name in CHECK_NAMES:
        for line in _FAILS[name]:
            print(line)
        if _FAILS[name]:
            failed_checks += 1
    print(f"汇总：{4 - failed_checks} 通过 / {failed_checks} 失败")
    return 1 if failed_checks else 0


if __name__ == "__main__":
    raise SystemExit(main())
