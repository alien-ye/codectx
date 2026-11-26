import ast
import contextlib
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from ..model import ExtractResult, RawRef, Symbol
from ._util import node_text, parser, receiver_text


def _dotted(node, data):
    parts = []
    while node and node.type == "attribute":
        parts.append(node_text(node.child_by_field_name("attribute"), data))
        node = node.child_by_field_name("object")
    if node and node.type == "identifier":
        parts.append(node_text(node, data))
        return ".".join(reversed(parts))
    return ""


def _bound(name, bindings):
    head, dot, tail = name.partition(".")
    bound = bindings.get(head)
    return bound + dot + tail if bound else None


_CONTAINERS = {"dict", "list", "set", "frozenset", "tuple"}
_BUILTIN_CONTAINERS = {"builtins." + name for name in _CONTAINERS}
_LITERAL_TYPES = {
    "dictionary": "dict",
    "dictionary_comprehension": "dict",
    "list": "list",
    "list_comprehension": "list",
    "set": "set",
    "set_comprehension": "set",
    "tuple": "tuple",
}


def _type_name(name, bindings):
    if name in _CONTAINERS and name not in bindings:
        return "builtins." + name
    return _bound(name, bindings) or name or None


def _annotation_type(annotation, data, bindings):
    if not annotation or not annotation.named_children:
        return None
    node = annotation.named_children[0]
    if node.type in {"generic_type", "subscript"}:
        name = _type_name(_dotted(node.named_children[0], data), bindings)
        return name if name in _BUILTIN_CONTAINERS else None
    if node.type == "string":
        with contextlib.suppress(ValueError, SyntaxError):
            name = ast.literal_eval(node_text(node, data))
            if isinstance(name, str) and all(part.isidentifier() for part in name.split(".")):
                return _type_name(name, bindings)
    return _type_name(_dotted(node, data), bindings)


def _value_type(node, data, bindings, receivers):
    while node and node.type == "parenthesized_expression" and node.named_child_count == 1:
        node = node.named_children[0]
    if node is None:
        return None
    if node.type in _LITERAL_TYPES:
        return "builtins." + _LITERAL_TYPES[node.type]
    if node.type == "call":
        name = _type_name(_dotted(node.child_by_field_name("function"), data), bindings)
        if name and (name in _BUILTIN_CONTAINERS or name.rsplit(".", 1)[-1][:1].isupper()):
            return name
        return None
    return receivers.get(_dotted(node, data))


@dataclass(slots=True)
class _Fields:
    """Collect instance field uses until all declarations in this class have been visited."""

    declared: dict[str, str | None] = field(default_factory=dict)
    initialized: dict[str, str | None] = field(default_factory=dict)
    uses: list[tuple[RawRef, str, bool]] = field(default_factory=list)

    def resolve(self):
        for ref, attr, in_init in self.uses:
            ref.receiver_type = self.declared.get(attr)
            if not in_init and attr not in self.declared:
                ref.receiver_type = self.initialized.get(attr)


@dataclass(slots=True)
class _Scope:
    qname: str = ""
    kind: str = "module"
    fields: _Fields | None = None
    instance: str | None = None

    def attribute(self, name):
        if self.instance and name:
            root, dot, attr = name.partition(".")
            if root == self.instance and dot and attr.isidentifier():
                return attr
        return None


def _instance_parameter(node, data, bindings):
    if node.parent and node.parent.type == "decorated_definition":
        for decorator in node.parent.named_children:
            if decorator.type == "decorator" and decorator.named_children:
                name = _dotted(decorator.named_children[0], data)
                if (_bound(name, bindings) or name) in {
                    "staticmethod",
                    "classmethod",
                    "builtins.staticmethod",
                    "builtins.classmethod",
                }:
                    return None
    params = node.child_by_field_name("parameters")
    if params and params.named_children:
        first = params.named_children[0]
        ident = first.child_by_field_name("name") or (
            first.named_children[0] if first.named_children else first
        )
        if ident.type == "identifier" and first.type in {
            "identifier",
            "typed_parameter",
            "default_parameter",
            "typed_default_parameter",
        }:
            return node_text(ident, data)
    return None


