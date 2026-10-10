bl_info = {
    "name": "Retarget Bake",
    "author": "local",
    "version": (1, 3, 2),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar > Retarget",
    "description": "Bake an animation from a source armature (FBX/GLB/Mesh2Motion) onto another skeleton",
    "category": "Animation",
}

import os
import re
import json
import shutil
import struct
import tempfile
import urllib.request
import bpy
from bpy.props import (StringProperty, EnumProperty, BoolProperty, FloatProperty,
                       IntProperty, PointerProperty, CollectionProperty)
from bpy_extras.io_utils import ImportHelper
from mathutils import Matrix, Vector

from .fbx_ascii import ascii_to_binary

MIXAMO = "mixamorig:"

# ---------------------------------------------------------------- presets
# (source bone, target bone, mode, root motion)
# DELTA = copy the rotation relative to the rest pose (world space)
# AIM   = point the bone in the same world direction as the source bone
_BIP_COMMON = [
    ("BIP01 PELVIS", "DELTA", True), ("BIP01 SPINE", "DELTA", False), ("BIP01 SPINE1", "DELTA", False),
    ("BIP01 SPINE2", "DELTA", False), ("BIP01 NECK", "AIM", False), ("BIP01 HEAD", "AIM", False),
]

PRESET_MIXAMO = [
    ("Hips", "BIP01 PELVIS", "DELTA", True),
    ("Spine", "BIP01 SPINE", "DELTA", False),
    ("Spine1", "BIP01 SPINE1", "DELTA", False),
    ("Spine2", "BIP01 SPINE2", "DELTA", False),
    ("Neck", "BIP01 NECK", "AIM", False),
    ("Head", "BIP01 HEAD", "AIM", False),
    ("LeftShoulder", "BIP01 L CLAVICLE", "DELTA", False),
    ("LeftArm", "BIP01 L UPPERARM", "AIM", False),
    ("LeftForeArm", "BIP01 L FOREARM", "AIM", False),
    ("RightShoulder", "BIP01 R CLAVICLE", "DELTA", False),
    ("RightArm", "BIP01 R UPPERARM", "AIM", False),
    ("RightForeArm", "BIP01 R FOREARM", "AIM", False),
    ("LeftUpLeg", "BIP01 L THIGH", "DELTA", False),
    ("LeftLeg", "BIP01 L CALF", "DELTA", False),
    ("LeftFoot", "BIP01 L FOOT", "DELTA", False),
    ("RightUpLeg", "BIP01 R THIGH", "DELTA", False),
    ("RightLeg", "BIP01 R CALF", "DELTA", False),
    ("RightFoot", "BIP01 R FOOT", "DELTA", False),
]
CHAINS_MIXAMO = [
    ("BIP01 L THIGH", "BIP01 L CALF", "LeftFoot", True),
    ("BIP01 R THIGH", "BIP01 R CALF", "RightFoot", True),
    ("BIP01 L UPPERARM", "BIP01 L FOREARM", "LeftHand", False),
    ("BIP01 R UPPERARM", "BIP01 R FOREARM", "RightHand", False),
]

