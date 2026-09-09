"""Render one installed model through Viewport3D and report fur GPU state."""

from __future__ import annotations

import argparse
import hashlib
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
    parser.add_argument("--animation-frames", type=int, default=0,
                        help="Save a bounded wind sequence after convergence (maximum 96 frames)")
    parser.add_argument("--animation-fps", type=int, default=12)
    parser.add_argument("--disable-hdr", action="store_true")
    parser.add_argument("--verify-deferred-targets", action="store_true")
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
    parser.add_argument("--fur-wind-time-step", type=float, default=0.0)
    parser.add_argument("--fur-environment", type=lambda value: int(value, 0))
    parser.add_argument(
        "--disable-fur-environment", action="store_true",
        help="Diagnostic only: omit the default Hair probe and BRDF lookup",
    )
    parser.add_argument("--fur-environment-dds-dir", type=Path)
    parser.add_argument("--fur-environment-cube", type=int)
    parser.add_argument("--fur-brdf-dds", type=Path)
    parser.add_argument("--fur-scene-bundle", type=Path,
                        help="Explicit scene resources and tile lookup for this model placement and camera")
    parser.add_argument("--preview-light-direction", type=float, nargs=3,
                        help="Controlled world-space key direction for isolated asset comparisons")
    parser.add_argument("--base-shell-only", action="store_true")
    parser.add_argument("--fur-reverse-layer", type=int)
    parser.add_argument("--cull-backfaces", action="store_true")
    parser.add_argument("--uniform-unlit-fur", action="store_true")
    parser.add_argument("--albedo-unlit-fur", action="store_true")
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--orthographic", action="store_true")
    parser.add_argument("--yaw", type=float)
    parser.add_argument("--camera-yaw-step", type=float, default=0.0)
    parser.add_argument("--temporal-nonopaque-response", type=float)
    parser.add_argument("--temporal-conditional-floor", action="store_true")
    parser.add_argument("--temporal-hdr-reference", type=float)
    parser.add_argument("--pitch", type=float)
    parser.add_argument("--distance-scale", type=float, default=1.0)
    args = parser.parse_args()
    if not 0 <= args.animation_frames <= 96 or not 1 <= args.animation_fps <= 24:
        parser.error("Animation requires 0..96 frames and 1..24 FPS")
    if args.animation_frames and (args.fur_wind_time is None or args.fur_wind_time_step != 0):
        parser.error("Animation requires a fixed --fur-wind-time and no --fur-wind-time-step")
    if args.preview_light_direction is not None and args.fur_scene_bundle is not None:
        parser.error("Preview light direction cannot override a scene bundle")
    if args.disable_fur_environment and (
        args.fur_environment is not None or args.fur_environment_dds_dir is not None
        or args.fur_brdf_dds is not None
    ):
        parser.error("--disable-fur-environment cannot be combined with environment inputs")
    if args.fur_environment is not None and args.fur_environment_dds_dir is not None:
        parser.error("Choose an installed or captured Hair environment, not both")
    if args.fur_environment_cube is not None and args.fur_environment_dds_dir is None:
        parser.error("--fur-environment-cube requires --fur-environment-dds-dir")
    if args.fur_wind_time_step != 0.0 and args.fur_wind_time is None:
        parser.error("--fur-wind-time-step requires --fur-wind-time")

    forge_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(forge_root))

    from PyQt6.QtCore import QTimer, Qt
    from PyQt6.QtWidgets import QApplication
    from OpenGL.GL import (
        GL_BACK, GL_CULL_FACE, GL_RENDERER, GL_VENDOR, GL_VERSION,
        GL_TEXTURE_2D, GL_TEXTURE_BINDING_2D, GL_TEXTURE_INTERNAL_FORMAT,
        GL_TEXTURE_WIDTH, GL_TEXTURE_HEIGHT,
        glBindTexture, glCullFace, glEnable, glFinish, glGetIntegerv,
        glGetString, glGetTexLevelParameteriv, glGetTexParameterfv,
    )
    import numpy as np

    from core.archive import TocParser
    from core.asset_loader import load_asset, load_fur_environment, load_model_textures
    from core.fur_resources import (
        DEFAULT_HAIR_ENVIRONMENT_ASSET_ID, default_hair_brdf_rg_half,
    )
    from core.hashes import HashLookup
    from core.mesh import mesh_to_numpy
    from core.texture import TextureParser
    from core.cube_texture import CubeMipChain
    from ui.viewport import (
        Viewport3D,
        _is_authored_wool,
        _perspective,
        _perspective_clip_planes,
    )
    if args.uniform_unlit_fur or args.albedo_unlit_fur:
        import ui.viewport as viewport_module
        shared = viewport_module._HAIR_PREVIEW_LIGHTING
        shading_start = shared.index(
            "    // Unit-radiance direct-light evaluation"
        )
        debug_color = "albedo.rgb" if args.albedo_unlit_fur else "vec3(0.5)"
        debug_shared = (
            shared[:shading_start]
            + f"    indirectColor = {debug_color};\n    directColor = vec3(0.0);\n}}\n"
        )
        for name in ('FUR_SHELL_FRAG_SRC', 'FUR_LIGHTING_FRAG', 'FUR_SCENE_LIGHTING_FRAG'):
            setattr(viewport_module, name, getattr(viewport_module, name).replace(shared, debug_shared))

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
    environment_source = "disabled_control" if args.disable_fur_environment else None
    environment_layout = None
    cube_mips = []
    brdf_rg_half = default_hair_brdf_rg_half()
    brdf_width, brdf_height = 64, 64
    if args.fur_environment is not None or args.fur_environment_dds_dir is not None:
        if args.fur_environment_dds_dir is not None:
            if args.fur_environment_cube is None:
                raise RuntimeError("--fur-environment-dds-dir requires --fur-environment-cube")
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
                    levels.append((width, height, dds_cube[148:]))
                cube_mips.append(levels)
            cube_mips = CubeMipChain(cube_mips, 'bc6u')
            environment_label = f"capture-cube-{args.fur_environment_cube}"
            environment_source = "capture_override"
            environment_layout = "captured_face_mips"
        else:
            environment_label = f"{args.fur_environment:016X}"
            environment_source = "installed_override"
            environment_entry = toc.find_entry(args.fur_environment)
            if environment_entry is None:
                raise RuntimeError(
                    f"Environment {args.fur_environment:016X} is absent from the TOC"
                )
            environment = TextureParser(
                toc.extract_asset(environment_entry)
            ).parse()
            environment_layout = (
                "packed_probe_atlas_1024x512"
                if environment.is_packed_probe_atlas else "face_major_cube"
            )
            if environment.fmt != 0x5F:
                raise RuntimeError('Environment override is not BC6U')
            cube_mips = CubeMipChain(environment.compressed_cube_mips(), 'bc6u')
            print(
                f"[fur-env] parsed fmt={environment.fmt:#x} "
                f"planes={environment.planes} faces={len(cube_mips)}",
                flush=True,
            )
            if not cube_mips:
                raise RuntimeError("Environment asset is not a decodable BC6 cube")
    elif not args.disable_fur_environment:
        environment = load_fur_environment(textures, toc)
        if environment is not None:
            cube_mips, brdf_rg_half, (brdf_width, brdf_height) = environment
            environment_label = f"{DEFAULT_HAIR_ENVIRONMENT_ASSET_ID:016X}"
            environment_source = "installed_default"
            environment_layout = "face_major_cube"
    if args.fur_brdf_dds is not None:
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
    if cube_mips:
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
    if args.preview_light_direction is not None:
        viewport.set_preview_light_direction(args.preview_light_direction)
    viewport.set_temporal_aa_state(
        nonopaque_response=args.temporal_nonopaque_response,
        conditional_floor=args.temporal_conditional_floor,
        hdr_reference=args.temporal_hdr_reference,
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
    viewport._ortho = bool(args.orthographic)
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
        if args.fur_scene_bundle is not None:
            with np.load(args.fur_scene_bundle, allow_pickle=False) as scene_bundle:
                viewport.set_fur_scene_lighting(scene_bundle)
            viewport.makeCurrent()
        frame_times_ms = []
        current_wind_time = args.fur_wind_time
        camera_yaw_start = float(viewport.camera.yaw)
        temporal_samples_before_motion = int(viewport._temporal_sample_count)
        camera_motion_frames = 0

        def advance_wind_time() -> None:
            nonlocal current_wind_time
            if current_wind_time is None or args.fur_wind_time_step == 0.0:
                return
            current_wind_time += args.fur_wind_time_step
            viewport._fur_wind_time_override = current_wind_time

        def advance_camera() -> None:
            nonlocal camera_motion_frames
            if args.camera_yaw_step == 0.0:
                return
            viewport.camera.yaw += args.camera_yaw_step
            camera_motion_frames += 1

        for _ in range(max(1, args.samples)):
            advance_wind_time()
            advance_camera()
            started = time.perf_counter()
            viewport.paintGL()
            glFinish()
            frame_times_ms.append((time.perf_counter() - started) * 1000.0)
        # Continue the same temporal history through stationary or deterministic
        # camera-motion frames until the requested evidence age is reached.
        for _ in range(max(0, args.converge_samples)):
            if viewport._temporal_sample_count >= args.converge_samples:
                break
            advance_wind_time()
            advance_camera()
            viewport.paintGL()
            glFinish()
        image = viewport.grabFramebuffer()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if image.isNull() or not image.save(str(args.output)):
            raise RuntimeError(f"Could not save framebuffer to {args.output}")

        animation_report = None
        if args.animation_frames:
            from PIL import Image
            import io
            from PyQt6.QtCore import QBuffer, QIODevice
            sequence = []
            times = []
            for frame in range(args.animation_frames):
                current_wind_time = args.fur_wind_time + frame / args.animation_fps
                viewport._fur_wind_time_override = current_wind_time
                # grabFramebuffer renders the current state; retain history
                # between samples rather than reconverging each pose.
                captured = viewport.grabFramebuffer()
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                if captured.isNull() or not captured.save(buffer, 'PNG'):
                    raise RuntimeError('Could not capture wind animation frame')
                sequence.append(Image.open(io.BytesIO(bytes(buffer.data()))).convert('RGB'))
                times.append(current_wind_time)
            animation_path = args.output.with_suffix('.gif')
            sequence[0].save(animation_path, save_all=True, append_images=sequence[1:],
                             duration=round(1000 / args.animation_fps), loop=0, disposal=2)
            changes = [float(np.abs(np.asarray(frame, dtype=float) -
                        np.asarray(sequence[0], dtype=float)).mean()) for frame in sequence]
            animation_report = {'file': str(animation_path), 'frames': len(sequence),
                                'fps': args.animation_fps, 'shader_times': times,
                                'mean_rgb_change_from_first': changes,
                                'scope': 'Wind deformation, not skeletal animation or native sequence parity'}

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
        texture_formats = {}
        texture_anisotropy = {}
        previous_texture = int(glGetIntegerv(GL_TEXTURE_BINDING_2D))
        for mesh in fur_meshes:
            formats = {}
            anisotropy = {}
            for role, attribute in (
                ('base', 'texture_id'), ('fur_control', 'fur_control_tex_id'),
                ('specular_color', 'specular_tex_id'),
            ):
                texture_id = getattr(mesh, attribute, 0)
                if texture_id:
                    glBindTexture(GL_TEXTURE_2D, texture_id)
                    formats[role] = int(glGetTexLevelParameteriv(
                        GL_TEXTURE_2D, 0, GL_TEXTURE_INTERNAL_FORMAT,
                    ))
                    anisotropy[role] = (
                        float(glGetTexParameterfv(GL_TEXTURE_2D, 0x84FE))
                        if viewport._max_texture_anisotropy > 1.0 else 1.0
                    )
            texture_formats[mesh.material_index] = formats
            texture_anisotropy[mesh.material_index] = anisotropy
        glBindTexture(GL_TEXTURE_2D, previous_texture)
        motion_blur_targets = []
        for texture in (
            viewport._motion_blur_depth_velocity_texture,
            viewport._motion_blur_half_velocity_texture,
            *viewport._motion_blur_neighborhood_textures,
            *viewport._motion_blur_scatter_textures,
        ):
            if not texture:
                continue
            glBindTexture(GL_TEXTURE_2D, texture)
            motion_blur_targets.append({
                "texture": int(texture),
                "width": int(glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_WIDTH)),
                "height": int(glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_HEIGHT)),
                "internal_format": int(glGetTexLevelParameteriv(
                    GL_TEXTURE_2D, 0, GL_TEXTURE_INTERNAL_FORMAT,
                )),
            })
        temporal_disocclusion_targets = []
        for texture in (
            *viewport._temporal_disocclusion_textures,
            *viewport._temporal_depth_textures,
        ):
            if not texture:
                continue
            glBindTexture(GL_TEXTURE_2D, texture)
            temporal_disocclusion_targets.append({
                "texture": int(texture),
                "width": int(glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_WIDTH)),
                "height": int(glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_HEIGHT)),
                "internal_format": int(glGetTexLevelParameteriv(
                    GL_TEXTURE_2D, 0, GL_TEXTURE_INTERNAL_FORMAT,
                )),
            })
        temporal_alpha_targets = []
        for texture in (
            *viewport._temporal_linear_depth_textures,
            *viewport._temporal_half_textures,
            viewport._temporal_alpha_mask_texture,
        ):
            if not texture:
                continue
            glBindTexture(GL_TEXTURE_2D, texture)
            temporal_alpha_targets.append({
                "texture": int(texture),
                "width": int(glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_WIDTH)),
                "height": int(glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_HEIGHT)),
                "internal_format": int(glGetTexLevelParameteriv(
                    GL_TEXTURE_2D, 0, GL_TEXTURE_INTERNAL_FORMAT,
                )),
            })
        glBindTexture(GL_TEXTURE_2D, previous_texture)
        deferred_checks = None
        motion_blur_checks = None
        temporal_disocclusion_checks = None
        temporal_alpha_checks = None
        temporal_motion_stencil_checks = None
        if args.verify_deferred_targets:
            if not viewport._fur_deferred_active:
                raise RuntimeError("Deferred target verification requires active deferred fur")
            import ctypes
            from OpenGL.GL import (
                GL_RED, GL_RED_INTEGER, GL_RG, GL_RGBA, GL_RGBA_INTEGER,
                GL_FLOAT, GL_UNSIGNED_BYTE, GL_UNSIGNED_SHORT,
                GL_FRAMEBUFFER, GL_FRAMEBUFFER_BINDING, GL_DEPTH_ATTACHMENT,
                GL_COLOR_ATTACHMENT4, GL_COLOR_ATTACHMENT5,
                GL_FRAMEBUFFER_ATTACHMENT_OBJECT_NAME,
                glBindFramebuffer, glGetFramebufferAttachmentParameteriv,
            )
            from OpenGL.raw.GL.VERSION.GL_1_1 import glGetTexImage
            physical_w, physical_h = viewport._framebuffer_size()

            def read_target(texture, dtype=np.float32, integer=False):
                values = np.empty((physical_h, physical_w, 4), dtype=dtype)
                glBindTexture(GL_TEXTURE_2D, texture)
                glGetTexImage(GL_TEXTURE_2D, 0, GL_RGBA_INTEGER if integer else GL_RGBA,
                              GL_UNSIGNED_SHORT if integer else GL_FLOAT,
                              ctypes.c_void_p(values.ctypes.data))
                return values

            def read_red_target(texture, size):
                width, height = size
                values = np.empty((height, width), dtype=np.float32)
                glBindTexture(GL_TEXTURE_2D, texture)
                glGetTexImage(
                    GL_TEXTURE_2D, 0, GL_RED, GL_FLOAT,
                    ctypes.c_void_p(values.ctypes.data),
                )
                return values

            def read_rg_target(texture, size):
                width, height = size
                values = np.empty((height, width, 2), dtype=np.float32)
                glBindTexture(GL_TEXTURE_2D, texture)
                glGetTexImage(
                    GL_TEXTURE_2D, 0, GL_RG, GL_FLOAT,
                    ctypes.c_void_p(values.ctypes.data),
                )
                return values

            def read_red_uint8_target(texture, size):
                width, height = size
                values = np.empty((height, width), dtype=np.uint8)
                glBindTexture(GL_TEXTURE_2D, texture)
                glGetTexImage(
                    GL_TEXTURE_2D, 0, GL_RED_INTEGER, GL_UNSIGNED_BYTE,
                    ctypes.c_void_p(values.ctypes.data),
                )
                return values

            packed_material = read_target(viewport._fur_material_textures[0], np.uint16, True)
            mask = (((packed_material[:, :, 0] >> 13) & 7) == 3) & ((packed_material[:, :, 0] & 4096) == 0)
            normal_mask = read_target(viewport._fur_normal_texture)
            assert np.array_equal(normal_mask[:, :, 3], mask.astype(np.float32))
            scene = read_target(viewport._hdr_color_buffers[0])
            resolved = read_target(viewport._fur_contact_texture)
            assert np.array_equal(scene[~mask], resolved[~mask])
            assert np.isfinite(resolved[mask]).all() and mask.any()
            stored_checks = {}
            for stage, values in (("lighting", resolved), ("denoise", read_target(viewport._fur_denoise_texture))):
                if stage == "denoise" and not viewport._fur_denoise_enabled:
                    continue
                assert np.array_equal(scene[~mask], values[~mask]), stage
                rgb = values[mask, :3]
                assert np.isfinite(rgb).all() and np.all(rgb >= 0), stage
                assert np.all(rgb <= [65024, 65024, 64512]), stage
                # Check the native representable grid independently of the GLSL
                # bit-mask implementation, including the subnormal range.
                exponents = np.maximum(np.frexp(rgb)[1] - 1, -14)
                step = np.ldexp(np.ones_like(rgb), exponents - [6, 6, 5])
                assert np.array_equal(np.floor(rgb / step) * step, rgb), stage
                stored_checks[stage] = int(mask.sum())
            target_formats = []
            for texture in viewport._fur_material_textures:
                glBindTexture(GL_TEXTURE_2D, texture)
                target_formats.append(int(glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_INTERNAL_FORMAT)))
            assert target_formats == [0x8D76, 0x8C43, 0x822E, 0x8236, 0x822F]
            previous_fbo = int(glGetIntegerv(GL_FRAMEBUFFER_BINDING))
            attachments = []
            for fbo in (viewport._hdr_fbo, viewport._fur_material_fbo):
                glBindFramebuffer(GL_FRAMEBUFFER, fbo)
                attachments.append(int(glGetFramebufferAttachmentParameteriv(
                    GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_FRAMEBUFFER_ATTACHMENT_OBJECT_NAME)))
            assert attachments[0] == attachments[1] != 0
            shared_stencil_attachments = []
            for fbo, attachment in (
                (viewport._hdr_fbo, GL_COLOR_ATTACHMENT4),
                (viewport._fur_material_fbo, GL_COLOR_ATTACHMENT5),
            ):
                glBindFramebuffer(GL_FRAMEBUFFER, fbo)
                shared_stencil_attachments.append(int(
                    glGetFramebufferAttachmentParameteriv(
                        GL_FRAMEBUFFER, attachment,
                        GL_FRAMEBUFFER_ATTACHMENT_OBJECT_NAME,
                    )
                ))
            assert shared_stencil_attachments == [
                viewport._scene_stencil_texture,
                viewport._scene_stencil_texture,
            ]
            glBindFramebuffer(GL_FRAMEBUFFER, previous_fbo)
            glBindTexture(GL_TEXTURE_2D, previous_texture)
            deferred_checks = {
                "native_target_formats": target_formats,
                "hair_mask_exact": int(mask.sum()),
                "non_hair_color_preserved": int((~mask).sum()),
                "fur_color_finite": True,
                "native_color_precision_pixels": stored_checks,
                "shared_opaque_depth_attachment": True,
                "shared_temporal_stencil_attachment": True,
            }
            scene_velocity = read_rg_target(
                viewport._scene_velocity_texture, viewport._bloom_size,
            )
            assert np.isfinite(scene_velocity).all()
            if args.camera_yaw_step != 0.0:
                assert np.count_nonzero(scene_velocity) > 0
            stencil = read_red_uint8_target(
                viewport._scene_stencil_texture, viewport._bloom_size,
            )
            stencil_values, stencil_counts = np.unique(
                stencil, return_counts=True,
            )
            assert set(stencil_values.tolist()).issubset({0, 128})
            if not args.disable_fur:
                assert 128 in stencil_values
            temporal_motion_stencil_checks = {
                "opaque_velocity_finite": True,
                "opaque_velocity_minimum": scene_velocity.min(axis=(0, 1)).tolist(),
                "opaque_velocity_maximum": scene_velocity.max(axis=(0, 1)).tolist(),
                "opaque_velocity_max_abs": np.max(
                    np.abs(scene_velocity), axis=(0, 1),
                ).tolist(),
                "opaque_velocity_nonzero_pixels": np.count_nonzero(
                    scene_velocity, axis=(0, 1),
                ).tolist(),
                "stencil_values": {
                    str(int(value)): int(count)
                    for value, count in zip(stencil_values, stencil_counts)
                },
                "stencil_bit_128_exact": True,
            }
            scatter_targets = []
            for index, texture in enumerate(viewport._motion_blur_scatter_textures):
                values = read_red_target(texture, viewport._motion_blur_sizes[0])
                assert np.isfinite(values).all(), index
                assert np.all((values >= 0.0) & (values <= 1.0)), index
                scatter_targets.append({
                    "index": index,
                    "valid": bool(viewport._motion_blur_scatter_valid[index]),
                    "minimum": float(values.min()),
                    "maximum": float(values.max()),
                    "nonzero_pixels": int(np.count_nonzero(values)),
                    "pixel_count": int(values.size),
                })
            assert len(scatter_targets) == 2
            assert all(target["valid"] for target in scatter_targets)
            motion_intermediates = []
            for name, texture, size in (
                ("full_velocity", viewport._fur_material_textures[4], viewport._bloom_size),
                ("half_depth_velocity", viewport._motion_blur_depth_velocity_texture,
                 viewport._motion_blur_sizes[0]),
                ("half_velocity", viewport._motion_blur_half_velocity_texture,
                 viewport._motion_blur_sizes[0]),
                ("quarter_neighborhood", viewport._motion_blur_neighborhood_textures[0],
                 viewport._motion_blur_sizes[1]),
                ("sixteenth_neighborhood", viewport._motion_blur_neighborhood_textures[1],
                 viewport._motion_blur_sizes[2]),
                ("sixteenth_gathered", viewport._motion_blur_neighborhood_textures[2],
                 viewport._motion_blur_sizes[2]),
            ):
                values = read_rg_target(texture, size)
                assert np.isfinite(values).all(), name
                motion_intermediates.append({
                    "name": name,
                    "minimum": values.min(axis=(0, 1)).tolist(),
                    "maximum": values.max(axis=(0, 1)).tolist(),
                    "max_abs": np.max(np.abs(values), axis=(0, 1)).tolist(),
                    "nonzero_pixels": np.count_nonzero(values, axis=(0, 1)).tolist(),
                })
            motion_blur_checks = {
                "paired_r8_finite_normalized": True,
                "targets": scatter_targets,
                "intermediates": motion_intermediates,
            }
            disocclusion_readback = []
            depth_motion_readback = []
            for index, texture in enumerate(viewport._temporal_disocclusion_textures):
                values = read_rg_target(texture, viewport._bloom_size)
                assert np.isfinite(values).all(), index
                assert np.all((values >= 0.0) & (values <= 1.0)), index
                disocclusion_readback.append({
                    "index": index,
                    "valid": bool(viewport._temporal_disocclusion_valid[index]),
                    "minimum": values.min(axis=(0, 1)).tolist(),
                    "maximum": values.max(axis=(0, 1)).tolist(),
                    "nonzero_pixels": np.count_nonzero(values, axis=(0, 1)).tolist(),
                })
            for index, texture in enumerate(viewport._temporal_depth_textures):
                values = read_rg_target(texture, viewport._bloom_size)
                assert np.isfinite(values).all(), index
                assert np.all(values >= 0.0), index
                depth_motion_readback.append({
                    "index": index,
                    "valid": bool(viewport._temporal_disocclusion_valid[index]),
                    "minimum": values.min(axis=(0, 1)).tolist(),
                    "maximum": values.max(axis=(0, 1)).tolist(),
                    "nonzero_pixels": np.count_nonzero(values, axis=(0, 1)).tolist(),
                })
            assert len(disocclusion_readback) == len(depth_motion_readback) == 2
            assert all(target["valid"] for target in disocclusion_readback)
            temporal_disocclusion_checks = {
                "paired_rg8_finite_normalized": True,
                "paired_rg16f_finite_nonnegative": True,
                "disocclusion": disocclusion_readback,
                "depth_motion": depth_motion_readback,
            }
            linear_depth_readback = []
            for name, texture in zip(
                ("opaque", "composed"), viewport._temporal_linear_depth_textures,
            ):
                values = read_red_target(texture, viewport._bloom_size)
                assert np.isfinite(values).all() and np.all(values >= 0.0), name
                linear_depth_readback.append({
                    "name": name,
                    "minimum": float(values.min()),
                    "maximum": float(values.max()),
                    "nonzero_pixels": int(np.count_nonzero(values)),
                })
            alpha_mask = read_red_target(
                viewport._temporal_alpha_mask_texture,
                viewport._motion_blur_sizes[0],
            )
            assert np.isfinite(alpha_mask).all()
            assert np.all((alpha_mask >= 0.0) & (alpha_mask <= 1.0))
            half_names = (
                "disocclusion", "velocity", "maximum_depth", "minimum_depth",
            )
            half_readback = []
            for index, (name, texture) in enumerate(zip(
                half_names, viewport._temporal_half_textures,
            )):
                values = (
                    read_rg_target(texture, viewport._motion_blur_sizes[0])
                    if index == 1 else
                    read_red_target(texture, viewport._motion_blur_sizes[0])
                )
                assert np.isfinite(values).all(), name
                if index != 1:
                    assert np.all(values >= 0.0), name
                half_readback.append({
                    "name": name,
                    "minimum": np.min(values, axis=(0, 1)).tolist()
                    if values.ndim == 3 else float(values.min()),
                    "maximum": np.max(values, axis=(0, 1)).tolist()
                    if values.ndim == 3 else float(values.max()),
                    "nonzero_pixels": np.count_nonzero(values, axis=(0, 1)).tolist()
                    if values.ndim == 3 else int(np.count_nonzero(values)),
                })
            temporal_alpha_checks = {
                "valid": bool(viewport._temporal_alpha_valid),
                "linear_depth_finite_nonnegative": True,
                "alpha_mask_finite_normalized": True,
                "alpha_mask_minimum": float(alpha_mask.min()),
                "alpha_mask_maximum": float(alpha_mask.max()),
                "alpha_mask_nonzero_pixels": int(np.count_nonzero(alpha_mask)),
                "linear_depth": linear_depth_readback,
                "half_outputs": half_readback,
            }
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
        camera_history_preserved = (
            int(viewport._temporal_sample_count)
            >= temporal_samples_before_motion + camera_motion_frames
        )
        if args.camera_yaw_step != 0.0:
            assert camera_motion_frames > 0
            assert camera_history_preserved
        def quantiles_or_empty(values, probabilities):
            return np.quantile(values, probabilities).tolist() \
                if values.size else []

        report = {
            "model": f"{args.model:016X}",
            "path": lookup.full_path(args.model),
            "lod": args.lod,
            "viewport_size": [args.width, args.height],
            "orthographic": bool(args.orthographic),
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
            "fur_renderer": "recovered_shells_and_capture_derived_model_strands",
            "vertex_tangent_frame": "retail_packed_authored_tangent_and_handedness",
            "fur_layer_volume": (
                "recovered_procedural_128x128x32_exact_integer_mips"
            ),
            "fur_coverage_resolve": "32_sample_jittered_temporal_stochastic_opaque",
            "temporal_sample_count": viewport._temporal_sample_count,
            "temporal_apply_misc": {
                "nonopaque_response_input": args.temporal_nonopaque_response,
                "conditional_floor": args.temporal_conditional_floor,
                "hdr_reference_input": args.temporal_hdr_reference,
                "last_frame_history_age": max(
                    int(viewport._temporal_sample_count) - 1, 0,
                ),
                "last_frame_m_Misc": list(viewport.temporal_aa_misc(
                    max(int(viewport._temporal_sample_count) - 1, 0),
                )),
            },
            "temporal_camera_motion": {
                "yaw_start": camera_yaw_start,
                "yaw_step": args.camera_yaw_step,
                "frames": camera_motion_frames,
                "yaw_end": float(viewport.camera.yaw),
                "sample_count_before": temporal_samples_before_motion,
                "sample_count_after": int(viewport._temporal_sample_count),
                "history_preserved": camera_history_preserved,
            },
            "temporal_motion_stencil": temporal_motion_stencil_checks,
            "temporal_color_storage": (
                "paired_native_r11g11b10"
                if len(viewport._temporal_textures) == 2 else "unavailable"
            ),
            "temporal_depth_history": (
                "paired_rg16f_depth_camera_motion"
                if len(viewport._temporal_depth_textures) == 2 else "unavailable"
            ),
            "temporal_full_disocclusion": {
                "producer": "captured_full_resolution_depth_motion_scatter_path",
                "program_ready": bool(viewport._temporal_disocclusion_prog),
                "history_valid": list(viewport._temporal_disocclusion_valid),
                "targets": temporal_disocclusion_targets,
                "readback": temporal_disocclusion_checks,
            },
            "temporal_accumulated_alpha": {
                "producer": "events_16269_18687_18695_18704_18712",
                "queue_execution": "dense_mask_discard_output_equivalent",
                "programs_ready": all((
                    viewport._temporal_linear_depth_prog,
                    viewport._temporal_half_base_prog,
                    viewport._temporal_alpha_mask_prog,
                    viewport._temporal_alpha_half_prog,
                )),
                "valid": bool(viewport._temporal_alpha_valid),
                "targets": temporal_alpha_targets,
                "readback": temporal_alpha_checks,
            },
            "motion_blur_scatter": {
                "producer": "captured_downsample_neighborhood_and_40_crossing_path",
                "programs_ready": all((
                    viewport._motion_blur_downsample_prog,
                    viewport._motion_blur_neighborhood_half_prog,
                    viewport._motion_blur_neighborhood_quarter_prog,
                    viewport._motion_blur_gather_neighborhood_prog,
                    viewport._motion_blur_scatter_prog,
                )),
                "sizes": [list(size) for size in viewport._motion_blur_sizes],
                "history_valid": list(viewport._motion_blur_scatter_valid),
                "targets": motion_blur_targets,
                "readback": motion_blur_checks,
            },
            "fur_contact_shadow": (
                "native_four_tap_key_light_before_denoise"
                if viewport._fur_contact_enabled and viewport._fur_deferred_active
                else "disabled_control"
            ),
            "fur_screen_space_shadow": viewport._fur_contact_enabled and viewport._fur_deferred_active,
            "fur_deferred_lighting": viewport._fur_deferred_active,
            "fur_scene_lighting": viewport._fur_deferred_active and viewport._fur_scene_is_current(),
            "fur_scene_bundle": str(args.fur_scene_bundle) if args.fur_scene_bundle else None,
            "preview_light_direction": list(viewport._preview_light_direction),
            "fur_scene_key_shadow": bool(viewport._fur_scene_is_current()
                                         and viewport._fur_scene_gpu.params['has_key_shadow']),
            "fur_contact_program": bool(viewport._fur_contact_prog),
            "fur_material_program": bool(viewport._fur_material_prog),
            "fur_decode_program": bool(viewport._fur_decode_prog),
            "fur_lighting_program": bool(viewport._fur_lighting_prog),
            "fur_material_targets": [
                "RGBA16_UINT", "RGBA8_SRGB", "R32_FLOAT", "R32_UINT",
                "RG16_FLOAT", "shared_R8_UINT_stencil",
            ],
            "fur_color_storage": (
                "native_r11g11b10_rtz_at_lighting_and_denoise_stores"
                if viewport._fur_deferred_active else "forward_framebuffer"
            ),
            "deferred_target_checks": deferred_checks,
            "fur_hair_denoise": (
                "captured_three_step_tangent_depth_mask_gather"
                if viewport._fur_denoise_enabled and viewport._fur_deferred_active
                else "disabled_control"
            ),
            "fur_environment": {
                "asset": environment_label,
                "source": environment_source,
                "layout": environment_layout,
                "encoding": getattr(cube_mips, 'encoding', 'rgb16f'),
                "face_count": len(cube_mips),
                "mips_per_face": len(cube_mips[0]) if cube_mips else 0,
                "face_size": list(cube_mips[0][0][:2]) if cube_mips else None,
                "brdf_source": "dds_override" if args.fur_brdf_dds else "embedded_exact",
                "brdf_rg_sha256": hashlib.sha256(brdf_rg_half).hexdigest(),
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
                "time_step": args.fur_wind_time_step,
                "initial_time": args.fur_wind_time,
                "object_phase": viewport._fur_wind_object_phase,
                "field": "captured_64_vector_cubic_procedural",
            },
            "fur_weighted_oit": False,
            "model_strands": {
                "program_ready": bool(viewport._model_strand_material_prog),
                "groups": [group.summary for group in viewport._gpu_model_strands],
                "material_path": "shared_native_hair_gbuffer_decode_lighting_denoise",
                "dynamics": sorted({
                    group.summary.get("dynamics", "unknown")
                    for group in viewport._gpu_model_strands
                }),
            },
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
                    "gpu_texture_formats": texture_formats[mesh.material_index],
                    "gpu_texture_anisotropy": texture_anisotropy[mesh.material_index],
                }
                for mesh in fur_meshes
            ],
            "opengl": {
                "vendor": (glGetString(GL_VENDOR) or b"").decode(errors="replace"),
                "renderer": (glGetString(GL_RENDERER) or b"").decode(errors="replace"),
                "version": (glGetString(GL_VERSION) or b"").decode(errors="replace"),
                "native_raster_active": bool(viewport._native_raster_active),
            },
            "synchronous_frame_time_ms": {
                "samples": frame_times_ms,
                "median": float(np.median(frame_times_ms)),
                "p95": float(np.percentile(frame_times_ms, 95)),
            },
            "screenshot": str(args.output),
            "wind_animation": animation_report,
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        if cube_mips and not report["fur_environment"]["gpu_ready"]:
            viewport.doneCurrent()
            viewport.close()
            app.exit(1)
            return
        viewport.doneCurrent()
        viewport.close()
        app.quit()

    QTimer.singleShot(max(100, args.delay_ms), finish)
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
