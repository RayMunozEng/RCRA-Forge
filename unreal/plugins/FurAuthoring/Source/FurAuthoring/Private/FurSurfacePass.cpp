#include "FurSurfacePass.h"
#include "MeshMaterialShader.h"
#include "MeshPassProcessor.inl"
#include "SimpleMeshDrawCommandPass.h"
#include "SceneView.h"
#include "SceneUniformBuffer.h"
#include "SceneRendererInterface.h"
#include "MaterialShared.h"
#include "Materials/MaterialRenderProxy.h"
#include "VertexFactory.h"
#include "RenderGraphBuilder.h"
#include "RHIStaticStates.h"

static bool CompileFurSurface(const FMeshMaterialShaderPermutationParameters& P)
{
 return IsFeatureLevelSupported(P.Platform,ERHIFeatureLevel::SM5)
  && P.MaterialParameters.MaterialShaderTags.Contains(TEXT("RecoveredFurSurface"))
  && P.MaterialParameters.BlendMode==BLEND_Masked
  && !P.MaterialParameters.bHasPixelDepthOffsetConnected
  && !P.VertexFactoryType->SupportsNaniteRendering();
}
class FFurSurfaceVS:public FMeshMaterialShader
{
 DECLARE_SHADER_TYPE(FFurSurfaceVS,MeshMaterial);
public:
 FFurSurfaceVS(){}
 FFurSurfaceVS(const FMeshMaterialShaderType::CompiledShaderInitializerType& I):FMeshMaterialShader(I){}
 static bool ShouldCompilePermutation(const FMeshMaterialShaderPermutationParameters& P){return CompileFurSurface(P);}
};
class FFurSurfacePS:public FMeshMaterialShader
{
 DECLARE_SHADER_TYPE(FFurSurfacePS,MeshMaterial);
public:
 FFurSurfacePS(){}
 FFurSurfacePS(const FMeshMaterialShaderType::CompiledShaderInitializerType& I):FMeshMaterialShader(I){}
 static bool ShouldCompilePermutation(const FMeshMaterialShaderPermutationParameters& P){return CompileFurSurface(P);}
 static void ModifyCompilationEnvironment(const FMaterialShaderPermutationParameters& P,FShaderCompilerEnvironment& E)
 {
  FMeshMaterialShader::ModifyCompilationEnvironment(P,E);
  E.SetDefine(TEXT("SCENE_TEXTURES_DISABLED"),1);
  E.SetRenderTargetOutputFormat(0,PF_A32B32G32R32F);
  E.SetRenderTargetOutputFormat(1,PF_A32B32G32R32F);
 }
};
IMPLEMENT_MATERIAL_SHADER_TYPE(,FFurSurfaceVS,TEXT("/Plugin/FurAuthoring/FurSurface.usf"),TEXT("Main"),SF_Vertex);
IMPLEMENT_MATERIAL_SHADER_TYPE(,FFurSurfacePS,TEXT("/Plugin/FurAuthoring/FurSurface.usf"),TEXT("Main"),SF_Pixel);

class FFurSurfaceProcessor:public FMeshPassProcessor
{
 FMeshPassProcessorRenderState State;
public:
 int32 Submitted=0;
 FFurSurfaceProcessor(const FScene* Scene,const FSceneView& View,FMeshPassDrawListContext* Context)
 :FMeshPassProcessor(EMeshPass::Num,Scene,View.GetFeatureLevel(),&View,Context)
 {
  State.SetBlendState(TStaticBlendState<>::GetRHI());
  State.SetDepthStencilState(TStaticDepthStencilState<false,CF_Equal>::GetRHI());
 }
 virtual void AddMeshBatch(const FMeshBatch& Mesh,uint64 Mask,const FPrimitiveSceneProxy* Primitive,int32 StaticId=INDEX_NONE) override
 {
  if(!Mesh.MaterialRenderProxy || !Mesh.VertexFactory)return;
  const FMaterial* Mat=Mesh.MaterialRenderProxy->GetMaterialNoFallback(FeatureLevel);
  if(!Mat || !Mat->GetRenderingThreadShaderMap() || Mat->GetBlendMode()!=BLEND_Masked)return;
  FMaterialShaderTypes Types;Types.AddShaderType<FFurSurfaceVS>();Types.AddShaderType<FFurSurfacePS>();
  FMaterialShaders Found;
  TArray<FName> Tags;Mat->GetShaderTags(Tags);
  if(!Tags.Contains(TEXT("RecoveredFurSurface")))return;
  if(!Mat->TryGetShaders(Types,Mesh.VertexFactory->GetType(),Found))return;
  TMeshProcessorShaders<FFurSurfaceVS,FFurSurfacePS> Shaders;
  Found.TryGetVertexShader(Shaders.VertexShader);Found.TryGetPixelShader(Shaders.PixelShader);
  FMeshMaterialShaderElementData Data;
  Data.InitializeMeshMaterialData(ViewIfDynamicMeshCommand,Primitive,Mesh,StaticId,true);
  const auto Overrides=ComputeMeshOverrideSettings(Mesh);
  BuildMeshDrawCommands(Mesh,Mask,Primitive,*Mesh.MaterialRenderProxy,*Mat,State,Shaders,
   ComputeMeshFillMode(*Mat,Overrides),ComputeMeshCullMode(*Mat,Overrides),
   FMeshDrawCommandSortKey::Default,EMeshPassFeatures::Default,Data);
  ++Submitted;
 }
};
BEGIN_SHADER_PARAMETER_STRUCT(FFurSurfacePassParameters,)
 SHADER_PARAMETER_RDG_UNIFORM_BUFFER(FSceneUniformParameters,Scene)
 SHADER_PARAMETER_STRUCT_REF(FViewUniformShaderParameters,View)
 SHADER_PARAMETER_STRUCT_INCLUDE(FInstanceCullingDrawParams,InstanceCullingDrawParams)
 RENDER_TARGET_BINDING_SLOTS()
