"""Build the twisted solar-rail scene and render pose stills.

Usage:
  uv run python scripts/solar_rail/build.py --round 1
  uv run python scripts/solar_rail/build.py --round 2 --animate
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from blender_mcp import headless
from blender_mcp.config import get_settings

HERE = Path(__file__).resolve().parent
FRAMES = 192
POSES = (("start", 0.0), ("mid", 0.5), ("end", 1.0))
CAMERAS = ("CameraTrack", "CameraHero", "CameraSide", "CameraAxle")


def smoothstep(u: float) -> float:
    return u * u * (3.0 - 2.0 * u)


def inv_smoothstep(s: float) -> float:
    s = min(1.0, max(0.0, s))
    return 0.5 - math.sin(math.asin(1.0 - 2.0 * s) / 3.0)


def frame_for_distance(s: float, frames: int = FRAMES) -> int:
    u = inv_smoothstep(s)
    return int(round(1 + u * (frames - 1)))


def set_camera_code(name: str, frame: int) -> str:
    return f"""
cam = D.objects.get({name!r})
if cam is None:
    raise RuntimeError("missing camera " + {name!r})
C.scene.camera = cam
C.scene.frame_set({int(frame)})
result = {{"camera": cam.name, "frame": C.scene.frame_current}}
"""


def animate_code(path: str, camera: str, samples: int, width: int, height: int, step: int) -> str:
    return f"""
import os
scene = C.scene
cam = D.objects.get({camera!r})
if cam is None:
    raise RuntimeError("missing camera " + {camera!r})
scene.camera = cam
scene.frame_start = 1
scene.frame_end = {FRAMES}
scene.frame_step = {int(step)}
scene.render.resolution_x = {int(width)}
scene.render.resolution_y = {int(height)}
scene.render.resolution_percentage = 100
scene.render.fps = 24
for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        scene.render.engine = engine
        break
    except TypeError:
        continue
eevee = getattr(scene, "eevee", None)
if eevee is not None and hasattr(eevee, "taa_render_samples"):
    eevee.taa_render_samples = {int(samples)}
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
try:
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
except TypeError:
    pass
try:
    scene.render.ffmpeg.audio_codec = "NONE"
except TypeError:
    pass
os.makedirs(os.path.dirname({path!r}), exist_ok=True)
scene.render.filepath = {path!r}
scene.render.use_file_extension = True
bpy.ops.render.render(animation=True)
result = {{"filepath": scene.render.filepath, "frame_step": scene.frame_step}}
"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the twisted solar rail")
    parser.add_argument("--round", type=int, default=1, dest="round_n")
    parser.add_argument("--no-stills", action="store_true")
    parser.add_argument("--animate", action="store_true")
    parser.add_argument("--camera", default="CameraSide")
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--step", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=900.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    for s in (0.0, 0.25, 0.5, 0.75, 1.0):
        back = smoothstep(inv_smoothstep(s))
        if abs(back - s) > 1e-6:
            raise SystemExit(f"ease inverse failed for {s}: {back}")

    settings = get_settings()
    out = settings.output_dir / "solar_rail"
    renders = out / "renders"
    out.mkdir(parents=True, exist_ok=True)
    renders.mkdir(parents=True, exist_ok=True)
    blend = out / "solar_rail.blend"
    code = (HERE / "scene.py").read_text(encoding="utf-8")

    requests: list[dict] = [
        {"type": "execute", "code": code},
        {"type": "save_as", "path": str(blend), "compress": True},
    ]
    stills: list[tuple[str, str, Path]] = []
    if not args.no_stills:
        tag = f"r{args.round_n:02d}"
        for pose_name, distance in POSES:
            frame = frame_for_distance(distance)
            for camera in CAMERAS:
                path = renders / f"{tag}_{camera}_{pose_name}.png"
                stills.append((camera, pose_name, path))
                requests.append({"type": "execute", "code": set_camera_code(camera, frame)})
                requests.append(
                    {
                        "type": "render",
                        "path": str(path),
                        "engine": "EEVEE",
                        "samples": args.samples,
                        "resolution": [args.width, args.height],
                        "frame": frame,
                    }
                )

    print(f"Building {blend}")
    job = headless.run_job(settings, requests, timeout=args.timeout)
    if not job.ok:
        print(job.stdout[-4000:])
        for response in job.responses:
            if not response.get("ok"):
                print(response.get("error") or response)
        return 1

    scene_result = job.responses[0].get("result") or {}
    print("Scene:", scene_result)
    collisions = scene_result.get("collision_count", 0)
    if collisions:
        print(f"WARNING: {collisions} support samples intersect the wagon")

    if args.animate:
        movie = renders / f"r{args.round_n:02d}_drive"
        print(f"Rendering animation via {args.camera}")
        anim = headless.run_job(
            settings,
            [
                {
                    "type": "execute",
                    "code": animate_code(
                        str(movie),
                        args.camera,
                        args.samples,
                        args.width,
                        args.height,
                        args.step,
                    ),
                }
            ],
            open_blend=blend,
            timeout=max(args.timeout, 2400.0),
        )
        if not anim.ok:
            print(anim.stdout[-4000:])
            for response in anim.responses:
                if not response.get("ok"):
                    print(response.get("error") or response)
            return 1
        print("Animation:", anim.responses[-1].get("result"))

    print("Stills:")
    for camera, pose_name, path in stills:
        print(f"  {camera} {pose_name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
