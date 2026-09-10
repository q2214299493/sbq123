"""Static scheduler-dispatch inventory for architecture regression tests.

Resolve command fragments through assignments and local command runners. This
is a conservative source guard, not a sandbox for arbitrary computed programs.
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict


MUTATION = re.compile(r"(?<![\w-])(?:bsub|bkill|sbatch|scancel|qsub|qdel)(?![\w-])")
SINKS = {"subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_call",
         "subprocess.check_output", "os.system", "os.popen"}


def qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return qualified_name(node.value) + "." + node.attr
    return ""


def import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                aliases[alias.asname or alias.name] = (
                    f"{node.module}.{alias.name}" if isinstance(node, ast.ImportFrom) else alias.name
                )
    return aliases


def command_bindings(tree: ast.AST):
    values = defaultdict(list)
    functions = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = node
            values[node.name].extend(item.value for item in ast.walk(node)
                                     if isinstance(item, ast.Return) and item.value is not None)
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and node.value is not None:
                    values[target.id].append(node.value)
        if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            values[node.target.id].append(node.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"append", "extend"}:
            values[qualified_name(node.func.value)].extend(node.args)
    return functions, values


def dispatch_sites(tree: ast.AST) -> list[int]:
    aliases = import_aliases(tree)
    functions, values = command_bindings(tree)

    def name(call):
        parts = qualified_name(call.func).split(".", 1)
        return ".".join([aliases.get(parts[0], parts[0]), *parts[1:]])

    runners = set(SINKS)
    for _ in range(len(functions) + 1):
        found = {key for key, function in functions.items() if any(
            isinstance(node, ast.Call) and name(node) in runners for node in ast.walk(function)
        )}
        if found <= runners:
            break
        runners.update(found)

    def fragments(node, seen=frozenset()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.Name):
            if node.id in seen:
                return []
            return [part for value in values[node.id] for part in fragments(value, seen | {node.id})]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            parts = fragments(node.left, seen) + fragments(node.right, seen)
            return [*parts, "".join(parts)]
        return [part for child in ast.iter_child_nodes(node) for part in fragments(child, seen)]

    return sorted({node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call)
                   and name(node) in runners
                   and any(MUTATION.search(part) for arg in [*node.args, *(kw.value for kw in node.keywords)]
                           for part in fragments(arg))})