# Mesh2Motion / Quaternius humanoid rig
PRESET_M2M = [
    ("pelvis", "BIP01 PELVIS", "DELTA", True),
    ("spine_01", "BIP01 SPINE", "DELTA", False),
    ("spine_02", "BIP01 SPINE1", "DELTA", False),
    ("spine_03", "BIP01 SPINE2", "DELTA", False),
    ("neck_01", "BIP01 NECK", "AIM", False),
    ("head", "BIP01 HEAD", "AIM", False),
    ("clavicle_l", "BIP01 L CLAVICLE", "DELTA", False),
    ("upperarm_l", "BIP01 L UPPERARM", "AIM", False),
    ("lowerarm_l", "BIP01 L FOREARM", "AIM", False),
    ("clavicle_r", "BIP01 R CLAVICLE", "DELTA", False),
    ("upperarm_r", "BIP01 R UPPERARM", "AIM", False),
    ("lowerarm_r", "BIP01 R FOREARM", "AIM", False),
    ("thigh_l", "BIP01 L THIGH", "DELTA", False),
    ("calf_l", "BIP01 L CALF", "DELTA", False),
    ("foot_l", "BIP01 L FOOT", "DELTA", False),
    ("thigh_r", "BIP01 R THIGH", "DELTA", False),
    ("calf_r", "BIP01 R CALF", "DELTA", False),
    ("foot_r", "BIP01 R FOOT", "DELTA", False),
]
CHAINS_M2M = [
    ("BIP01 L THIGH", "BIP01 L CALF", "foot_l", True),
    ("BIP01 R THIGH", "BIP01 R CALF", "foot_r", True),
    ("BIP01 L UPPERARM", "BIP01 L FOREARM", "hand_l", False),
    ("BIP01 R UPPERARM", "BIP01 R FOREARM", "hand_r", False),
]
# Mesh2Motion spider rig -> Gothic crawler (Bip01 skeleton with mandibles "J"/"J1", arms and legs)
PRESET_SPIDER = [
    ("hips", "Bip01 Pelvis", "DELTA", True),
    ("tail_1", "Bip01 Spine", "DELTA", False),
    ("tail_2", "Bip01 Spine1", "DELTA", False),
    ("spine_1", "Bip01 Spine2", "DELTA", False),
    ("spine_2", "Bip01 Neck", "DELTA", False),
    ("head", "Bip01 Head", "DELTA", False),
    ("teeth_l", "Bip01 L J", "DELTA", False),
    ("teeth_l", "Bip01 L J1", "DELTA", False),
    ("teeth_r", "Bip01 R J", "DELTA", False),
    ("teeth_r", "Bip01 R J1", "DELTA", False),
    ("legs_anchor_1_l", "Bip01 L Clavicle", "DELTA", False),
    ("legs_anchor_1_r", "Bip01 R Clavicle", "DELTA", False),
    ("leg_a_1_l", "Bip01 L UpperArm", "DELTA", False),
    ("leg_a_2_l", "Bip01 L Forearm", "DELTA", False),
    ("leg_a_3_l", "Bip01 L Hand", "DELTA", False),
    ("leg_a_1_r", "Bip01 R UpperArm", "DELTA", False),
    ("leg_a_2_r", "Bip01 R Forearm", "DELTA", False),
    ("leg_a_3_r", "Bip01 R Hand", "DELTA", False),
    ("leg_d_1_l", "Bip01 L Thigh", "DELTA", False),
    ("leg_d_2_l", "Bip01 L Calf", "DELTA", False),
    ("leg_d_3_l", "Bip01 L Foot", "DELTA", False),
    ("leg_d_1_r", "Bip01 R Thigh", "DELTA", False),
    ("leg_d_2_r", "Bip01 R Calf", "DELTA", False),
    ("leg_d_3_r", "Bip01 R Foot", "DELTA", False),
]
CHAINS_SPIDER = [
    ("Bip01 L UpperArm", "Bip01 L Forearm", "leg_a_tip_l", True),
    ("Bip01 R UpperArm", "Bip01 R Forearm", "leg_a_tip_r", True),
    ("Bip01 L Thigh", "Bip01 L Calf", "leg_d_tip_l", True),
    ("Bip01 R Thigh", "Bip01 R Calf", "leg_d_tip_r", True),
]
# (name, bone table, limb chains, limb IK on by default)
# The spider legs are built very differently from the crawler limbs, so IK is off for it
# (the chains are still used to work out the scale).
PRESETS = [("Mixamo -> BIP01", PRESET_MIXAMO, CHAINS_MIXAMO, True),
           ("Mesh2Motion humanoid -> BIP01", PRESET_M2M, CHAINS_M2M, True),
           ("Mesh2Motion spider -> Crawler (Bip01)", PRESET_SPIDER, CHAINS_SPIDER, False)]

# Mesh2Motion animation library (CC0), raw files from the project's GitHub repository
M2M_URL = "https://raw.githubusercontent.com/Mesh2Motion/mesh2motion-app/main/static/animations/"
CATALOG = [
    ("human-base-animations.glb", "Human - base (87)", "Humanoid rig, base animation set"),
    ("human-addon-animations.glb", "Human - addon (75)", "Humanoid rig, extra animations"),
    ("human-mocap-animations.glb", "Human - mocap (16)", "Humanoid rig, motion capture clips"),
    ("spider-animations.glb", "Spider (10)", "Spider rig"),
    ("fox-animations.glb", "Fox (14)", "Quadruped fox rig"),
    ("horse-animations.glb", "Horse (14)", "Quadruped horse rig"),
    ("bird-animations.glb", "Bird (5)", "Bird rig"),
    ("dragon-animations.glb", "Dragon (5)", "Dragon rig"),
    ("kaiju-animations.glb", "Kaiju (10)", "Kaiju rig"),
    ("snake-animations.glb", "Snake (8)", "Snake rig"),
    ("shark-animations.glb", "Shark (7)", "Shark rig"),
]


# ---------------------------------------------------------------- properties
class RB_Item(bpy.types.PropertyGroup):
    src: StringProperty(name="Source bone")
    tgt: StringProperty(name="Target bone")
    mode: EnumProperty(
        name="Mode",
        items=[("DELTA", "Relative", "Copy rotation relative to rest pose", 'CON_ROTLIKE', 0),
               ("AIM", "Aim", "Point the bone in the same world direction as the source bone", 'TRACKING', 1)],
        default="DELTA")
    use_loc: BoolProperty(name="Root motion", default=False,
                          description="This bone receives the source root translation")


