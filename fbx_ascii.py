"""ASCII FBX -> binary FBX converter (Blender imports only binary FBX)."""
import struct


# ------------------------------------------------------------ ASCII FBX -> binary FBX
_D_ARR = {"Vertices", "Normals", "Binormals", "Tangents", "UV", "Weights", "Transform", "TransformLink",
          "Matrix", "Colors", "Points", "Knots"}
_P_INT = {"int", "Integer", "enum", "Enum", "bool", "Bool", "Short", "UShort", "Visibility Inheritance"}
_P_LONG = {"KTime", "Time", "LongLong", "ULongLong"}
_LONG_PARENTS = {"Objects", "Connections", "Documents"}
_UNESC = (("&quot;", '"'), ("&lf;", "\n"), ("&cr;", "\r"), ("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"))


def _unesc(s):
    for a, b in _UNESC:
        s = s.replace(a, b)
    return s


def _tokenize_values(s):
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c in " \t,\r\n":
            i += 1
        elif c == '"':
            j = s.find('"', i + 1)
            if j < 0:
                j = n
            out.append(("S", s[i + 1:j]))
            i = j + 1
        elif c == "*":
            j = i + 1
            while j < n and s[j].isdigit():
                j += 1
            out.append(("A", int(s[i + 1:j] or 0)))
            i = j
        else:
            j = i
            while j < n and s[j] not in ', \t':
                j += 1
            out.append(("T", s[i:j]))
            i = j
    return out


def _num(tok):
    try:
        return int(tok)
    except ValueError:
        try:
            return float(tok)
        except ValueError:
            return None


def _s(text):
    b = text.encode("utf-8")
    return b"S" + struct.pack("<I", len(b)) + b


def _enc_array(name, toks):
    nums = []
    for t in toks:
        v = _num(t.strip())
        nums.append(0 if v is None else v)
    if name in _D_ARR or any(isinstance(x, float) for x in nums):
        ch, fmt = b"d", "d"
        nums = [float(x) for x in nums]
    elif name == "KeyTime":
        ch, fmt = b"l", "q"
    elif name in ("KeyValueFloat", "KeyAttrDataFloat"):
        ch, fmt = b"f", "f"
        nums = [float(x) for x in nums]
    elif nums and max(abs(x) for x in nums) > 2 ** 31 - 1:
        ch, fmt = b"l", "q"
    else:
        ch, fmt = b"i", "i"
    data = struct.pack("<%d%s" % (len(nums), fmt), *nums)
    return ch + struct.pack("<III", len(nums), 0, len(data)) + data


def _finalize(node, parent_name):
    name = node["name"]
    if node["arr"] is not None:
        props = [node["arr"]]
    else:
        raw = node["raw"]
        ptype = raw[1][1] if name == "P" and len(raw) > 1 and raw[1][0] == "S" else None
        long_ctx = parent_name in _LONG_PARENTS or name == "RootNode"
        props = []
        for idx, (k, v) in enumerate(raw):
            if k == "S":
                text = _unesc(v)
                if parent_name == "Objects" and idx == 1 and "::" in text:
                    cls, nm = text.split("::", 1)
                    text = nm + "\x00\x01" + cls
                props.append(_s(text))
                continue
            n = _num(v)
            if n is None:
                props.append(_s(v))
            elif name == "P" and idx >= 4:
                if ptype in _P_INT:
                    props.append(b"I" + struct.pack("<i", int(n)))
                elif ptype in _P_LONG:
                    props.append(b"L" + struct.pack("<q", int(n)))
                else:
                    props.append(b"D" + struct.pack("<d", float(n)))
            elif isinstance(n, int):
                if long_ctx or not (-2 ** 31 <= n < 2 ** 31):
                    props.append(b"L" + struct.pack("<q", n))
                else:
                    props.append(b"I" + struct.pack("<i", n))
            else:
                props.append(b"D" + struct.pack("<d", n))
    node["enc"] = props
    for c in node["children"]:
        _finalize(c, name)


def _write_node(buf, node):
    start = len(buf)
    name = node["name"].encode("utf-8")
    props = node["enc"]
    buf += struct.pack("<III", 0, len(props), 0)
    buf += struct.pack("<B", len(name)) + name
    ps = len(buf)
    for p in props:
        buf += p
    plen = len(buf) - ps
    if node["children"]:
        for c in node["children"]:
            _write_node(buf, c)
        buf += b"\x00" * 13
    struct.pack_into("<III", buf, start, len(buf), len(props), plen)


def ascii_to_binary(src_path, dst_path):
    """Convert an ASCII FBX (7.x) to a binary FBX that Blender can import."""
    with open(src_path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    root, stack, i = [], [], 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith(";"):
            continue
        if line == "}":
            if stack:
                stack.pop()
            continue
        name, _, rest = line.partition(":")
        rest = rest.strip()
        opens = rest.endswith("{")
        if opens:
            rest = rest[:-1].strip()
        vals = _tokenize_values(rest)
        node = {"name": name.strip(), "raw": [], "arr": None, "children": [], "enc": []}
        if opens and any(k == "A" for k, _ in vals):
            data = []
            while i < len(lines):
                ln = lines[i].strip()
                i += 1
                if ln == "}":
                    break
                if ln.startswith("a:"):
                    ln = ln[2:]
                data.append(ln)
            toks = [t for t in ",".join(data).split(",") if t.strip()]
            node["arr"] = _enc_array(node["name"], toks)
            opens = False
        else:
            node["raw"] = [(k, v) for k, v in vals if k != "A"]
        (stack[-1]["children"] if stack else root).append(node)
        if opens:
            stack.append(node)
    for n in root:
        _finalize(n, "")
    buf = bytearray(b"Kaydara FBX Binary  \x00\x1a\x00" + struct.pack("<I", 7400))
    for n in root:
        _write_node(buf, n)
    buf += b"\x00" * 13
    with open(dst_path, "wb") as fh:
        fh.write(bytes(buf))
