#include "FurDenoise.h"
#include "GlobalShader.h"
#include "ShaderParameterStruct.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "RHIStaticStates.h"
#include "DataDrivenShaderPlatformInfo.h"

class FRecoveredFurDenoiseCS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FRecoveredFurDenoiseCS);
    SHADER_USE_PARAMETER_STRUCT(FRecoveredFurDenoiseCS,FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters,)
        SHADER_PARAMETER_RDG_TEXTURE(Texture2D,FurSceneColor)
        SHADER_PARAMETER_RDG_TEXTURE(Texture2D,FurStrandDepth)
        SHADER_PARAMETER_RDG_TEXTURE(Texture2D,FurNormalMask)
        SHADER_PARAMETER_RDG_TEXTURE(Texture2D<uint>,FurActiveTiles)
        SHADER_PARAMETER_SAMPLER(SamplerState,FurPointClamp)
        SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D<float4>,FurFilteredColor)
        SHADER_PARAMETER(FUintVector2,FurDimensions)
        SHADER_PARAMETER(FUintVector2,FurPixelOffset)
        SHADER_PARAMETER(FVector4f,FurScreenToView)
        SHADER_PARAMETER(FVector4f,FurViewToScreen)
        SHADER_PARAMETER(FMatrix44f,FurWorldToView)
        SHADER_PARAMETER(float,FurPreExposure)
        SHADER_PARAMETER(float,FurTemporalIndex)
        SHADER_PARAMETER(float,FurTemporalCycle)
    END_SHADER_PARAMETER_STRUCT()
    static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters)
    { return IsFeatureLevelSupported(Parameters.Platform,ERHIFeatureLevel::SM5); }
};
IMPLEMENT_GLOBAL_SHADER(FRecoveredFurDenoiseCS,"/Plugin/FurAuthoring/FurDenoise.usf","MainCS",SF_Compute);

FRDGTexture* AddRecoveredFurDenoisePass(FRDGBuilder& GraphBuilder,const FFurDenoiseInputs& Inputs)
{
    if(!FMath::IsFinite(Inputs.PreExposure) || Inputs.PreExposure<=0 || !Inputs.SceneColor || !Inputs.StrandDepth || !Inputs.NormalMask || !Inputs.ActiveTiles)
        return nullptr;
    const FIntPoint Size=Inputs.SceneColor->Desc.Extent;
    const FIntPoint Tiles(FMath::DivideAndRoundUp(Size.X,8),FMath::DivideAndRoundUp(Size.Y,8));
    if(Size.X<=0 || Size.Y<=0 || Size.X>4096 || Size.Y>4096
        || Inputs.StrandDepth->Desc.Extent!=Size || Inputs.NormalMask->Desc.Extent!=Size
        || Inputs.ActiveTiles->Desc.Extent!=Tiles
        || (Inputs.ActiveTiles->Desc.Format!=PF_R8_UINT && Inputs.ActiveTiles->Desc.Format!=PF_R32_UINT))
        return nullptr;
    auto* Output=GraphBuilder.CreateTexture(FRDGTextureDesc::Create2D(Size,PF_FloatRGBA,
        FClearValueBinding::None,TexCreate_ShaderResource|TexCreate_UAV),TEXT("Fur.DenoisedColor"));
    auto* Parameters=GraphBuilder.AllocParameters<FRecoveredFurDenoiseCS::FParameters>();
    Parameters->FurSceneColor=Inputs.SceneColor;
    Parameters->FurStrandDepth=Inputs.StrandDepth;
    Parameters->FurNormalMask=Inputs.NormalMask;
    Parameters->FurActiveTiles=Inputs.ActiveTiles;
    Parameters->FurPointClamp=TStaticSamplerState<SF_Point,AM_Clamp,AM_Clamp,AM_Clamp>::GetRHI();
    Parameters->FurFilteredColor=GraphBuilder.CreateUAV(Output);
    Parameters->FurDimensions=FUintVector2(Size.X,Size.Y);
    Parameters->FurPixelOffset=FUintVector2(Inputs.PixelOffset.X,Inputs.PixelOffset.Y);
    Parameters->FurScreenToView=Inputs.ScreenToView;
    Parameters->FurViewToScreen=Inputs.ViewToScreen;
    Parameters->FurWorldToView=Inputs.WorldToView;
    Parameters->FurPreExposure=Inputs.PreExposure;
    Parameters->FurTemporalIndex=Inputs.TemporalIndex;
    Parameters->FurTemporalCycle=Inputs.TemporalCycle;
    TShaderMapRef<FRecoveredFurDenoiseCS> Shader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
    FComputeShaderUtils::AddPass(GraphBuilder,RDG_EVENT_NAME("Fur.RecoveredDenoise"),Shader,
        Parameters,FComputeShaderUtils::GetGroupCount(Size,8));
    return Output;
}

class FFurActiveTilesCS:public FGlobalShader
{
 DECLARE_GLOBAL_SHADER(FFurActiveTilesCS);
 SHADER_USE_PARAMETER_STRUCT(FFurActiveTilesCS,FGlobalShader);
 BEGIN_SHADER_PARAMETER_STRUCT(FParameters,)
  SHADER_PARAMETER_RDG_TEXTURE(Texture2D,FurNormalMask)
  SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D<uint>,FurTileMask)
  SHADER_PARAMETER(FUintVector2,FurDimensions)
 END_SHADER_PARAMETER_STRUCT()
 static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& P)
 {return IsFeatureLevelSupported(P.Platform,ERHIFeatureLevel::SM5);}
};
IMPLEMENT_GLOBAL_SHADER(FFurActiveTilesCS,"/Plugin/FurAuthoring/FurActiveTiles.usf","MainCS",SF_Compute);
FRDGTexture* AddFurActiveTilesPass(FRDGBuilder& GraphBuilder,FRDGTexture* NormalMask)
{
 if(!NormalMask || NormalMask->Desc.Extent.X<=0 || NormalMask->Desc.Extent.Y<=0
  || NormalMask->Desc.Extent.X>4096 || NormalMask->Desc.Extent.Y>4096)return nullptr;
 const FIntPoint Size=NormalMask->Desc.Extent;
 const FIntPoint Tiles=FIntPoint(FMath::DivideAndRoundUp(Size.X,8),FMath::DivideAndRoundUp(Size.Y,8));
 auto* Output=GraphBuilder.CreateTexture(FRDGTextureDesc::Create2D(Tiles,PF_R32_UINT,
  FClearValueBinding::None,TexCreate_ShaderResource|TexCreate_UAV),TEXT("Fur.ActiveTiles"));
 auto* P=GraphBuilder.AllocParameters<FFurActiveTilesCS::FParameters>();
 P->FurNormalMask=NormalMask;P->FurTileMask=GraphBuilder.CreateUAV(Output);
 P->FurDimensions=FUintVector2(Size.X,Size.Y);
 TShaderMapRef<FFurActiveTilesCS> Shader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
 FComputeShaderUtils::AddPass(GraphBuilder,RDG_EVENT_NAME("Fur.ActiveTiles"),Shader,P,FIntVector(Tiles.X,Tiles.Y,1));
 return Output;
}