class RB_Chain(bpy.types.PropertyGroup):
    use: BoolProperty(name="Use", default=True)
    up: StringProperty(name="Target upper bone")
    low: StringProperty(name="Target lower bone")
    src_end: StringProperty(name="Source end bone",
                            description="Source bone whose head is the effector (foot/hand)")


class RB_Name(bpy.types.PropertyGroup):
    value: StringProperty()


def _arm_poll(self, obj):
    return obj.type == 'ARMATURE'


_action_items_cache = []


def _action_items(self, context):
    global _action_items_cache
    items = [(a.value, a.value, "") for a in self.src_actions]
    _action_items_cache = items or [("NONE", "(no animations)", "")]
    return _action_items_cache


def _clean_name(n):
    return n.split("|")[-1]


def _on_action_change(self, context):
    if self.src_action and self.src_action != "NONE":
        self.action_name = _clean_name(self.src_action)


class RB_Settings(bpy.types.PropertyGroup):
    source: PointerProperty(name="Source", type=bpy.types.Object, poll=_arm_poll)
    target: PointerProperty(name="Target", type=bpy.types.Object, poll=_arm_poll)
    items: CollectionProperty(type=RB_Item)
    index: IntProperty()
    chains: CollectionProperty(type=RB_Chain)
    src_actions: CollectionProperty(type=RB_Name)
    src_action: EnumProperty(name="Animation", items=_action_items, update=_on_action_change)
    src_junk: StringProperty()
    catalog: EnumProperty(name="Library", items=[(a, b, c) for a, b, c in CATALOG])
    bake_all: BoolProperty(name="Bake all animations", default=False,
                           description="Bake every animation of the source file as a separate action")
    chain_src: StringProperty(name="Source chain start")
    chain_tgt: StringProperty(name="Target chain start")
    chain_len: IntProperty(name="Length", default=0, min=0, description="Number of bones (0 = to the end of the chain)")
    chain_mode: EnumProperty(
        name="Mode",
        items=[("DELTA", "Relative", "Copy rotation relative to rest pose"),
               ("AIM", "Aim", "Point bones in the same world direction as the source")],
        default="DELTA")
    action_name: StringProperty(name="Action name", default="Baked")
    auto_scale: BoolProperty(name="Auto scale", default=True,
                             description="Scale root motion by the ratio of leg lengths")
    scale: FloatProperty(name="Scale", default=1.0, min=0.001, soft_max=5.0)
    fit_ground: BoolProperty(name="Fit to ground", default=True,
                             description="Shift the root vertically so the lowest joints keep the same ground clearance")
    in_place: BoolProperty(name="In place", default=False,
                           description="Remove the overall travel of the root so the cycle stays in place")
    root_motion: BoolProperty(name="Motion on root bone", default=True,
                              description="Put the body travel on the root bone (needed for in-game movement); "
                                          "the hip bone keeps only the local motion")
    root_bone: StringProperty(name="Root bone")
    root_vertical: BoolProperty(name="Include vertical", default=False,
                                description="Root also takes the vertical motion (otherwise only X/Y travel)")
    use_ik: BoolProperty(name="Limb IK", default=True,
                         description="Two-bone IK pass so feet/hands reach the source positions "
                                     "(scaled by limb length) on skeletons with different proportions")
    set_range: BoolProperty(name="Set scene range", default=True)
    delete_source: BoolProperty(name="Delete source after bake", default=True)


# ---------------------------------------------------------------- helpers
def _norm(n):
    n = n.split(":")[-1].lower()
    return "".join(c for c in n if c.isalnum())


def _add_item(s, src, tgt, mode, loc):
    it = s.items.add()
    it.src, it.tgt, it.mode, it.use_loc = src, tgt, mode, loc


def _src_name(src, n):
    if n in src.data.bones:
        return n
    if MIXAMO + n in src.data.bones:
        return MIXAMO + n
    return None


def automap(s):
    """Fill the mapping from the best matching preset (or by matching names). Returns (count, preset name)."""
    src, tgt = s.source, s.target
    s.items.clear()
    s.chains.clear()
    s.root_bone = ""
    best = None
    tlook = {b.name.casefold(): b.name for b in tgt.data.bones}
    for pname, table, chains, ik_on in PRESETS:
        hits = [(_src_name(src, sn), tlook[tn.casefold()], mode, loc) for sn, tn, mode, loc in table
                if _src_name(src, sn) and tn.casefold() in tlook]
        if best is None or len(hits) > len(best[1]):
            best = (pname, hits, chains, ik_on)
    used = None
    if best and len(best[1]) >= 4:
        used = best[0]
        s.use_ik = best[3]
        for sn, tn, mode, loc in best[1]:
            _add_item(s, sn, tn, mode, loc)
        for up, low, end, on in best[2]:
            full = _src_name(src, end)
            if up.casefold() in tlook and low.casefold() in tlook and full:
                c = s.chains.add()
                c.up, c.low, c.src_end, c.use = tlook[up.casefold()], tlook[low.casefold()], full, on
    else:
        tnorm = {_norm(b.name): b.name for b in tgt.data.bones}
        seen = set()
        for b in src.data.bones:
            t = tnorm.get(_norm(b.name))
            if t and t not in seen:
                seen.add(t)
                _add_item(s, b.name, t, "DELTA", b.parent is None)
        if len(s.items):
            used = "matching names"
    loc = next((it for it in s.items if it.use_loc), None)
    if loc and loc.tgt in tgt.data.bones:
        b = tgt.data.bones[loc.tgt]
        while b.parent:
            b = b.parent
        mapped = {it.tgt for it in s.items}
        if b.name != loc.tgt and b.name not in mapped:
            s.root_bone = b.name
    return len(s.items), used


