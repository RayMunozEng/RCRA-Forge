"""Render one installed model through Viewport3D and report fur GPU state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--hashes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--model", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--lod", type=int, default=0)
    parser.add_argument("--delay-ms", type=int, default=2500)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--converge-samples", type=int, default=32)
    parser.add_argument("--disable-hdr", action="store_true")
    parser.add_argument("--disable-fur", action="store_true")
    parser.add_argument("--disable-fur-contact", action="store_true")
    parser.add_argument("--enable-fur-contact", action="store_true")
    parser.add_argument("--disable-fur-denoise", action="store_true")
    parser.add_argument("--fur-wetness", type=float, default=0.0)
    parser.add_argument("--fur-wind-strength", type=float, default=0.0)
    parser.add_argument(
        "--fur-wind-vector", type=float, nargs=3, default=(1.0, 0.0, 0.0),
    )
    parser.add_argument("--fur-wind-object-phase", type=float, default=0.0)
    parser.add_argument("--fur-wind-time", type=float)
    parser.add_argument("--fur-environment", type=lambda value: int(value, 0))
    parser.add_argument("--fur-environment-dds-dir", type=Path)
    parser.add_argument("--fur-environment-cube", type=int)
    parser.add_argument("--fur-brdf-dds", type=Path)
    parser.add_argument("--base-shell-only", action="store_true")
    parser.add_argument("--fur-reverse-layer", type=int)
    parser.add_argument("--cull-backfaces", action="store_true")
    parser.add_argument("--uniform-unlit-fur", action="store_true")
    parser.add_argument("--albedo-unlit-fur", action="store_true")
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--yaw", type=float)
    parser.add_argument("--pitch", type=float)
    parser.add_argument("--distance-scale", type=float, default=1.0)
    args = parser.parse_args()

    forge_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(forge_root))

    from PyQt6.QtCore import QTimer, Qt
    from PyQt6.QtWidgets import QApplication
    from OpenGL.GL import (
        GL_BACK, GL_CULL_FACE, GL_RENDERER, GL_VENDOR, GL_VERSION,
        glCullFace, glEnable, glFinish, glGetString,
    )
    import numpy as np

    from core.archive import TocParser
    from core.asset_loader import load_asset, load_model_textures
    from core.hashes import HashLookup
    from core.mesh import mesh_to_numpy
    from core.texture import TextureParser
    from ui.viewport import (
        Viewport3D,
        _is_authored_wool,
        _perspective,
        _perspective_clip_planes,
    )
    if args.uniform_unlit_fur or args.albedo_unlit_fur:
        import ui.viewport as viewport_module
        shading_start = viewport_module.FUR_SHELL_FRAG_SRC.index(
            "    float key = max(dot(normal, normalize(uLightDir)), 0.0);"
        )
        shading_end = viewport_module.FUR_SHELL_FRAG_SRC.index(
            "    // Recovered retail behavior: opaque stochastic coverage.",
            shading_start,
        )
        debug_color = "albedo.rgb" if args.albedo_unlit_fur else "vec3(0.5)"
        viewport_module.FUR_SHELL_FRAG_SRC = (
            viewport_module.FUR_SHELL_FRAG_SRC[:shading_start]
            + f"    vec3 color = {debug_color};\n"
            + viewport_module.FUR_SHELL_FRAG_SRC[shading_end:]
        )

    toc = TocParser(str(args.game_root / "toc"))
    toc.parse()
    lookup = HashLookup()
    lookup.load(str(args.hashes))
    entry = toc.find_entry(args.model)
    if entry is None:
        raise RuntimeError(f"Model {args.model:016X} is absent from the installed TOC")
    result = load_asset(entry, toc, lookup)
    if result.model is None:
        raise RuntimeError(result.error or "Asset did not parse as a model")
    textures = load_model_textures(result.model, entry, toc, lookup)

    app = QApplication([sys.argv[0]])
    viewport = Viewport3D()
    environment_label = None
    if args.fur_environment is not None or args.fur_environment_dds_dir is not None:
        if args.fur_brdf_dds is None:
            raise RuntimeError("Hair environment input requires --fur-brdf-dds")
        if args.fur_environment is not None and args.fur_environment_dds_dir is not None:
            raise RuntimeError("Choose an installed or captured Hair environment, not both")
        if args.fur_environment_dds_dir is not None:
            if args.fur_environment_cube is None:
                raise RuntimeError("--fur-environment-dds-dir requires --fur-environment-cube")
            import imagecodecs
            import numpy as np

            cube_mips = []
            for face in range(6):
                levels = []
                for mip in range(6):
                    path = args.fur_environment_dds_dir / (
                        f"g_EnvProbeArray-cube{args.fur_environment_cube}-"
                        f"face{face}-mip{mip}.dds"
                    )
                    dds_cube = path.read_bytes()
                    width = struct.unpack_from("<I", dds_cube, 16)[0]
                    height = struct.unpack_from("<I", dds_cube, 12)[0]
                    dxgi_format = struct.unpack_from("<I", dds_cube, 128)[0]
                    if dds_cube[:4] != b"DDS " or dxgi_format != 95:
                        raise RuntimeError(f"Captured probe is not BC6U DX10 DDS: {path}")
                    decoded = imagecodecs.bcn_decode(
                        dds_cube[148:], format=6, shape=(height, width, 3),
                    )
                    levels.append((
                        width, height,
                        np.asarray(decoded, dtype=np.float16).tobytes(),
                    ))
                cube_mips.append(levels)
            environment_label = f"capture-cube-{args.fur_environment_cube}"
        else:
            environment_label = f"{args.fur_environment:016X}"
            environment_entry = toc.find_entry(args.fur_environment)
            if environment_entry is None:
                raise RuntimeError(
                    f"Environment {args.fur_environment:016X} is absent from the TOC"
                )
            environment = TextureParser(
                toc.extract_asset(environment_entry)
            ).parse()
            cube_mips = environment.decoded_cube_mips_rgb_half()
            print(
                f"[fur-env] parsed fmt={environment.fmt:#x} "
                f"planes={environment.planes} faces={len(cube_mips)}",
                flush=True,
            )
            if not cube_mips:
                raise RuntimeError("Environment asset is not a decodable BC6 cube")
        dds = args.fur_brdf_dds.read_bytes()
        if dds[:4] != b"DDS " or dds[84:88] != b"DX10":
            raise RuntimeError("Hair BRDF lookup is not a DX10 DDS")
        brdf_width = struct.unpack_from("<I", dds, 16)[0]
        brdf_height = struct.unpack_from("<I", dds, 12)[0]
        dxgi_format = struct.unpack_from("<I", dds, 128)[0]
        if dxgi_format != 10:
            raise RuntimeError(
                f"Hair BRDF lookup format is DXGI {dxgi_format}, expected 10"
            )
        rgba_half = dds[148:]
        brdf_rg_half = b"".join(
            rgba_half[offset:offset + 4]
            for offset in range(0, len(rgba_half), 8)
        )
        viewport.set_fur_environment(
            cube_mips, brdf_rg_half, (brdf_width, brdf_height),
        )
        print(
            f"[fur-env] queued source={environment_label} "
            f"cube_mips={len(cube_mips[0])} "
            f"brdf={brdf_width}x{brdf_height}",
            flush=True,
        )
    if args.disable_fur_contact:
        viewport._fur_contact_enabled = False
    elif args.enable_fur_contact:
        viewport._fur_contact_enabled = True
    viewport._fur_denoise_enabled = not args.disable_fur_denoise
    viewport.set_fur_weather(
        wetness=args.fur_wetness,
        wind_strength=args.fur_wind_strength,
        wind_vector=args.fur_wind_vector,
        wind_object_phase=args.fur_wind_object_phase,
        wind_time=args.fur_wind_time,
    )
    # Automated evidence captures must not interrupt the desktop session.
    # Keeping a native widget alive is required for QOpenGLWidget, but an
    # off-desktop, non-activating window renders the same framebuffer without
    # surfacing over the user's work.
    viewport.setWindowFlags(
        Qt.WindowType.Tool
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowDoesNotAcceptFocus
    )
    viewport.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    viewport.move(-10000, -10000)
    if args.disable_hdr:
        viewport._bloom_supported = False
    viewport.resize(args.width, args.height)
    viewport.show()
    viewport.load_mesh(result.model)
    # The model is still pending its first GL upload, so select the requested
    # LOD before paintGL consumes it rather than calling the interactive setter.
    viewport._active_lod = args.lod
    viewport.load_textures(textures)
    if args.disable_fur:
        viewport.set_show_fur(False)

    def finish() -> None:
        viewport.makeCurrent()
        # Upload/frame the model first, then apply an optional reproducible
        # camera override to the bounds-derived camera distance.
        viewport.paintGL()
        if args.base_shell_only:
            for gpu_mesh in viewport._gpu_meshes:
                if gpu_mesh.fur_control_tex_id > 0:
                    gpu_mesh.fur_layer_count = 1
        viewport._fur_debug_reverse_layer = args.fur_reverse_layer
        if args.cull_backfaces:
            glEnable(GL_CULL_FACE)
            glCullFace(GL_BACK)
        if args.yaw is not None:
            viewport.camera.yaw = args.yaw
        if args.pitch is not None:
            viewport.camera.pitch = args.pitch
        viewport.camera.dist *= args.distance_scale
        frame_times_ms = []
        for _ in range(max(1, args.samples)):
            started = time.perf_counter()
            viewport.paintGL()
            glFinish()
            frame_times_ms.append((time.perf_counter() - started) * 1000.0)
        # Camera overrides reset temporal history.  Let the same 32-sample
        # stationary resolve used by the live viewport finish before capture;
        # otherwise the smoke image records only its first noisy phases.
        for _ in range(max(0, args.converge_samples)):
            if viewport._temporal_sample_count >= args.converge_samples:
                break
            viewport.paintGL()
            glFinish()
        image = viewport.grabFramebuffer()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if image.isNull() or not image.save(str(args.output)):
            raise RuntimeError(f"Could not save framebuffer to {args.output}")

        fur_meshes = [
            mesh for mesh in viewport._gpu_meshes
            if mesh.fur_control_tex_id > 0 and not mesh.is_composite_shell
        ]
        # Sheep is materially distinct wool, but the executable still sends it
        # through the same fur-shell pass.  Do not exclude it from rendered
        # shell counts merely because its density/offset identify that regime.
        shell_meshes = list(fur_meshes)
        composite_shell_meshes = [
            mesh for mesh in viewport._gpu_meshes if mesh.is_composite_shell
        ]
        triangle_count = sum(mesh.index_count // 3 for mesh in fur_meshes)
        fur_material_indices = {mesh.material_index for mesh in fur_meshes}
        length_by_material = {
            mesh.material_index: mesh.fur_length for mesh in fur_meshes
        }
        near, far = _perspective_clip_planes(
            viewport.camera, viewport._aabb_min, viewport._aabb_max,
        )
        projection = _perspective(
            60.0, args.width / max(args.height, 1), near, far,
        )
        mvp = projection @ viewport.camera.view_matrix()
        physical_size = np.asarray(viewport._framebuffer_size(), dtype=np.float64)
        triangle_areas = []
        projected_lengths = []
        for source_mesh in result.model.meshes:
            if source_mesh.look_index != 0 or source_mesh.lod_level != args.lod:
                continue
            if source_mesh.material_index not in fur_material_indices:
                continue
            positions, normals, _uvs, indices = mesh_to_numpy(result.model, source_mesh)
            triangles = indices.reshape((-1, 3))
            edges_a = positions[triangles[:, 1]] - positions[triangles[:, 0]]
            edges_b = positions[triangles[:, 2]] - positions[triangles[:, 0]]
            areas = np.linalg.norm(np.cross(edges_a, edges_b), axis=1) * 0.5
            triangle_areas.extend(areas.tolist())
            centers = positions[triangles].mean(axis=1)
            average_normals = normals[triangles].mean(axis=1)
            normal_lengths = np.linalg.norm(average_normals, axis=1, keepdims=True)
            average_normals /= np.maximum(normal_lengths, 1e-8)
            envelopes = centers + average_normals * length_by_material[
                source_mesh.material_index
            ]
            center_h = np.concatenate(
                [centers, np.ones((len(centers), 1), dtype=np.float32)], axis=1,
            )
            envelope_h = np.concatenate(
                [envelopes, np.ones((len(envelopes), 1), dtype=np.float32)], axis=1,
            )
            center_clip = center_h @ mvp.T
            envelope_clip = envelope_h @ mvp.T
            ndc_delta = (
                envelope_clip[:, :2] / envelope_clip[:, 3:4]
                - center_clip[:, :2] / center_clip[:, 3:4]
            )
            pixel_lengths = np.linalg.norm(
                ndc_delta * physical_size * 0.5, axis=1,
            )
            projected_lengths.extend(pixel_lengths.tolist())
        area_values = np.asarray(triangle_areas, dtype=np.float64)
        projected_values = np.asarray(projected_lengths, dtype=np.float64)
        def quantiles_or_empty(values, probabilities):
            return np.quantile(values, probabilities).tolist() \
                if values.size else []

        report = {
            "model": f"{args.model:016X}",
            "path": lookup.full_path(args.model),
            "lod": args.lod,
            "viewport_size": [args.width, args.height],
            "camera": {
                "yaw": viewport.camera.yaw,
                "pitch": viewport.camera.pitch,
                "distance": viewport.camera.dist,
                "target": viewport.camera.target.tolist(),
            },
            "fur_program": bool(viewport._fur_shader_prog),
            "fur_enabled": not args.disable_fur,
            "base_shell_only": args.base_shell_only,
            "cull_backfaces": args.cull_backfaces,
            "uniform_unlit_fur": args.uniform_unlit_fur,
            "albedo_unlit_fur": args.albedo_unlit_fur,
            "fur_renderer": "recovered_shells_with_material_specific_surfaces",
            "vertex_tangent_frame": "retail_packed_authored_tangent_and_handedness",
            "fur_layer_volume": (
                "recovered_procedural_128x128x32_exact_integer_mips"
            ),
            "fur_coverage_resolve": "32_sample_jittered_temporal_stochastic_opaque",
            "temporal_sample_count": viewport._temporal_sample_count,
            "fur_contact_shadow": (
                "control_blue_custom_depth_four_tap_hair_contact"
                if viewport._fur_contact_enabled
                else "disabled_control"
            ),
            "fur_screen_space_shadow": viewport._fur_contact_enabled,
            "fur_hair_denoise": (
                "captured_three_step_tangent_depth_mask_gather"
                if viewport._fur_denoise_enabled else "disabled_control"
            ),
            "fur_environment": {
                "asset": environment_label,
                "brdf_dds": (
                    str(args.fur_brdf_dds) if args.fur_brdf_dds else None
                ),
                "gpu_ready": (
                    viewport._fur_environment_texture > 0
                    and viewport._fur_brdf_texture > 0
                ),
            },
            "fur_wetness": viewport._fur_wetness,
            "fur_wind": {
                "strength": viewport._fur_wind_strength,
                "vector": viewport._fur_wind_vector.tolist(),
                "time": viewport._fur_wind_time_override,
                "object_phase": viewport._fur_wind_object_phase,
                "field": "captured_64_vector_cubic_procedural",
            },
            "fur_weighted_oit": False,
            "fur_material_count": len({mesh.material_index for mesh in fur_meshes}),
            "fur_mesh_count": len(fur_meshes),
            "authored_wool_surface_mesh_count": sum(
                _is_authored_wool(
                    density=mesh.fur_density,
                    offset_scale=mesh.fur_offset_scale,
                )
                for mesh in fur_meshes
            ),
            "fur_triangle_count": triangle_count,
            "composite_shell_mesh_count": len(composite_shell_meshes),
            "composite_shell_triangle_count": sum(
                mesh.index_count // 3 for mesh in composite_shell_meshes
            ),
            "retail_authored_additional_shell_count": sum(
                max(0, int(mesh.fur_layer_count or 32) - 1)
                for mesh in shell_meshes
            ),
            "rendered_shell_triangle_count": sum(
                (mesh.index_count // 3)
                * max(1, int(mesh.fur_layer_count or 32))
                for mesh in shell_meshes
            ),
            "projected_fur_length_pixel_quantiles": quantiles_or_empty(
                projected_values, [0.0, 0.1, 0.5, 0.9, 1.0],
            ),
            "fur_surface_area": float(area_values.sum()),
            "triangle_area_quantiles": quantiles_or_empty(
                area_values, [0.0, 0.01, 0.25, 0.5, 0.75, 0.99, 1.0],
            ),
            "meshes": [
                {
                    "material_index": mesh.material_index,
                    "material_name": mesh.material_name,
                    "triangles": mesh.index_count // 3,
                    "control_texture": mesh.fur_control_tex_id,
                    "authored_length": mesh.fur_length,
                    "authored_density": mesh.fur_density,
                    "authored_offset_scale": mesh.fur_offset_scale,
                    "authored_layer_count": mesh.fur_layer_count,
                    "authored_lod_reduction": mesh.fur_lod_reduction,
                    "authored_gloss_scale": mesh.fur_gloss_scale,
                    "authored_specular_scale": mesh.fur_specular_scale,
                    "authored_transmittance_scale": mesh.fur_transmittance_scale,
                    "authored_wind_turbulence": mesh.fur_wind_turbulence,
                    "derived_wind_radius": mesh.fur_wind_radius,
                    "specular_texture": mesh.specular_tex_id,
                }
                for mesh in fur_meshes
            ],
            "opengl": {
                "vendor": (glGetString(GL_VENDOR) or b"").decode(errors="replace"),
                "renderer": (glGetString(GL_RENDERER) or b"").decode(errors="replace"),
                "version": (glGetString(GL_VERSION) or b"").decode(errors="replace"),
            },
            "synchronous_frame_time_ms": {
                "samples": frame_times_ms,
                "median": float(np.median(frame_times_ms)),
                "p95": float(np.percentile(frame_times_ms, 95)),
            },
            "screenshot": str(args.output),
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        viewport.doneCurrent()
        viewport.close()
        app.quit()

    QTimer.singleShot(max(100, args.delay_ms), finish)
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
