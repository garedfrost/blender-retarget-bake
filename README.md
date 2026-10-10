# Retarget Bake

A Blender add-on that bakes an animation from a **source armature** (Mixamo FBX, GLB/glTF, the
[Mesh2Motion](https://mesh2motion.org) animation library) onto a **different skeleton** and keeps the
target's mesh, vertex weights and rest pose untouched. Only a new action is created.

It was written for retargeting animations onto old-game skeletons (Gothic / Risen style `Bip01` rigs)
whose proportions and bone structure differ from the usual humanoid rigs.

Tested with Blender 5.2 (needs 4.2+, it is a Blender extension).

## Features

- **Sources:** FBX (binary and ASCII), GLB/glTF, or straight from the Mesh2Motion library
  (human, spider, fox, horse, bird, dragon, kaiju, snake, shark). The library files are downloaded from the
  project's GitHub repository on demand and cached.
- **Animation picker** for files with many animations, plus *Bake all animations*.
- **Auto-map presets:** Mixamo -> BIP01, Mesh2Motion humanoid -> BIP01, Mesh2Motion spider -> Gothic Crawler.
  Target bone names are matched case-insensitively. Anything else falls back to matching names.
- **Map chain:** map a chain of bones one-to-one (following the first child) for skeletons with a different structure,
  for example spider legs onto crawler arms or mandibles.
- **Root motion on the root bone** (`Bip01`), so in-game movement works; the pelvis keeps only local motion.
  Optional *In place* mode and *Include vertical*.
- **Scale** of the root motion from limb lengths, optional **fit to ground**.
- **Limb IK** (analytic two-bone IK) so feet/hands follow the source on rigs with different proportions.
- ASCII FBX files are converted on the fly (Blender itself only imports binary FBX).
- After baking, everything that came with the imported source (armature, meshes, helper objects, actions)
  is removed; previously assigned actions of the target are kept with a fake user.

## Install

Download `retarget_bake.zip` from the Releases page, then in Blender:
*Edit > Preferences > Add-ons > (arrow menu, top right) > Install from Disk...* and pick the zip.
Blender asks for the *network* permission: it is only used to download Mesh2Motion animation files.
Online access must be enabled (*Preferences > System > Network*) for the library download; local files work without it.

## Usage

Open the 3D viewport sidebar (`N`), tab **Retarget**.

1. Pick the **Target** armature (your model).
2. Load a **Source**: the import button for a local FBX/GLB, or choose a library file and press the download button.
3. Choose the **Animation** (or tick *Bake all animations*).
4. Press **Auto-map bones**. If no preset fits, use **Map chain** and/or add rows by hand
   (the icons on each row switch *Relative* / *Aim* mode and mark the root-motion bone).
5. Press **Bake animation**.

Modes: *Relative* copies the rotation relative to the rest pose, *Aim* points the bone in the same world direction
as the source bone (useful when the rest poses differ a lot, e.g. T-pose vs. lowered arms).

## Notes and limitations

- Weights are never modified, only a new action is created. Unmapped bones stay at rest and follow their parents.
- Limb IK is a plain two-bone solver for limbs whose bones form an upper/lower pair. It is off for the spider preset because
  spider legs and crawler limbs have very different proportions.
- Presets are written for specific rigs; other rigs need manual mapping or a new preset (see `PRESETS` in `__init__.py`).
- Results were checked numerically (poses, ground contact, cleanup); always look at the result on your own model.

## Licenses and credits

- The add-on code is licensed under the **GPL-3.0-or-later** (see `LICENSE`).
- The Mesh2Motion code is MIT and its art assets (rigs, animations) are CC0; the human library is based on animations by
  [Quaternius](https://quaternius.com). Nothing from that library is bundled here, it is downloaded on request from
  <https://github.com/Mesh2Motion/mesh2motion-app>.
- Do not commit Mixamo animation files to this repository; Mixamo content is covered by Adobe's terms.