def map_chain(s):
    """Map a chain of bones one-to-one along the first child, starting from the chosen bones."""
    sb = s.source.data.bones.get(s.chain_src) if s.source else None
    tb = s.target.data.bones.get(s.chain_tgt) if s.target else None
    if not sb or not tb:
        raise RuntimeError("Choose a valid source and target start bone")
    limit = s.chain_len or 10000
    pairs = []
    while sb and tb and len(pairs) < limit:
        pairs.append((sb.name, tb.name))
        sb = sb.children[0] if sb.children else None
        tb = tb.children[0] if tb.children else None
    existing = {it.tgt: it for it in s.items}
    for sn, tn in pairs:
        it = existing.get(tn)
        if it is None:
            it = s.items.add()
            it.tgt = tn
        it.src, it.mode = sn, s.chain_mode
    return len(pairs)


def _leg_len(arm, bone_names):
    sc = arm.matrix_world.to_scale().x
    bs = [arm.data.bones[n] for n in bone_names]
    foot = min(bs, key=lambda b: (arm.matrix_world @ b.head_local).z)
    total, b = 0.0, foot
    for _ in range(2):
        if b.parent:
            b = b.parent
            total += b.length * sc
    return total


def _two_bone(A, T, l1, l2, pole):
    """Analytic two-bone IK. Returns (knee, effector) world positions."""
    v = T - A
    d = v.length
    if d < 1e-8:
        return None
    u = v / d
    d = max(abs(l1 - l2) + 1e-4, min(l1 + l2 - 1e-4, d))
    a = (l1 * l1 - l2 * l2 + d * d) / (2.0 * d)
    h = max(l1 * l1 - a * a, 0.0) ** 0.5
    p = pole - u * pole.dot(u)
    if p.length < 1e-6:
        p = u.cross(Vector((1, 0, 0)))
        if p.length < 1e-6:
            p = u.cross(Vector((0, 1, 0)))
    p.normalize()
    return A + u * a + p * h, A + u * d


# ---------------------------------------------------------------- import / download / cleanup
def cache_dir():
    try:
        return bpy.utils.extension_path_user(__package__, path="animations", create=True)
    except Exception:
        d = os.path.join(tempfile.gettempdir(), "retarget_bake_cache")
        os.makedirs(d, exist_ok=True)
        return d


def fetch_catalog_file(fname):
    dst = os.path.join(cache_dir(), fname)
    if os.path.exists(dst) and os.path.getsize(dst) > 1000:
        return dst
    if not bpy.app.online_access:
        raise RuntimeError("Online access is disabled. Enable it in Preferences > System > Network, "
                           "or download the file manually and use the Import button.")
    req = urllib.request.Request(M2M_URL + fname, headers={"User-Agent": "retarget_bake"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dst + ".part", "wb") as fh:
        shutil.copyfileobj(resp, fh)
    os.replace(dst + ".part", dst)
    return dst


def assign_action(obj, act):
    ad = obj.animation_data or obj.animation_data_create()
    ad.use_nla = False
    ad.action = act
    if hasattr(ad, "action_suitable_slots"):
        slots = list(ad.action_suitable_slots)
        if slots:
            ad.action_slot = slots[0]
        elif len(act.slots):
            ad.action_slot = act.slots[0]


def import_source(context, filepath):
    s = context.scene.rb_settings
    kinds = ("objects", "actions", "materials", "images", "meshes", "armatures", "collections")
    before = {k: set(getattr(bpy.data, k).keys()) for k in kinds}
    ext = os.path.splitext(filepath)[1].lower()
    tmp = None
    try:
        if ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=filepath)
        else:
            path = filepath
            with open(path, "rb") as fh:
                is_binary = fh.read(18) == b"Kaydara FBX Binary"
            if not is_binary:
                # Blender imports only binary FBX: convert ASCII FBX on the fly
                tmp = os.path.join(bpy.app.tempdir or tempfile.gettempdir(), "rb_ascii_converted.fbx")
                ascii_to_binary(path, tmp)
                path = tmp
            bpy.ops.import_scene.fbx(filepath=path)
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
    arms = [o for o in bpy.data.objects if o.name not in before["objects"] and o.type == 'ARMATURE']
    if not arms:
        raise RuntimeError("No armature found in the file")
    src = max(arms, key=lambda o: len(o.data.bones))
    new_actions = sorted([a for a in bpy.data.actions if a.name not in before["actions"]], key=lambda a: a.name.casefold())
    if src.animation_data:
        for tr in list(src.animation_data.nla_tracks):
            src.animation_data.nla_tracks.remove(tr)
    for a in new_actions:
        a.use_fake_user = True  # keep them alive until we are done
    s.source = src
    s.src_actions.clear()
    for a in new_actions:
        s.src_actions.add().value = a.name
    s.src_junk = json.dumps({k: [n for n in getattr(bpy.data, k).keys() if n not in before[k]]
                             for k in ("actions", "materials", "images", "objects", "collections")})
    if new_actions:
        s.src_action = new_actions[0].name
    s.action_name = (_clean_name(new_actions[0].name) if ext in (".glb", ".gltf") and new_actions
                     else os.path.splitext(os.path.basename(filepath))[0])
    if s.target:
        automap(s)
    return src


