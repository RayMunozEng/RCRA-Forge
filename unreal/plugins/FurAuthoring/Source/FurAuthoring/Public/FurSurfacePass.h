#pragma once
#include "CoreMinimal.h"
#include "RenderGraphFwd.h"
class FSceneView;
class FScene;
class FInstanceCullingManager;
class FPrimitiveSceneProxy;
struct FMeshBatch;
struct FFurSurfaceMesh
{
 const FMeshBatch* Mesh=nullptr;
 const FPrimitiveSceneProxy* Primitive=nullptr;
 uint64 ElementMask=~0ull;
 int32 StaticMeshId=INDEX_NONE;
};
struct FFurSurfaceTextures
{
 FRDGTexture* NormalMask=nullptr;
 FRDGTexture* StrandDepth=nullptr;
 int32 SubmittedBatches=0;
};
// Experimental render-thread pass. Explicit visible mesh list; no automatic scene hook.
// Single view, full scene extent. The caller must crop before AddRecoveredFurDenoisePass.
// Depth is read-only: only fur samples matching the already rendered scene can contribute.
FURAUTHORING_API FFurSurfaceTextures AddFurSurfacePass(FRDGBuilder& GraphBuilder,
 const FSceneView& View,const FScene* Scene,FInstanceCullingManager* InstanceCullingManager,
 FRDGTexture* SceneDepth,FIntRect ViewRect,TConstArrayView<FFurSurfaceMesh> Meshes);
