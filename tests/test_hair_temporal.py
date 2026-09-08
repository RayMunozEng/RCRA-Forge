import math

import pytest

from core.hair_temporal import (
    TEMPORAL_ACC_ALPHA_MOTION_THRESHOLD,
    TEMPORAL_ACC_ALPHA_DISOCCLUSION_BINDINGS,
    TEMPORAL_ACC_ALPHA_DISOCCLUSION_SHADER_SHA256,
    TEMPORAL_ACC_ALPHA_HALF_BINDINGS,
    TEMPORAL_ACC_ALPHA_HALF_MASK_BINDINGS,
    TEMPORAL_ACC_ALPHA_HALF_MASK_SHADER_SHA256,
    TEMPORAL_ACC_ALPHA_HALF_SHADER_SHA256,
    TEMPORAL_ACC_ALPHA_WORK_QUEUE_BINDINGS,
    TEMPORAL_ACC_ALPHA_WORK_QUEUE_SHADER_SHA256,
    TEMPORAL_APPLY_BINDINGS,
    TEMPORAL_APPLY_CBUFFER_SIZE,
    TEMPORAL_APPLY_SHADER_SHA256,
    TEMPORAL_DISOCCLUSION_BINDINGS,
    TEMPORAL_DISOCCLUSION_CAPTURE_DEPTH_BASE,
    TEMPORAL_DISOCCLUSION_CAPTURE_DEPTH_SLOPE,
    TEMPORAL_DISOCCLUSION_CAPTURE_MOTION_THRESHOLD,
    TEMPORAL_DISOCCLUSION_HALF_BINDINGS,
    TEMPORAL_DISOCCLUSION_HALF_SHADER_SHA256,
    TEMPORAL_DISOCCLUSION_SHADER_SHA256,
    TEMPORAL_NONOPAQUE_RESPONSE_FALLBACK,
    TemporalAaCBuffer,
    build_temporal_apply_cbuffer,
    temporal_apply_misc,
    temporal_disocclusion_camera_scale,
    temporal_hdr_scale,
    temporal_minimum_rejection,
    temporal_nonopaque_response,
    temporal_pixel_scale,
)


def test_captured_disocclusion_scalars_keep_exact_float32_values():
    assert TEMPORAL_DISOCCLUSION_CAPTURE_DEPTH_BASE == 8.0
    assert TEMPORAL_DISOCCLUSION_CAPTURE_DEPTH_SLOPE == 26.875001907348633
    assert TEMPORAL_DISOCCLUSION_CAPTURE_MOTION_THRESHOLD == 1.0
    assert TEMPORAL_ACC_ALPHA_MOTION_THRESHOLD == 0.6666666865348816
    assert temporal_disocclusion_camera_scale(1280) == 1.0
    assert temporal_disocclusion_camera_scale(3440) == 0.5581395626068115
    with pytest.raises(ValueError):
        temporal_disocclusion_camera_scale(0)


def test_captured_native_apply_contract_matches_recovered_producers():
    cbuffer = build_temporal_apply_cbuffer(
        view_space_delta=(
            1.0, 2.168404344971009e-19, 0.0, 0.0,
            4.336808689942018e-19, 1.0, 0.0, 0.0,
            -5.551115123125783e-17, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ),
        screen_to_view=(
            1.4289823770523071,
            0.5981786847114563,
            -0.7144911885261536,
            -0.29908934235572815,
        ),
        destination_size=(3440, 1440),
        filter_offset_pixels=(-0.3400000035762787, 0.019999980926513672),
        nonopaque_response=TEMPORAL_NONOPAQUE_RESPONSE_FALLBACK,
        runtime_hdr_reference=0.006569501478328294,
        history_age=3645,
    )

    assert cbuffer.pixel_scale == (
        3440.0,
        1440.0,
        0.0002906976733356714,
        0.0006944444612599909,
    )
    assert cbuffer.source_pixel_scale == cbuffer.pixel_scale
    assert cbuffer.misc == (
        0.0625,
        0.0022656249348074198,
        76.1092758178711,
        0.00027427318855188787,
    )
    assert cbuffer.misc2 == (0.0, 0.0, -0.3400000035762787, 0.019999980926513672)
    assert cbuffer.dither_constants == (
        0.011111111380159855,
        0.02222222276031971,
        0.0,
        0.4390000104904175,
    )

    captured_filter_registers = (
        (0.00452788919210434, 0.3166002333164215, 0.703286349773407, -0.054635629057884216),
        (0.01868058741092682, 0.0, 0.0, 0.0),
        (0.0023813899606466293, 0.0007661409908905625, 0.008746378123760223, -0.0003534287679940462),
    )
    for recovered, captured in zip(
        (cbuffer.filter_weights_a, cbuffer.filter_weights_b, cbuffer.filter_weights_c),
        captured_filter_registers,
    ):
        assert recovered == pytest.approx(captured, abs=1.0e-8)


