from functools import lru_cache
from importlib import import_module


def node_text(node, source):
    return source[node.start_byte : node.end_byte].decode("utf-8", "replace") if node else ""


def child_by_field_name(node, field):
    return node.child_by_field_name(field)


def node_has_error(node):
    return node.type == "ERROR" or node.has_error


def tree_has_error(node):
    return node_has_error(node)


@lru_cache(maxsize=2)
def parser(lang):
    from tree_sitter import Language, Parser

    try:
        module = import_module("tree_sitter_" + lang)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"Missing parser package 'tree_sitter_{lang}'. Install with `uv sync --extra java` or `pip install codectx[java]`."
        ) from exc
    return Parser(Language(module.language()))


def type_names(node, data):
    names = []
    stack = [node] if node else []
    while stack:
        item = stack.pop()
        if item.type in {"type_arguments", "marker_annotation", "annotation"}:
            continue
        if item.type in {"scoped_identifier", "scoped_type_identifier"}:
            parts = []
            components = [item]
            while components:
                c = components.pop()
                if c.type in {"identifier", "type_identifier"}:
                    parts.append(node_text(c, data))
                elif c.type not in {"type_arguments", "marker_annotation", "annotation"}:
                    components.extend(reversed(c.named_children))
            if parts:
                names.append(".".join(parts))
        elif item.type in {"identifier", "type_identifier"}:
            names.append(node_text(item, data))
        else:
            stack.extend(reversed(item.named_children))
    return list(dict.fromkeys(names))


def receiver_text(node, data):
    if node is None:
        return None
    return node_text(node, data) if node.end_byte - node.start_byte <= 160 else "<expression>"