def remove_source(src, junk=None):
    try:
        j = json.loads(junk) if junk else {}
    except ValueError:
        j = {}
    objs = [src] + list(src.children_recursive)
    for n in j.get("objects", []):
        o = bpy.data.objects.get(n)
        if o is not None and o not in objs:
            objs.append(o)
    datas = [o.data for o in objs if o.data]
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    ids = {d for d in datas if d.users == 0}
    if ids:
        bpy.data.batch_remove(ids)
    ids = set()
    for kind in ("actions", "materials", "images"):
        coll = getattr(bpy.data, kind)
        for n in j.get(kind, []):
            if n in coll:
                ids.add(coll[n])
    for n in j.get("collections", []):
        c = bpy.data.collections.get(n)
        if c is not None and not c.objects and not c.children:
            ids.add(c)
    if ids:
        bpy.data.batch_remove(ids)


def do_bake(context, s):
    src, tgt, scene = s.source, s.target, context.scene
    items = [it for it in s.items if it.src in src.data.bones and it.tgt in tgt.data.bones]
    if not items:
        raise RuntimeError("No valid bone pairs in the mapping")
    sa = src.animation_data.action if src.animation_data else None
    if sa is None:
        raise RuntimeError("Source armature has no action")
    src.animation_data.use_nla = False
    f0, f1 = int(sa.frame_range[0]), int(round(sa.frame_range[1]))
    tmap = {it.tgt: (it.src, it.mode) for it in items}
    loc_item = next((it for it in items if it.use_loc), None)
    loc_tgt = loc_item.tgt if loc_item else None

    tw, sw0 = tgt.matrix_world, src.matrix_world
    tsc = tw.to_scale().x
    root_tgt = None
    if s.root_motion and loc_item and s.root_bone in tgt.data.bones and s.root_bone not in tmap:
        root_tgt = s.root_bone

    rest_t = {b.name: tw @ b.matrix_local for b in tgt.data.bones}
    rest_s_inv = {it.src: (sw0 @ src.data.bones[it.src].matrix_local).to_3x3().normalized().inverted() for it in items}
    rest_s_head = lambda n: (sw0 @ src.data.bones[n].matrix_local).translation
    root_rest = rest_s_head(loc_item.src).copy() if loc_item else Vector()

    chains = {}
    if True:
        for c in s.chains:
            if not c.use or c.up not in tmap or c.low not in tmap or c.src_end not in src.data.bones:
                continue
            bu, bl = tgt.data.bones[c.up], tgt.data.bones[c.low]
            if bl.parent != bu:
                continue
            su, sl = tmap[c.up][0], tmap[c.low][0]
            l1, l2 = bu.length * tsc, bl.length * tsc
            sl1 = (rest_s_head(sl) - rest_s_head(su)).length
            sl2 = (rest_s_head(c.src_end) - rest_s_head(sl)).length
            if sl1 + sl2 < 1e-6:
                continue
            chains[c.up] = {"low": c.low, "src_up": su, "src_end": c.src_end, "l1": l1, "l2": l2,
                            "ratio": (l1 + l2) / (sl1 + sl2)}

    if s.auto_scale:
        rs = [c["ratio"] for c in chains.values()]
        if rs:
            ratio = sum(rs) / len(rs)
        else:
            a = _leg_len(src, [it.src for it in items])
            b = _leg_len(tgt, [it.tgt for it in items])
            ratio = (b / a) if a > 1e-6 and b > 1e-6 else 1.0
    else:
        ratio = s.scale
    if not s.use_ik:
        chains = {}

    def depth(b):
        d = 0
        while b.parent:
            b = b.parent
            d += 1
        return d
    order = sorted(tgt.data.bones, key=depth)

    cur_frame = scene.frame_current
    frames, src_min = {}, 1e9
    for f in range(f0, f1 + 1):
        scene.frame_set(f)
        dg = context.evaluated_depsgraph_get()
        se = src.evaluated_get(dg)
        swf = se.matrix_world
        rot = {}
        for it in items:
            m = swf @ se.pose.bones[it.src].matrix
            rot[it.src] = m.to_3x3().normalized()
            src_min = min(src_min, m.translation.z)
        if loc_item:
            hp = (swf @ se.pose.bones[loc_item.src].matrix).translation.copy()
            hd = (hp - root_rest) * ratio
        else:
            hd = Vector()
        ikrel = {}
        for up, c in chains.items():
            ru = (swf @ se.pose.bones[c["src_up"]].matrix).translation
            ee = (swf @ se.pose.bones[c["src_end"]].matrix).translation
            ikrel[up] = (ee - ru) * c["ratio"]
        frames[f] = [rot, hd, ikrel]

    if s.in_place and loc_item and f1 > f0:
        d0, d1 = frames[f0][1], frames[f1][1]
        for f in range(f0, f1 + 1):
            t = (f - f0) / (f1 - f0)
            frames[f][1] = frames[f][1] - Vector(((d1.x - d0.x) * t, (d1.y - d0.y) * t, 0.0))

    def fk_R(n, rot):
        sname, mode = tmap[n]
        Tr = rest_t[n].to_3x3().normalized()
        if mode == "DELTA":
            return (rot[sname] @ rest_s_inv[sname]) @ Tr
        v = rot[sname] @ Vector((0, 1, 0))
        d = Tr @ Vector((0, 1, 0))
        return d.rotation_difference(v).to_matrix() @ Tr

    def solve(rot, hdelta, ikrel):
        pose_w, basis, ik_R = {}, {}, {}
        for b in order:
            n = b.name
            rest = rest_t[n]
            if b.parent:
                L = pose_w[b.parent.name] @ (rest_t[b.parent.name].inverted() @ rest)
            else:
                L = rest.copy()
            if n in tmap:
                if n in ik_R:
                    R = ik_R[n]
                else:
                    R = fk_R(n, rot)
                    if n in ikrel:
                        c = chains[n]
                        R2 = fk_R(c["low"], rot)
                        A = L.translation
                        knee_fk = R @ Vector((0, c["l1"], 0))
                        res = _two_bone(A, A + ikrel[n], c["l1"], c["l2"], knee_fk)
                        if res:
                            K, E = res
                            d1 = (K - A).normalized()
                            d2 = (E - K).normalized()
                            R = (R @ Vector((0, 1, 0))).rotation_difference(d1).to_matrix() @ R
                            ik_R[c["low"]] = (R2 @ Vector((0, 1, 0))).rotation_difference(d2).to_matrix() @ R2
                pos = (rest.translation + hdelta) if n == loc_tgt else L.translation
                M = Matrix.Translation(pos) @ R.to_4x4()
            elif n == root_tgt:
                dv = Vector((hdelta.x, hdelta.y, hdelta.z if s.root_vertical else 0.0))
                M = Matrix.Translation(dv) @ L
            else:
                M = L
            basis[n] = L.inverted() @ M
            pose_w[n] = M
        return pose_w, basis

    zoff = 0.0
    if s.fit_ground:
        src_rest_min = min(rest_s_head(it.src).z for it in items)
        tgt_rest_min = min(rest_t[it.tgt].translation.z for it in items)
        tgt_min = 1e9
        for rot, hd, ik in frames.values():
            pw, _ = solve(rot, hd, ik)
            tgt_min = min(tgt_min, min(pw[t].translation.z for t in tmap))
        zoff = (ratio * src_min - tgt_min) + (tgt_rest_min - ratio * src_rest_min)

    if tgt.animation_data is None:
        tgt.animation_data_create()
    old = tgt.animation_data.action
    if old:
        old.use_fake_user = True  # keep the previous action, do not lose it
    act = bpy.data.actions.new(s.action_name or "Baked")
    tgt.animation_data.action = act

    for pb in tgt.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.scale = (1, 1, 1)
    for n in tmap:
        tgt.pose.bones[n].rotation_mode = 'QUATERNION'

    prev = {}
    for f, (rot, hd, ik) in frames.items():
        h = hd.copy()
        h.z += zoff
        _, basis = solve(rot, h, ik)
        for n in tmap:
            pb = tgt.pose.bones[n]
            q = basis[n].to_quaternion()
            if n in prev:
                q.make_compatible(prev[n])
            prev[n] = q.copy()
            pb.rotation_quaternion = q
            pb.keyframe_insert("rotation_quaternion", frame=f)
            if n == loc_tgt:
                pb.location = basis[n].to_translation()
                pb.keyframe_insert("location", frame=f)
        if root_tgt:
            pb = tgt.pose.bones[root_tgt]
            pb.location = basis[root_tgt].to_translation()
            pb.keyframe_insert("location", frame=f)

    if s.set_range:
        scene.frame_start, scene.frame_end = f0, f1
    scene.frame_set(f0 if s.set_range else cur_frame)
    return {"frames": (f0, f1), "scale": ratio, "ground_offset": zoff, "bones": len(tmap),
            "action": act.name, "root": root_tgt, "ik": list(chains.keys())}


