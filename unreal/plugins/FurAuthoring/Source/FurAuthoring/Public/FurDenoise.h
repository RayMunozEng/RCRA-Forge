#pragma once
#include "CoreMinimal.h"
class FRDGBuilder;
class FRDGTexture;
/** Inputs must share a tightly packed top-left viewport. Depth is in meters.
 * These are fur-specific buffers, NOT Unreal's unlit GBuffer defaults.
 * Caller must invoke before TAA and supply linear, pre-exposure-compatible color.
 */
struct FFurDenoiseInputs
{
    FRDGTexture* SceneColor = nullptr;
    FRDGTexture* StrandDepth = nullptr; // decoded world strand RGB, linear depth A
    FRDGTexture* NormalMask = nullptr; // decoded world normal RGB, fractional hair mask A
    FRDGTexture* ActiveTiles = nullptr; // unsigned integer Hair bit per8x8 tile
    FVector4f ScreenToView = FVector4f(2,2,-1,-1);
    FVector4f ViewToScreen = FVector4f(.5,.5,.5,.5);
    FMatrix44f WorldToView = FMatrix44f::Identity; // native view axes: positive depth
    FIntPoint PixelOffset=FIntPoint::ZeroValue;
    // Row-vector matrix maps decoded native world vectors to positive-Z view space.
    float PreExposure=1.0f;
    float TemporalIndex = .5f;
    float TemporalCycle = 0;
};
/** Returns a new RGBA16F texture, or nullptr if the required buffers are invalid.
 * No automatic scene hook: caller owns correct surface data and pass ordering.
 */
FURAUTHORING_API FRDGTexture* AddRecoveredFurDenoisePass(FRDGBuilder& GraphBuilder,
    const FFurDenoiseInputs& Inputs);

// Build one active flag per 8x8 block from the surviving fur mask.
FURAUTHORING_API FRDGTexture* AddFurActiveTilesPass(FRDGBuilder&,FRDGTexture* NormalMask);
