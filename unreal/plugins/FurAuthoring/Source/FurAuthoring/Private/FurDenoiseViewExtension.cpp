#include "FurDenoiseViewExtension.h"

#include "FurDenoise.h"
#include "FurSurfacePass.h"
#include "HAL/IConsoleManager.h"
#include "PostProcess/PostProcessInputs.h"
#include "PrimitiveSceneInfo.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "ScenePrivate.h"
#include "SceneRendering.h"
#include "SceneTexturesConfig.h"
#include "SceneViewExtension.h"
#include "StaticMeshBatch.h"

DEFINE_LOG_CATEGORY_STATIC(LogFurDenoiseViewExtension, Log, All);

static TAutoConsoleVariable<int32> CVarFurAuthoringDenoise(
    TEXT("r.FurAuthoring.Denoise"),
    0,
    TEXT("Run the recovered fur surface filter before TAA for materials tagged RecoveredFurSurface.\n")
    TEXT("0: disabled (default), 1: enabled"),
    ECVF_RenderThreadSafe);

class FFurDenoiseViewExtension final : public FSceneViewExtensionBase
{
public:
    explicit FFurDenoiseViewExtension(const FAutoRegister& AutoRegister)
        : FSceneViewExtensionBase(AutoRegister)
    {
    }

    virtual void SetupViewFamily(FSceneViewFamily&) override {}
    virtual void SetupView(FSceneViewFamily&, FSceneView&) override {}
    virtual void BeginRenderViewFamily(FSceneViewFamily&) override {}

    virtual bool IsActiveThisFrame_Internal(
        const FSceneViewExtensionContext&) const override
    {
        return CVarFurAuthoringDenoise.GetValueOnAnyThread() != 0;
    }