def _imports(node, data, package, bindings, owner):
    module = node_text(node.child_by_field_name("module_name"), data)
    if module.startswith("."):
        tail = module.lstrip(".")
        levels = len(module) - len(tail)
        base = package.split(".")
        if package and levels <= len(base):
            module = ".".join(filter(None, [*base[: len(base) - levels + 1], tail]))
    names = node.children_by_field_name("name")
    for child in names:
        target_node = child.child_by_field_name("name") if child.type == "aliased_import" else child
        name = node_text(target_node, data)
        alias = node_text(child.child_by_field_name("alias"), data)
        if node.type == "import_from_statement":
            full = module.rstrip(".") + "." + name if module.strip(".") else module + name
            local = alias or name
            target = name
        else:
            full, local, target = name, alias or name.split(".")[0], name
        bindings[local] = full if alias or node.type == "import_from_statement" else local
        yield RawRef(
            owner, target, "imports", node.start_point.row + 1, alias=local, target_qualified=full
        )
    if any(c.type == "wildcard_import" for c in node.named_children):
        yield RawRef(owner, module, "imports", node.start_point.row + 1, target_qualified=module)


def _reflective_call(function, args, bindings, owner, line, data):
    dotted = _dotted(function, data)
    api = _bound(dotted, bindings) or dotted
    if api in {"getattr", "hasattr", "setattr"}:
        index, kind = 1, "references"
    elif api in {"importlib.import_module", "__import__"}:
        index, kind = 0, "imports"
    else:
        return None
    if len(args) <= index:
        return None
    receiver = receiver_text(args[0], data) if index else None
    argument = args[index]
    if argument.type in {"string", "concatenated_string"}:
        with contextlib.suppress(ValueError, SyntaxError):
            value = ast.literal_eval(node_text(argument, data))
            if isinstance(value, str):
                return RawRef(
                    owner,
                    value,
                    kind,
                    line,
                    receiver=receiver,
                    evidence="reflective",
                    target_qualified=value if kind == "imports" else None,
                )
    return RawRef(owner, api, kind, line, receiver=receiver, evidence="dynamic_dispatch")