def test_temporal_cbuffer_binary_contract_round_trips_all_224_bytes():
    cbuffer = build_temporal_apply_cbuffer(
        view_space_delta=tuple(float(index) for index in range(16)),
        screen_to_view=(1.0, 2.0, 3.0, 4.0),
        destination_size=(1920, 1080),
        source_size=(1280, 720),
        filter_offset_pixels=(0.25, -0.125),
        history_age=9,
        conditional_floor=True,
        fuzz_enabled=True,
        screen_capture_enabled=True,
    )
    packed = cbuffer.pack()

    assert len(packed) == TEMPORAL_APPLY_CBUFFER_SIZE
    assert TemporalAaCBuffer.unpack(packed) == cbuffer


def test_native_apply_binding_and_shader_identity_are_explicit():
    assert TEMPORAL_APPLY_SHADER_SHA256 == (
        "b892667bfa835a95a7f58c78b30b35d45e5784b48d750bf6543bf557d9956e0f"
    )
    assert [binding[0] for binding in TEMPORAL_APPLY_BINDINGS] == [
        "t5", "t6", "t7", "t8", "t9", "t10", "t11", "u0"
    ]
    assert TEMPORAL_APPLY_BINDINGS[-1] == (
        "u0", "g_TemporalAaOutput", "R11G11B10_FLOAT"
    )


def test_native_disocclusion_chain_identities_and_bindings_are_explicit():
    assert TEMPORAL_DISOCCLUSION_SHADER_SHA256 == (
        "5b4710e1aa9806872423d16b5a66bfa8755ee3269bd07685888b808d7b31cc97"
    )
    assert [binding[0] for binding in TEMPORAL_DISOCCLUSION_BINDINGS] == [
        "t5", "t6", "t7", "t8", "u0", "u1"
    ]
    assert TEMPORAL_DISOCCLUSION_HALF_SHADER_SHA256 == (
        "afad553b7bdab5011e9acc6a61e7818abb723c06f986243e478239b61740a9a8"
    )
    assert [binding[0] for binding in TEMPORAL_DISOCCLUSION_HALF_BINDINGS] == [
        "t5", "u0"
    ]
    assert TEMPORAL_ACC_ALPHA_HALF_MASK_SHADER_SHA256 == (
        "a7f48ebde450132e5eccf52f3161001bd464d74a459ab234fcbe632b641349d7"
    )
    assert [binding[0] for binding in TEMPORAL_ACC_ALPHA_HALF_MASK_BINDINGS] == [
        "t5", "t6", "u0"
    ]
    assert TEMPORAL_ACC_ALPHA_WORK_QUEUE_SHADER_SHA256 == (
        "4c6def4e3af247418b546dd581cf971bd93fc274e3c1163a892f6ec8da3729b1"
    )
    assert [binding[0] for binding in TEMPORAL_ACC_ALPHA_WORK_QUEUE_BINDINGS] == [
        "t5", "u0"
    ]
    assert TEMPORAL_ACC_ALPHA_DISOCCLUSION_SHADER_SHA256 == (
        "3325938addce04cf33c1d7d66bc6b22d8c7bd539715ec870a090707d04aee605"
    )
    assert [binding[0] for binding in TEMPORAL_ACC_ALPHA_DISOCCLUSION_BINDINGS] == [
        "t5", "t6", "t7", "t8", "t9", "t10", "u0", "u1"
    ]
    assert TEMPORAL_ACC_ALPHA_HALF_SHADER_SHA256 == (
        "f702297bceb7df68c195b3655bf6d24beb75bb9d998a2da3f49644cb911bd5e7"
    )
    assert [binding[0] for binding in TEMPORAL_ACC_ALPHA_HALF_BINDINGS] == [
        "t9", "t5", "t6", "t7", "u0", "u1", "u2", "u3"
    ]
    assert TEMPORAL_ACC_ALPHA_HALF_BINDINGS[-1] == (
        "u3", "g_AccAlphaMinDepthOutput", "R16_FLOAT"
    )


def test_temporal_hdr_scale_preserves_clamp_and_nan_behavior():
    assert temporal_hdr_scale(None) == 0.25
    assert temporal_hdr_scale(float("nan")) == 0.25
    assert temporal_hdr_scale(0.0) == pytest.approx(5000.0)
    assert temporal_hdr_scale(1000.0) == pytest.approx(0.005)
    assert math.isfinite(temporal_hdr_scale(float("nan")))


def test_runtime_temporal_misc_preserves_native_override_and_floor_rules():
    fallback = TEMPORAL_NONOPAQUE_RESPONSE_FALLBACK
    assert temporal_nonopaque_response(None) == fallback
    assert temporal_nonopaque_response(0.0) == fallback
    assert temporal_nonopaque_response(-1.0) == fallback
    assert temporal_nonopaque_response(float("nan")) == fallback
    assert temporal_nonopaque_response(0.2) == pytest.approx(0.2)
    assert temporal_minimum_rejection(0.2) == pytest.approx(0.2)
    assert temporal_minimum_rejection(0.08, conditional_floor=True) == pytest.approx(0.1)
    assert temporal_apply_misc(
        nonopaque_response=fallback,
        runtime_hdr_reference=0.006569501478328294,
        history_age=3645,
    ) == (
        0.0625,
        0.0022656249348074198,
        76.1092758178711,
        0.00027427318855188787,
    )


def test_temporal_pixel_scale_rejects_empty_dimensions():
    with pytest.raises(ValueError, match="positive"):
        temporal_pixel_scale((0, 1440))