END_SHADER_PARAMETER_STRUCT()
FFurSurfaceTextures AddFurSurfacePass(FRDGBuilder& GraphBuilder,const FSceneView& View,
 const FScene* Scene,FInstanceCullingManager* InstanceCullingManager,FRDGTexture* SceneDepth,
 FIntRect ViewRect,TConstArrayView<FFurSurfaceMesh> Meshes)
{
 FFurSurfaceTextures Out;
 if(!View.bIsViewInfo || !Scene || !SceneDepth || Meshes.IsEmpty() || View.IsInstancedStereo()
  || View.GetFeatureLevel()<ERHIFeatureLevel::SM5 || ViewRect.Min.X<0 || ViewRect.Min.Y<0
  || ViewRect.Width()<=0 || ViewRect.Height()<=0 || SceneDepth->Desc.NumSamples!=1
  || SceneDepth->Desc.Extent.X>4096 || SceneDepth->Desc.Extent.Y>4096
  || ViewRect.Max.X>SceneDepth->Desc.Extent.X || ViewRect.Max.Y>SceneDepth->Desc.Extent.Y)return Out;
 auto Desc=FRDGTextureDesc::Create2D(SceneDepth->Desc.Extent,PF_A32B32G32R32F,FClearValueBinding::Transparent,
  TexCreate_RenderTargetable|TexCreate_ShaderResource);
 Out.NormalMask=GraphBuilder.CreateTexture(Desc,TEXT("Fur.Surface.NormalMask"));
 // Keep full float depth until the recovered conservative-half conversion.
 Desc.Format=PF_A32B32G32R32F;
 Out.StrandDepth=GraphBuilder.CreateTexture(Desc,TEXT("Fur.Surface.StrandDepth"));
 auto* P=GraphBuilder.AllocParameters<FFurSurfacePassParameters>();
 P->View=View.ViewUniformBuffer;
 P->Scene=GetSceneUniformBufferRef(GraphBuilder,View);
 P->RenderTargets[0]=FRenderTargetBinding(Out.NormalMask,ERenderTargetLoadAction::EClear);
 P->RenderTargets[1]=FRenderTargetBinding(Out.StrandDepth,ERenderTargetLoadAction::EClear);
 P->RenderTargets.DepthStencil=FDepthStencilBinding(SceneDepth,ERenderTargetLoadAction::ELoad,
  ERenderTargetLoadAction::ELoad,FExclusiveDepthStencil::DepthRead_StencilNop);
 AddSimpleMeshPass(GraphBuilder,P,Scene,View,InstanceCullingManager,RDG_EVENT_NAME("Fur.Surface"),ViewRect,
  [&](FMeshPassDrawListContext* Context)
  {
   FFurSurfaceProcessor Processor(Scene,View,Context);
   for(const FFurSurfaceMesh& Item:Meshes)
    if(Item.Mesh)Processor.AddMeshBatch(*Item.Mesh,Item.ElementMask,Item.Primitive,Item.StaticMeshId);
   Out.SubmittedBatches=Processor.Submitted;
  });
 return Out;
}