# ---------------------------------------------------------------- operators
class RB_OT_import(bpy.types.Operator, ImportHelper):
    bl_idname = "retarget_bake.import_fbx"
    bl_label = "Import source file"
    bl_description = "Import an FBX or GLB/glTF with animations and use its armature as the source"
    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx;*.glb;*.gltf", options={'HIDDEN'})

    def execute(self, context):
        try:
            import_source(context, self.filepath)
        except Exception as e:
            self.report({'ERROR'}, "Could not import the file: %s" % e)
            return {'CANCELLED'}
        return {'FINISHED'}


class RB_OT_catalog(bpy.types.Operator):
    bl_idname = "retarget_bake.import_catalog"
    bl_label = "Download & import from Mesh2Motion"
    bl_description = "Download the selected Mesh2Motion animation library (CC0) from GitHub and use it as the source"

    def execute(self, context):
        s = context.scene.rb_settings
        try:
            path = fetch_catalog_file(s.catalog)
            import_source(context, path)
        except Exception as e:
            self.report({'ERROR'}, "Could not get the library: %s" % e)
            return {'CANCELLED'}
        self.report({'INFO'}, "Loaded %d animations" % len(s.src_actions))
        return {'FINISHED'}


class RB_OT_automap(bpy.types.Operator):
    bl_idname = "retarget_bake.automap"
    bl_label = "Auto-map bones"
    bl_description = "Fill the mapping from a preset (Mixamo / Mesh2Motion humanoid -> BIP01), otherwise by matching names"

    @classmethod
    def poll(cls, context):
        s = context.scene.rb_settings
        return s.source is not None and s.target is not None

    def execute(self, context):
        n, used = automap(context.scene.rb_settings)
        if n == 0:
            self.report({'WARNING'}, "No known preset matches: use 'Map chain' or add rows manually")
        else:
            self.report({'INFO'}, "Mapped %d bones (%s)" % (n, used))
        return {'FINISHED'}


