import re

from ..model import ExtractResult, RawRef, Symbol
from ._util import node_text, parser, receiver_text, type_names

TYPES = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration",
}
METHODS = {"method_declaration", "constructor_declaration", "compact_constructor_declaration"}


def _namespace(root, data):
    package, imports, wildcard = "", {}, False
    for node in root.named_children:
        if node.type not in {"package_declaration", "import_declaration"}:
            continue
        name = next(
            (
                node_text(c, data)
                for c in node.named_children
                if c.type in {"identifier", "scoped_identifier"}
            ),
            "",
        )
        if node.type == "package_declaration":
            package = name
        elif any(c.type == "asterisk" for c in node.named_children):
            wildcard = True
        elif name:
            imports[name.rsplit(".", 1)[-1]] = name
    return package, imports, wildcard


def _qualified(name, package, imports, wildcard):
    head, dot, tail = name.partition(".")
    if head in imports:
        return imports[head] + dot + tail
    if dot and head[:1].islower():
        return name
    if not wildcard:
        return f"{package}.{name}" if package else name
    return None


def _arguments(node):
    return (
        [
            child
            for child in node.named_children
            if child.type not in {"line_comment", "block_comment"}
        ]
        if node
        else []
    )


def _parameter_type(param, data, imports):
    typ = param.child_by_field_name("type")
    if typ is None and param.type == "spread_parameter":
        typ = next(
            (c for c in param.named_children if c.type not in {"modifiers", "variable_declarator"}),
            None,
        )
    raw = re.sub(r"\s+", "", node_text(typ, data))
    raw = re.sub(r"(?<![\w.])[A-Za-z_$][\w$]*", lambda m: imports.get(m[0], m[0]), raw)
    return raw + (
        "[]"
        if param.type == "spread_parameter"
        else node_text(param.child_by_field_name("dimensions"), data)
    )


def _bind_declaration(node, data, namespace, bindings, *, field=False):
    declared = node.child_by_field_name("type")
    for decl in node.children_by_field_name("declarator"):
        name = node_text(decl.child_by_field_name("name"), data)
        type_node = declared
        if node_text(declared, data) == "var":
            value = decl.child_by_field_name("value")
            type_node = (
                value.child_by_field_name("type")
                if value and value.type == "object_creation_expression"
                else None
            )
        names = type_names(type_node, data) if type_node and type_node.type != "array_type" else []
        bound = (
            (_qualified(names[0], *namespace) or names[0])
            if names and not decl.child_by_field_name("dimensions")
            else None
        )
        for key in (name, "this." + name) if field else (name,):
            if bound:
                bindings[key] = bound
            else:
                bindings.pop(key, None)


def _reflection(name, receiver, args, prefix, line, data):
    class_lookup = name == "forName" and receiver in {"Class", "java.lang.Class"}
    member_lookup = (
        name in {"getMethod", "getDeclaredMethod", "getField", "getDeclaredField"} and receiver
    )
    proxy = name == "newProxyInstance" and receiver in {"Proxy", "java.lang.reflect.Proxy"}
    if not (class_lookup or member_lookup or proxy):
        return None
    # Class.forName(Module, String) uses its second argument.
    arg = args[1] if class_lookup and len(args) == 2 else args[0] if args else None
    literal = node_text(arg, data)
    if not proxy and arg and arg.type == "string_literal" and re.fullmatch(r'"[\w.$]+"', literal):
        target = literal[1:-1].replace("$", ".") if class_lookup else literal[1:-1]
        return RawRef(
            prefix,
            target.rsplit(".", 1)[-1],
            "references",
            line,
            receiver=receiver,
            target_qualified=target if class_lookup else None,
            evidence="reflective",
            target_kind="class"
            if class_lookup
            else "variable"
            if name.endswith("Field")
            else "method",
        )
    return RawRef(prefix, name, "references", line, receiver=receiver, evidence="dynamic_dispatch")