    virtual void PrePostProcessPass_RenderThread(
        FRDGBuilder& GraphBuilder,
        const FSceneView& BaseView,
        const FPostProcessingInputs& Inputs) override
    {
        if (CVarFurAuthoringDenoise.GetValueOnRenderThread() == 0
            || !BaseView.bIsViewInfo
            || !BaseView.Family
            || !BaseView.Family->Scene
            || !Inputs.SceneTextures)
        {
            return;
        }

        const FViewInfo& View = static_cast<const FViewInfo&>(BaseView);
        if (!View.IsPerspectiveProjection() || View.IsInstancedStereo())
        {
            return;
        }

        const FScene* Scene = View.Family->Scene->GetRenderScene();
        if (!Scene)
        {
            return;
        }

        FRDGTexture* SceneColor =
            Inputs.SceneTextures->GetParameters()->SceneColorTexture;
        FRDGTexture* SceneDepth =
            Inputs.SceneTextures->GetParameters()->SceneDepthTexture;
        if (!SceneColor || !SceneDepth || SceneColor->Desc.Format != PF_FloatRGBA
            || View.ViewRect.Min.X < 0 || View.ViewRect.Min.Y < 0
            || View.ViewRect.Width() <= 0 || View.ViewRect.Height() <= 0
            || View.ViewRect.Width() > 4096 || View.ViewRect.Height() > 4096)
        {
            return;
        }

        TArray<FFurSurfaceMesh> Meshes;
        Meshes.Reserve(View.DynamicMeshElements.Num() + Scene->StaticMeshes.Num());
        for (const auto& Batch : View.DynamicMeshElements)
        {
            if (Batch.GetHasMaskedMaterial() && Batch.GetRenderInMainPass())
            {
                Meshes.Add({Batch.Mesh, Batch.PrimitiveSceneProxy, ~0ull, INDEX_NONE});
            }
        }
        for (auto It = Scene->StaticMeshes.CreateConstIterator(); It; ++It)
        {
            const FStaticMeshBatch* Mesh = *It;
            if (Mesh && Mesh->Id < View.StaticMeshVisibilityMap.Num()
                && View.StaticMeshVisibilityMap[Mesh->Id])
            {
                Meshes.Add({Mesh, Mesh->PrimitiveSceneInfo->Proxy, ~0ull, Mesh->Id});
            }
        }

        const FFurSurfaceTextures Surface = AddFurSurfacePass(
            GraphBuilder,
            View,
            Scene,
            nullptr,
            SceneDepth,
            View.ViewRect,
            Meshes);
        if (!Surface.NormalMask || !Surface.StrandDepth || Surface.SubmittedBatches == 0)
        {
            return;
        }

        auto CropToView = [&](FRDGTexture* Source, const TCHAR* Name)
        {
            FRDGTextureDesc Desc = Source->Desc;
            Desc.Extent = View.ViewRect.Size();
            FRDGTexture* Cropped = GraphBuilder.CreateTexture(Desc, Name);
            FRHICopyTextureInfo CopyInfo;
            CopyInfo.SourcePosition = FIntVector(
                View.ViewRect.Min.X,
                View.ViewRect.Min.Y,
                0);
            CopyInfo.Size = FIntVector(
                View.ViewRect.Width(),
                View.ViewRect.Height(),
                1);
            AddCopyTexturePass(GraphBuilder, Source, Cropped, CopyInfo);
            return Cropped;
        };

        FFurDenoiseInputs Filter;
        Filter.SceneColor = CropToView(SceneColor, TEXT("Fur.SceneColor"));
        Filter.NormalMask = CropToView(Surface.NormalMask, TEXT("Fur.NormalMask"));
        Filter.StrandDepth = CropToView(Surface.StrandDepth, TEXT("Fur.StrandDepth"));
        Filter.ActiveTiles = AddFurActiveTilesPass(GraphBuilder, Filter.NormalMask);

        const FMatrix& Projection = View.ViewMatrices.GetViewToClip();
        const double ProjectionX = Projection.M[0][0];
        const double ProjectionY = Projection.M[1][1];
        const double JitterX = Projection.M[2][0];
        const double JitterY = Projection.M[2][1];
        if (!FMath::IsFinite(ProjectionX) || !FMath::IsFinite(ProjectionY)
            || FMath::IsNearlyZero(ProjectionX) || FMath::IsNearlyZero(ProjectionY))
        {
            return;
        }
        Filter.ScreenToView = FVector4f(
            2.0 / ProjectionX,
            -2.0 / ProjectionY,
            (-1.0 - JitterX) / ProjectionX,
            (1.0 - JitterY) / ProjectionY);
        Filter.ViewToScreen = FVector4f(
            ProjectionX * 0.5,
            -ProjectionY * 0.5,
            0.5 + JitterX * 0.5,
            0.5 - JitterY * 0.5);

        const FMatrix& WorldToView = View.ViewMatrices.GetWorldToView();
        Filter.WorldToView = FMatrix44f::Identity;
        // Recovered native vectors use UE xzy. Both sides use row-vector matrices.
        for (int32 Row = 0; Row < 3; ++Row)
        {
            const int32 SourceRow = Row == 1 ? 2 : Row == 2 ? 1 : 0;
            for (int32 Column = 0; Column < 3; ++Column)
            {
                Filter.WorldToView.M[Row][Column] = WorldToView.M[SourceRow][Column];
            }
        }

        const FViewUniformShaderParameters& Uniforms =
            *View.CachedViewUniformShaderParameters;
        uint32 HaltonIndex = (Uniforms.StateFrameIndex & 31u) + 1u;
        float HaltonWeight = 0.5f;
        Filter.TemporalIndex = 0.0f;
        while (HaltonIndex)
        {
            Filter.TemporalIndex += (HaltonIndex & 1u) * HaltonWeight;
            HaltonIndex >>= 1u;
            HaltonWeight *= 0.5f;
        }
        Filter.TemporalCycle = static_cast<float>(Uniforms.StateFrameIndex % 160u);
        Filter.PreExposure = Uniforms.PreExposure;
        Filter.PixelOffset = View.ViewRect.Min;

        FRDGTexture* Filtered = AddRecoveredFurDenoisePass(GraphBuilder, Filter);
        if (!Filtered)
        {
            return;
        }

        if (!bLoggedExecution)
        {
            UE_LOG(
                LogFurDenoiseViewExtension,
                Display,
                TEXT("Production pre-TAA fur denoise executed: %u tagged batches, %dx%d view."),
                Surface.SubmittedBatches,
                View.ViewRect.Width(),
                View.ViewRect.Height());
            bLoggedExecution = true;
        }

        FRHICopyTextureInfo CopyBack;
        CopyBack.DestPosition = FIntVector(
            View.ViewRect.Min.X,
            View.ViewRect.Min.Y,
            0);
        CopyBack.Size = FIntVector(
            View.ViewRect.Width(),
            View.ViewRect.Height(),
            1);
        AddCopyTexturePass(GraphBuilder, Filtered, SceneColor, CopyBack);
    }

private:
    bool bLoggedExecution = false;
};

static TSharedPtr<FFurDenoiseViewExtension, ESPMode::ThreadSafe>
    GFurDenoiseViewExtension;

void FurAuthoring::StartDenoiseViewExtension()
{
    if (!GFurDenoiseViewExtension.IsValid())
    {
        GFurDenoiseViewExtension =
            FSceneViewExtensions::NewExtension<FFurDenoiseViewExtension>();
    }
}

void FurAuthoring::StopDenoiseViewExtension()
{
    GFurDenoiseViewExtension.Reset();
}

bool FurAuthoring::IsDenoiseViewExtensionRegistered()
{
    return GFurDenoiseViewExtension.IsValid();
}