class RB_OT_item(bpy.types.Operator):
    bl_idname = "retarget_bake.item"
    bl_label = "Mapping row"
    action: EnumProperty(items=[("ADD", "Add", ""), ("REMOVE", "Remove", ""), ("CLEAR", "Clear", "")])

    def execute(self, context):
        s = context.scene.rb_settings
        if self.action == "ADD":
            s.items.add()
            s.index = len(s.items) - 1
        elif self.action == "CLEAR":
            s.items.clear()
            s.chains.clear()
            s.index = 0
        elif s.items:
            s.items.remove(s.index)
            s.index = max(0, min(s.index, len(s.items) - 1))
        return {'FINISHED'}


class RB_OT_map_chain(bpy.types.Operator):
    bl_idname = "retarget_bake.map_chain"
    bl_label = "Map chain"
    bl_description = "Map the source chain to the target chain bone by bone (following the first child)"

    @classmethod
    def poll(cls, context):
        s = context.scene.rb_settings
        return s.source is not None and s.target is not None and bool(s.chain_src) and bool(s.chain_tgt)

    def execute(self, context):
        try:
            n = map_chain(context.scene.rb_settings)
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        self.report({'INFO'}, "Mapped %d bones" % n)
        return {'FINISHED'}


class RB_OT_bake(bpy.types.Operator):
    bl_idname = "retarget_bake.bake"
    bl_label = "Bake animation"
    bl_description = "Bake the source animation onto the target armature as a new action"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        s = context.scene.rb_settings
        return s.source is not None and s.target is not None and len(s.items) > 0 and s.source != s.target

    def execute(self, context):
        s = context.scene.rb_settings
        src = s.source
        listed = [bpy.data.actions[a.value] for a in s.src_actions if a.value in bpy.data.actions]
        if listed:
            chosen = bpy.data.actions.get(s.src_action)
            todo = listed if s.bake_all else ([chosen] if chosen else listed[:1])
        else:
            todo = [None]  # use the action that is already assigned to the source
        wm = context.window_manager
        wm.progress_begin(0, len(todo))
        infos = []
        try:
            for i, act in enumerate(todo):
                if act is not None:
                    assign_action(src, act)
                    if len(todo) > 1:
                        s.action_name = _clean_name(act.name)
                info = do_bake(context, s)
                if len(todo) > 1:
                    bpy.data.actions[info["action"]].use_fake_user = True
                infos.append(info)
                wm.progress_update(i + 1)
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        finally:
            wm.progress_end()
        if s.delete_source:
            remove_source(src, s.src_junk)
            s.source = None
            s.src_actions.clear()
            s.src_junk = ""
            for info in infos:
                act = bpy.data.actions.get(info["action"])
                base_name = re.sub(r"\.\d{3}$", "", info["action"])
                if act is not None and base_name != info["action"] and base_name not in bpy.data.actions:
                    act.name = base_name
                    info["action"] = act.name
        last = infos[-1]
        self.report({'INFO'}, "Baked %d action(s); last '%s': frames %d-%d, %d bones, scale %.3f, root: %s, IK chains: %d" % (
            len(infos), last["action"], last["frames"][0], last["frames"][1], last["bones"], last["scale"],
            last["root"] or "-", len(last["ik"])))
        return {'FINISHED'}