def analyze(source, file_path):
    data = source.encode()
    tree = parser("java").parse(data)
    symbols, refs = [], []

    package, imports, wildcard = _namespace(tree.root_node, data)
    stack = [(tree.root_node, [], None, {})]
    while stack:
        node, scopes, source_byte, bindings = stack.pop()
        ref_start = len(refs)
        line = node.start_point.row + 1
        typ = node.type
        prefix = ".".join(scopes)
        if typ in TYPES | METHODS:
            name = (
                "<init>"
                if "constructor" in typ
                else node_text(node.child_by_field_name("name"), data)
            )
            qname = prefix + "." + name if prefix else name
            params, ret = node.child_by_field_name("parameters"), node.child_by_field_name("type")
            sig = node_text(params, data) if params else None
            if ret:
                sig = (sig or "") + " -> " + node_text(ret, data)
            doc = None
            prev = node.prev_named_sibling
            if prev and prev.type == "block_comment" and node_text(prev, data).startswith("/**"):
                doc = "\n".join(
                    re.sub(r"^\s*\* ?", "", line).strip()
                    for line in node_text(prev, data)[3:-2].splitlines()
                ).strip()
            parameters = [c for c in _arguments(params) if c.type != "receiver_parameter"]
            types = [_parameter_type(c, data, imports) for c in parameters]
            if typ in TYPES:
                bindings = {}
                body = node.child_by_field_name("body")
                for decl in body.named_children if body else ():
                    if decl.type == "field_declaration":
                        _bind_declaration(
                            decl, data, (package, imports, wildcard), bindings, field=True
                        )
            else:
                bindings = bindings.copy()
            for param, type_name in zip(parameters, types, strict=True):
                local = node_text(param.child_by_field_name("name"), data)
                bindings.pop(local, None)
                if local and re.fullmatch(r"[\w.]+", type_name):
                    bindings[local] = _qualified(type_name, package, imports, wildcard) or type_name
            modifiers = {
                c.type for m in node.named_children if m.type == "modifiers" for c in m.children
            }
            symbols.append(
                Symbol(
                    file_path,
                    name,
                    qname,
                    "class" if typ in TYPES else "method",
                    node.start_point.row + 1,
                    node.end_point.row + 1,
                    node.start_byte,
                    node.end_byte,
                    sig,
                    doc,
                    parse_ok=not node.has_error,
                    canonical_name=(f"{package}.{qname}" if package else qname)
                    if typ in TYPES
                    else None,
                    arity=len(parameters) if params else None,
                    override_signature=",".join(types)
                    if typ == "method_declaration" and not modifiers & {"private", "static"}
                    else None,
                    variadic=any(c.type == "spread_parameter" for c in parameters),
                )
            )
            source_byte = node.start_byte
            scopes = [*scopes, name]
            prefix = qname
            if typ in TYPES:
                for child in node.named_children:
                    if child.type in {"superclass", "super_interfaces", "extends_interfaces"}:
                        edge = (
                            "extends"
                            if child.type in {"superclass", "extends_interfaces"}
                            else "implements"
                        )
                        for target in type_names(child, data):
                            refs.append(
                                RawRef(
                                    qname,
                                    target.rsplit(".", 1)[-1],
                                    edge,
                                    line,
                                    target_qualified=_qualified(target, package, imports, wildcard),
                                )
                            )
        elif typ in {"field_declaration", "constant_declaration", "enum_constant"}:
            declarations = (
                [node]
                if typ == "enum_constant"
                else [c for c in node.named_children if c.type == "variable_declarator"]
            )
            for decl in declarations:
                name = node_text(decl.child_by_field_name("name"), data)
                if name:
                    symbols.append(
                        Symbol(
                            file_path,
                            name,
                            prefix + "." + name if prefix else name,
                            "variable",
                            node.start_point.row + 1,
                            node.end_point.row + 1,
                            node.start_byte,
                            node.end_byte,
                            parse_ok=not node.has_error,
                        )
                    )
        if typ in {
            "block",
            "for_statement",
            "enhanced_for_statement",
            "catch_clause",
            "lambda_expression",
        }:
            bindings = bindings.copy()
        if typ == "local_variable_declaration":
            _bind_declaration(node, data, (package, imports, wildcard), bindings)
        if typ == "object_creation_expression":
            names = type_names(node.child_by_field_name("type"), data)
            body = next((c for c in node.named_children if c.type == "class_body"), None)
            if names:
                base = names[0]
                qualified = _qualified(base, package, imports, wildcard)
                refs.append(
                    RawRef(
                        prefix or "<module>",
                        base.rsplit(".", 1)[-1],
                        "references",
                        line,
                        source_start_byte=source_byte,
                        target_qualified=qualified,
                        target_kind="class",
                        evidence="construction",
                    )
                )
                if body:
                    name = f"<anonymous@{line}:{node.start_point.column + 1}>"
                    qname = f"{prefix}.{name}" if prefix else name
                    symbols.append(
                        Symbol(
                            file_path,
                            name,
                            qname,
                            "class",
                            line,
                            body.end_point.row + 1,
                            node.start_byte,
                            body.end_byte,
                        )
                    )
                    refs.append(
                        RawRef(
                            qname,
                            base.rsplit(".", 1)[-1],
                            "anonymous_base",
                            line,
                            source_start_byte=node.start_byte,
                            target_qualified=qualified,
                        )
                    )
                    for child in reversed(node.named_children):
                        stack.append(
                            (child, [*scopes, name], node.start_byte, {})
                            if child == body
                            else (child, scopes, source_byte, bindings)
                        )
                    continue
        if typ == "method_invocation":
            name = node_text(node.child_by_field_name("name"), data)
            if name:
                receiver = receiver_text(node.child_by_field_name("object"), data)
                args = _arguments(node.child_by_field_name("arguments"))
                refs.append(
                    RawRef(
                        prefix or "<module>",
                        name,
                        "calls",
                        line,
                        receiver=receiver,
                        receiver_type=bindings.get(receiver),
                        arity=len(args),
                    )
                )
                site = _reflection(name, receiver, args, prefix or "<module>", line, data)
                if site:
                    refs.append(site)
        elif typ in {"annotation", "marker_annotation"}:
            name = node_text(node.child_by_field_name("name"), data)
            refs.append(
                RawRef(
                    prefix or "<module>",
                    name.rsplit(".", 1)[-1],
                    "references",
                    line,
                    target_qualified=_qualified(name, package, imports, wildcard),
                    target_kind="class",
                    evidence="annotation",
                )
            )
        elif typ == "method_reference":
            parts = _arguments(node)
            if len(parts) >= 2 and parts[-1].type == "identifier":
                refs.append(
                    RawRef(
                        prefix or "<module>",
                        node_text(parts[-1], data),
                        "references",
                        line,
                        receiver=receiver_text(parts[0], data),
                        evidence="method_reference",
                        target_kind="method",
                    )
                )
        elif typ == "import_declaration":
            for c in node.named_children:
                if c.type in {"scoped_identifier", "identifier"}:
                    refs.append(
                        RawRef(
                            prefix or "<module>",
                            node_text(c, data).rsplit(".", 1)[-1],
                            "imports",
                            line,
                            target_qualified=node_text(c, data),
                        )
                    )
                    break
        for ref in refs[ref_start:]:
            ref.source_start_byte = source_byte
        stack.extend(
            (child, scopes, source_byte, bindings) for child in reversed(node.named_children)
        )
    return ExtractResult(
        symbols,
        not tree.root_node.has_error,
        "syntax error in source" if tree.root_node.has_error else None,
    ), refs


def extract(source, file_path):
    return analyze(source, file_path)[0]


def extract_refs(source, file_path):
    return analyze(source, file_path)[1]
