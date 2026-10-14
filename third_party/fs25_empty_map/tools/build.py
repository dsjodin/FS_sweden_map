"""
build.py - assemble a from-scratch FS25 starter map into out/<mod>/. Size via CLI:
  python tools/build.py 16    (default) -> FS25_Empty16x   (8192 m)
  python tools/build.py 4               -> FS25_Empty4x    (4096 m)
Everything scales from mapcfg.Cfg. Verifies every map-local file the i3d references exists.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mapcfg, gen_i3d, gen_data, gen_configs

SIZES = {"16": mapcfg.CFG16, "4": mapcfg.CFG4, "64": mapcfg.CFG64}


def build(cfg):
    out = os.path.abspath(os.path.join(HERE, "..", "out", cfg.mod))
    maps = os.path.join(out, "maps"); data = os.path.join(maps, "data")
    os.makedirs(data, exist_ok=True)
    local = gen_i3d.build(cfg, os.path.join(maps, cfg.i3d))
    gen_data.build(cfg, data)
    gen_configs.build(cfg, out, maps)
    missing = [f for f in local if not os.path.exists(os.path.join(maps, f.replace("/", os.sep)))]
    print(f"\nbuild {cfg.title} -> {out}")
    print("local files referenced by i3d:", len(local), "| MISSING:", missing or "none")
    return out


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "16"
    build(SIZES[key])