# ---------------------------------------------------------------- UI
class RB_UL_items(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        s = context.scene.rb_settings
        row = layout.row(align=True)
        if s.source:
            row.prop_search(item, "src", s.source.data, "bones", text="")
        else:
            row.prop(item, "src", text="")
        if s.target:
            row.prop_search(item, "tgt", s.target.data, "bones", text="")
        else:
            row.prop(item, "tgt", text="")
        row.prop(item, "mode", text="", icon_only=True)
        row.prop(item, "use_loc", text="", icon='CON_LOCLIKE')


class RB_PT_panel(bpy.types.Panel):
    bl_label = "Retarget Bake"
    bl_idname = "RB_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Retarget"

    def draw(self, context):
        s = context.scene.rb_settings
        lay = self.layout
        box = lay.box()
        col = box.column(align=True)
        row = col.row(align=True)
        row.prop(s, "source", text="Source")
        row.operator("retarget_bake.import_fbx", text="", icon='IMPORT')
        row = col.row(align=True)
        row.prop(s, "catalog", text="")
        row.operator("retarget_bake.import_catalog", text="", icon='URL')
        if len(s.src_actions):
            col.prop(s, "src_action", text="Animation")
            col.prop(s, "bake_all")
        box.prop(s, "target", text="Target")

        lay.operator("retarget_bake.automap", icon='BONE_DATA')
        lay.template_list("RB_UL_items", "", s, "items", s, "index", rows=6)
        row = lay.row(align=True)
        op = row.operator("retarget_bake.item", text="Add", icon='ADD')
        op.action = "ADD"
        op = row.operator("retarget_bake.item", text="Remove", icon='REMOVE')
        op.action = "REMOVE"
        op = row.operator("retarget_bake.item", text="Clear", icon='X')
        op.action = "CLEAR"

        box = lay.box()
        box.label(text="Map chain (for different skeletons)")
        if s.source:
            box.prop_search(s, "chain_src", s.source.data, "bones", text="From")
        else:
            box.prop(s, "chain_src", text="From")
        if s.target:
            box.prop_search(s, "chain_tgt", s.target.data, "bones", text="To")
        else:
            box.prop(s, "chain_tgt", text="To")
        row = box.row(align=True)
        row.prop(s, "chain_len")
        row.prop(s, "chain_mode", text="")
        box.operator("retarget_bake.map_chain", icon='LINKED')

        box = lay.box()
        box.prop(s, "action_name")
        row = box.row(align=True)
        row.prop(s, "auto_scale")
        sub = row.row()
        sub.enabled = not s.auto_scale
        sub.prop(s, "scale", text="")
        box.prop(s, "fit_ground")
        box.prop(s, "in_place")
        box.prop(s, "set_range")
        box.prop(s, "delete_source")

        box = lay.box()
        box.prop(s, "root_motion")
        sub = box.column()
        sub.enabled = s.root_motion
        if s.target:
            sub.prop_search(s, "root_bone", s.target.data, "bones", text="Root")
        else:
            sub.prop(s, "root_bone", text="Root")
        sub.prop(s, "root_vertical")

        box = lay.box()
        box.prop(s, "use_ik")
        sub = box.column(align=True)
        sub.enabled = s.use_ik
        for c in s.chains:
            sub.prop(c, "use", text="%s / %s" % (c.up, c.low))

        lay.operator("retarget_bake.bake", icon='ACTION')


classes = (RB_Item, RB_Chain, RB_Name, RB_Settings, RB_OT_import, RB_OT_catalog, RB_OT_automap, RB_OT_item,
           RB_OT_map_chain, RB_OT_bake, RB_UL_items, RB_PT_panel)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.rb_settings = PointerProperty(type=RB_Settings)


def unregister():
    del bpy.types.Scene.rb_settings
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