def analyze(source, file_path):
    data = source.encode()
    tree = parser("python").parse(data)
    symbols, refs = [], []

    path = PurePosixPath(file_path).with_suffix("")
    package = ".".join(path.parent.parts)
    module = package if path.name == "__init__" else ".".join(path.parts)
    classes = []
    stack = [(tree.root_node, _Scope(), {}, {})]
    while stack:
        node, scope, bindings, receiver_types = stack.pop()
        line = node.start_point.row + 1
        typ = node.type
        prefix = scope.qname
        if typ == "decorated_definition":
            definition = node.child_by_field_name("definition")
            if definition:
                name = node_text(definition.child_by_field_name("name"), data)
                decorated = _Scope(f"{prefix}.{name}" if prefix else name, "decorated")
                for child in reversed(node.named_children):
                    stack.append(
                        (
                            child,
                            decorated if child.type == "decorator" else scope,
                            bindings,
                            receiver_types,
                        )
                    )
                continue
        if typ == "decorator" and node.named_children:
            expr = node.named_children[0]
            callee = expr.child_by_field_name("function") if expr.type == "call" else expr
            dotted = _dotted(callee, data)
            if dotted:
                target = _bound(dotted, bindings)
                refs.append(
                    RawRef(
                        prefix,
                        (target or dotted).rsplit(".", 1)[-1],
                        "references",
                        line,
                        target_qualified=target,
                        evidence="decorator",
                    )
                )
                if expr.type == "call":
                    arguments = expr.child_by_field_name("arguments")
                    if arguments:
                        stack.extend(
                            (c, scope, bindings, receiver_types)
                            for c in reversed(arguments.named_children)
                        )
                continue
        if typ in {"function_definition", "class_definition"}:
            name = node_text(node.child_by_field_name("name"), data)
            kind = (
                "class"
                if typ == "class_definition"
                else "method"
                if scope.kind == "class"
                else "function"
            )
            qname = prefix + "." + name if prefix else name
            params = node.child_by_field_name("parameters")
            ret = node.child_by_field_name("return_type")
            sig = node_text(params, data) if params else None
            if ret:
                sig = (sig or "") + " -> " + node_text(ret, data)
            doc = None
            body = node.child_by_field_name("body")
            if body and body.named_children:
                first = body.named_children[0]
                if (
                    first.type == "expression_statement"
                    and first.named_children
                    and first.named_children[0].type == "string"
                ):
                    with contextlib.suppress(ValueError, SyntaxError):
                        doc = ast.literal_eval(node_text(first.named_children[0], data))
            symbols.append(
                Symbol(
                    file_path,
                    name,
                    qname,
                    kind,
                    node.start_point.row + 1,
                    node.end_point.row + 1,
                    node.start_byte,
                    node.end_byte,
                    sig,
                    doc,
                    canonical_name=f"{module}.{qname}",
                    parse_ok=not node.has_error,
                )
            )
            if kind == "class":
                facts = _Fields()
                classes.append(facts)
                scope = _Scope(qname, kind, facts)
            elif kind == "method":
                scope = _Scope(qname, kind, scope.fields, _instance_parameter(node, data, bindings))
            else:
                scope = _Scope(qname, kind)
            prefix = qname
            if typ == "class_definition":
                bases = node.child_by_field_name("superclasses")
                if bases:
                    for base in bases.named_children:
                        metaclass = base.type == "keyword_argument"
                        if (
                            metaclass
                            and node_text(base.child_by_field_name("name"), data) != "metaclass"
                        ):
                            continue
                        expr = base.child_by_field_name("value") if metaclass else base
                        if expr and expr.type == "subscript":
                            expr = expr.child_by_field_name("value")
                        dotted = _dotted(expr, data)
                        if dotted:
                            target = _bound(dotted, bindings) or (dotted if "." in dotted else None)
                            refs.append(
                                RawRef(
                                    qname,
                                    (target or dotted).rsplit(".", 1)[-1],
                                    "references" if metaclass else "extends",
                                    line,
                                    target_qualified=target,
                                    target_kind="class",
                                    evidence="metaclass" if metaclass else None,
                                )
                            )
            bindings[name] = None
            bindings = bindings.copy()
            receiver_types = {}
            if params:
                for param in params.named_children:
                    ident = param.child_by_field_name("name") or (
                        param.named_children[0] if param.named_children else param
                    )
                    local = node_text(ident, data)
                    annotation = param.child_by_field_name("type")
                    receiver_types[local] = _annotation_type(annotation, data, bindings)
                    bindings[local] = None
        elif typ == "assignment" and scope.kind in {"module", "class"}:
            left = node.child_by_field_name("left")
            if left and left.type == "identifier":
                name = node_text(left, data)
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
        if typ == "assignment":
            left = node.child_by_field_name("left")
            local = _dotted(left, data)
            if local:
                block = node.parent.parent if node.parent else None
                direct = block is not None and (
                    block.type == "module"
                    or (
                        block.type == "block"
                        and block.parent.type in {"function_definition", "class_definition"}
                    )
                )
                annotation = node.child_by_field_name("type")
                inferred = None
                if direct:
                    inferred = (
                        _annotation_type(annotation, data, bindings)
                        if annotation
                        else _value_type(
                            node.child_by_field_name("right"), data, bindings, receiver_types
                        )
                    )
                if scope.kind == "class" and local.isidentifier() and annotation and direct:
                    scope.fields.declared[local] = inferred
                attr = scope.attribute(local)
                if attr and prefix.endswith(".__init__"):
                    if annotation and direct:
                        scope.fields.declared[attr] = inferred
                    else:
                        scope.fields.initialized[attr] = inferred
                if local == scope.instance:
                    scope.instance = None
                receiver_types[local] = inferred
                bindings[local] = None
        if typ == "call":
            fn = node.child_by_field_name("function")
            args = node.child_by_field_name("arguments")
            target = ""
            if fn and fn.type == "attribute":
                target = node_text(fn.child_by_field_name("attribute"), data)
            elif fn and fn.type == "identifier":
                target = node_text(fn, data)
            if target:
                obj = fn.child_by_field_name("object")
                receiver = receiver_text(obj, data)
                bound = _bound(_dotted(fn, data), bindings)
                ref = RawRef(
                    prefix or "<module>",
                    (bound or target).rsplit(".", 1)[-1],
                    "calls",
                    line,
                    receiver=receiver,
                    receiver_type=_value_type(obj, data, bindings, receiver_types),
                    target_qualified=bound,
                )
                refs.append(ref)
                name = _dotted(obj, data)
                attr = scope.attribute(name)
                if attr and name not in receiver_types:
                    scope.fields.uses.append((ref, attr, prefix.endswith(".__init__")))
                site = _reflective_call(
                    fn,
                    [c for c in args.named_children if c.type != "comment"] if args else [],
                    bindings,
                    prefix or "<module>",
                    line,
                    data,
                )
                if site:
                    refs.append(site)
        elif typ in {"import_statement", "import_from_statement"}:
            refs.extend(_imports(node, data, package, bindings, prefix or "<module>"))
        stack.extend(
            (child, scope, bindings, receiver_types) for child in reversed(node.named_children)
        )
    for facts in classes:
        facts.resolve()
    return ExtractResult(
        symbols,
        not tree.root_node.has_error,
        "syntax error in source" if tree.root_node.has_error else None,
    ), refs


def extract(source, file_path):
    return analyze(source, file_path)[0]


def extract_refs(source, file_path):
    return analyze(source, file_path)[1]
