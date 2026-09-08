#include "FurViewportProbe.h"
#if WITH_EDITOR
#include "Editor.h"
#include "LevelEditorViewport.h"
#include "SceneViewExtension.h"
#include "ScenePrivate.h"
#include "SceneRendering.h"
#include "PostProcess/PostProcessInputs.h"
#include "SceneTexturesConfig.h"
#include "FurSurfacePass.h"
#include "FurDenoise.h"
#include "RenderGraphUtils.h"
#include "StaticMeshBatch.h"
#include "PrimitiveSceneInfo.h"
#include "RenderGraphBuilder.h"
#include "Misc/FileHelper.h"
#include "Misc/ScopeLock.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
BEGIN_SHADER_PARAMETER_STRUCT(FFurSurfaceReadbackParameters,)
 RDG_TEXTURE_ACCESS(Color,ERHIAccess::CopySrc)
 RDG_TEXTURE_ACCESS(Filtered,ERHIAccess::CopySrc)
 RDG_TEXTURE_ACCESS(NormalMask,ERHIAccess::CopySrc)
 RDG_TEXTURE_ACCESS(StrandDepth,ERHIAccess::CopySrc)
END_SHADER_PARAMETER_STRUCT()
class FFurSurfaceReader:public FSceneViewExtensionBase
{
public:
 FFurSurfaceReader(const FAutoRegister& R):FSceneViewExtensionBase(R){}
 FCriticalSection Mutex;
 bool Enabled=false;
 FString Pending,Status=TEXT("idle");
 const FRenderTarget* Target=nullptr;
 void SetupViewFamily(FSceneViewFamily&) override{}
 void SetupView(FSceneViewFamily&,FSceneView&) override{}
 void BeginRenderViewFamily(FSceneViewFamily&) override{}
 void PrePostProcessPass_RenderThread(FRDGBuilder& GraphBuilder,const FSceneView& Base,const FPostProcessingInputs& Inputs) override
 {
  FString Filename;
  {FScopeLock Lock(&Mutex);if((Pending.IsEmpty() && !Enabled) || !Base.Family || Base.Family->RenderTarget!=Target)return;
   Filename=MoveTemp(Pending);Pending.Reset();Status=TEXT("reading");}
  if(!Base.bIsViewInfo || !Inputs.SceneTextures){FScopeLock Lock(&Mutex);Status=TEXT("error: missing view");return;}
  const FViewInfo& View=static_cast<const FViewInfo&>(Base);
  const FScene* Scene=View.Family->Scene->GetRenderScene();
  TArray<FFurSurfaceMesh> Meshes;
  for(const auto& Batch:View.DynamicMeshElements)
   if(Batch.GetHasMaskedMaterial() && Batch.GetRenderInMainPass())
    Meshes.Add({Batch.Mesh,Batch.PrimitiveSceneProxy,~0ull,INDEX_NONE});
  for(auto It=Scene->StaticMeshes.CreateConstIterator();It;++It)
  {
   const FStaticMeshBatch* Mesh=*It;
   if(Mesh && Mesh->Id<View.StaticMeshVisibilityMap.Num() && View.StaticMeshVisibilityMap[Mesh->Id])
    Meshes.Add({Mesh,Mesh->PrimitiveSceneInfo->Proxy,~0ull,Mesh->Id});
  }
  const auto Surface=AddFurSurfacePass(GraphBuilder,View,Scene,nullptr,
   Inputs.SceneTextures->GetParameters()->SceneDepthTexture,View.ViewRect,Meshes);
  if(!Surface.NormalMask || Surface.SubmittedBatches==0){FScopeLock Lock(&Mutex);Status=FString::Printf(TEXT("error: no fur batches (candidates=%d dynamic=%d static=%d)"),Meshes.Num(),View.DynamicMeshElements.Num(),Scene->StaticMeshes.Num());return;}
  // One-shot private integration probe. Keep the matching pre-TAA scene inputs.
  auto Crop=[&](FRDGTexture* Source,const TCHAR* Name)
  {
   auto Desc=Source->Desc;Desc.Extent=View.ViewRect.Size();
   auto* TargetTexture=GraphBuilder.CreateTexture(Desc,Name);
   FRHICopyTextureInfo Info;Info.SourcePosition=FIntVector(View.ViewRect.Min.X,View.ViewRect.Min.Y,0);
   Info.Size=FIntVector(View.ViewRect.Width(),View.ViewRect.Height(),1);
   AddCopyTexturePass(GraphBuilder,Source,TargetTexture,Info);return TargetTexture;
  };
  FRDGTexture* Original=Inputs.SceneTextures->GetParameters()->SceneColorTexture;
  if(!Original || Original->Desc.Format!=PF_FloatRGBA || !View.IsPerspectiveProjection())
  {FScopeLock Lock(&Mutex);Status=TEXT("error: unsupported scene color/projection");return;}
  FFurDenoiseInputs Filter;
  Filter.SceneColor=Crop(Original,TEXT("Fur.ProbeColor"));
  Filter.NormalMask=Crop(Surface.NormalMask,TEXT("Fur.ProbeNormal"));
  Filter.StrandDepth=Crop(Surface.StrandDepth,TEXT("Fur.ProbeStrand"));
  Filter.ActiveTiles=AddFurActiveTilesPass(GraphBuilder,Filter.NormalMask);
  const FMatrix& Projection=View.ViewMatrices.GetViewToClip();
  const double X=Projection.M[0][0],Y=Projection.M[1][1];
  const double JX=Projection.M[2][0],JY=Projection.M[2][1];
  Filter.ScreenToView=FVector4f(2/X,-2/Y,(-1-JX)/X,(1-JY)/Y);
  Filter.ViewToScreen=FVector4f(X*.5,-Y*.5,.5+JX*.5,.5-JY*.5);
  const FMatrix& WorldToView=View.ViewMatrices.GetWorldToView();
  Filter.WorldToView=FMatrix44f::Identity;
  // Native vectors are UE xzy. Both Unreal and this adapter use row-vector matrices.
  for(int Row=0;Row<3;++Row)for(int Col=0;Col<3;++Col)
   Filter.WorldToView.M[Row][Col]=WorldToView.M[Row==1?2:Row==2?1:0][Col];
  const auto& Uniforms=*View.CachedViewUniformShaderParameters;
  uint32 Index=(Uniforms.StateFrameIndex&31u)+1u;float Weight=.5f;
  Filter.TemporalIndex=0;
  while(Index){Filter.TemporalIndex+=(Index&1u)*Weight;Index>>=1;Weight*=.5f;}
  Filter.TemporalCycle=Uniforms.StateFrameIndex%160u;
  Filter.PreExposure=Uniforms.PreExposure;
  Filter.PixelOffset=View.ViewRect.Min;
  auto* Filtered=AddRecoveredFurDenoisePass(GraphBuilder,Filter);
  if(!Filtered){FScopeLock Lock(&Mutex);Status=TEXT("error: invalid filter inputs");return;}
  auto* P=GraphBuilder.AllocParameters<FFurSurfaceReadbackParameters>();
  P->Color=Filter.SceneColor;P->Filtered=Filtered;
  P->NormalMask=Surface.NormalMask;P->StrandDepth=Surface.StrandDepth;
  const FIntRect Rect=View.ViewRect;
  if(!Filename.IsEmpty())GraphBuilder.AddPass(RDG_EVENT_NAME("PrivateFurSurfaceReadback"),P,ERDGPassFlags::Readback,
   [this,Surface,Rect,Filename,Filter,Filtered](FRHICommandListImmediate& RHICmdList)
   {
    FReadSurfaceDataFlags Flags(RCM_MinMax);Flags.SetLinearToGamma(false);
    TArray<FLinearColor> Normal,Strand,Color,Result;
    RHICmdList.ReadSurfaceData(Filter.SceneColor->GetRHI(),FIntRect(FIntPoint::ZeroValue,Rect.Size()),Color,Flags);
    RHICmdList.ReadSurfaceData(Filtered->GetRHI(),FIntRect(FIntPoint::ZeroValue,Rect.Size()),Result,Flags);
    RHICmdList.ReadSurfaceData(Surface.NormalMask->GetRHI(),Rect,Normal,Flags);
    RHICmdList.ReadSurfaceData(Surface.StrandDepth->GetRHI(),Rect,Strand,Flags);
    bool Saved=Normal.Num()==Rect.Area() && Strand.Num()==Rect.Area();
    if(Saved)Saved=FFileHelper::SaveArrayToFile(TArrayView<const uint8>((const uint8*)Normal.GetData(),Normal.Num()*sizeof(FLinearColor)),*(Filename+TEXT("-normal.f32")))
     && FFileHelper::SaveArrayToFile(TArrayView<const uint8>((const uint8*)Strand.GetData(),Strand.Num()*sizeof(FLinearColor)),*(Filename+TEXT("-strand.f32")));
    if(Saved)Saved=FFileHelper::SaveArrayToFile(TArrayView<const uint8>((const uint8*)Color.GetData(),Color.Num()*sizeof(FLinearColor)),*(Filename+TEXT("-color.f32")))
     && FFileHelper::SaveArrayToFile(TArrayView<const uint8>((const uint8*)Result.GetData(),Result.Num()*sizeof(FLinearColor)),*(Filename+TEXT("-filtered.f32")));
    TSharedRef<FJsonObject> Data=MakeShared<FJsonObject>();
    Data->SetNumberField(TEXT("pre_exposure"),Filter.PreExposure);
    Data->SetNumberField(TEXT("temporal_index"),Filter.TemporalIndex);
    Data->SetNumberField(TEXT("temporal_cycle"),Filter.TemporalCycle);
    Data->SetNumberField(TEXT("width"),Rect.Width());Data->SetNumberField(TEXT("height"),Rect.Height());
    Data->SetNumberField(TEXT("submitted_batches"),Surface.SubmittedBatches);Data->SetBoolField(TEXT("saved"),Saved);
    Data->SetStringField(TEXT("storage"),TEXT("float32 RGBA; decoded native world vectors; mask and depth meters"));
    FString Json;FJsonSerializer::Serialize(Data,TJsonWriterFactory<>::Create(&Json));
    if(Saved)Saved=FFileHelper::SaveStringToFile(Json,*(Filename+TEXT(".json")));
    FScopeLock Lock(&Mutex);Status=Saved?TEXT("complete"):TEXT("error: save failed");
   });
  // Scene-color replacement is confined to this requested probe frame, before TAA.
  FRHICopyTextureInfo CopyBack;CopyBack.DestPosition=FIntVector(Rect.Min.X,Rect.Min.Y,0);
  CopyBack.Size=FIntVector(Rect.Width(),Rect.Height(),1);
  AddCopyTexturePass(GraphBuilder,Filtered,Original,CopyBack);
 }
};
static TSharedPtr<FFurSurfaceReader,ESPMode::ThreadSafe> SurfaceReader;
#endif
bool UFurViewportProbe::ArmSurfaceReadback(const FString& Filename)
{
#if WITH_EDITOR
 auto* Client=GCurrentLevelEditingViewportClient;
 if(!Client || !Client->Viewport || Filename.IsEmpty())return false;
 if(!SurfaceReader)SurfaceReader=FSceneViewExtensions::NewExtension<FFurSurfaceReader>();
 FScopeLock Lock(&SurfaceReader->Mutex);
 if(SurfaceReader->Status==TEXT("pending") || SurfaceReader->Status==TEXT("reading"))return false;
 SurfaceReader->Pending=Filename;SurfaceReader->Target=Client->Viewport;SurfaceReader->Status=TEXT("pending");return true;
#else
 return false;
#endif
}
FString UFurViewportProbe::SurfaceReadbackStatus()
{
#if WITH_EDITOR
 if(!SurfaceReader)return TEXT("idle");FScopeLock Lock(&SurfaceReader->Mutex);return SurfaceReader->Status;
#else
 return TEXT("error: editor required");
#endif
}

bool UFurViewportProbe::SetSurfaceFilterEnabled(bool Enabled)
{
#if WITH_EDITOR
 auto* Client=GCurrentLevelEditingViewportClient;
 if(!Client || !Client->Viewport)return false;
 if(!SurfaceReader)SurfaceReader=FSceneViewExtensions::NewExtension<FFurSurfaceReader>();
 FScopeLock Lock(&SurfaceReader->Mutex);
 SurfaceReader->Target=Client->Viewport;SurfaceReader->Enabled=Enabled;return true;
#else
 return false;
#endif
}
