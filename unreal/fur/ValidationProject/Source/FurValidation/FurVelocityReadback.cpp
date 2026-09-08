#include "FurViewportProbe.h"
#if WITH_EDITOR
#include "Editor.h"
#include "LevelEditorViewport.h"
#include "SceneViewExtension.h"
#include "SceneView.h"
#include "FXRenderingUtils.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "Misc/FileHelper.h"
#include "Misc/ScopeLock.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
BEGIN_SHADER_PARAMETER_STRUCT(FFurVelocityReadbackParameters, )
 RDG_TEXTURE_ACCESS(Velocity, ERHIAccess::CopySrc)
END_SHADER_PARAMETER_STRUCT()
class FFurVelocityReadback : public FSceneViewExtensionBase
{
public:
 FFurVelocityReadback(const FAutoRegister& Register):FSceneViewExtensionBase(Register){}
 FCriticalSection Mutex;
 FString Pending, Status=TEXT("idle");
 const FRenderTarget* Target=nullptr;
 virtual void SetupViewFamily(FSceneViewFamily&) override {}
 virtual void SetupView(FSceneViewFamily&,FSceneView&) override {}
 virtual void BeginRenderViewFamily(FSceneViewFamily&) override {}
 virtual void PrePostProcessPass_RenderThread(FRDGBuilder& GraphBuilder,const FSceneView& View,const FPostProcessingInputs&) override
 {
  FString Filename;
  { FScopeLock Lock(&Mutex);
    if(Pending.IsEmpty() || !View.Family || View.Family->RenderTarget!=Target)return;
    Filename=MoveTemp(Pending);Pending.Reset();Status=TEXT("reading"); }
  FRDGTextureRef Texture=UE::FXRenderingUtils::GetSceneVelocityTexture(View);
  if(!Texture || Texture->Desc.Extent.X>4096 || Texture->Desc.Extent.Y>4096)
  { FScopeLock Lock(&Mutex);Status=TEXT("error: missing or oversized texture");return; }
  const FIntRect Rect=UE::FXRenderingUtils::GetRawViewRectUnsafe(View);
  const FString Format=GPixelFormats[Texture->Desc.Format].Name;
  const double WorldTime=View.Family->Time.GetWorldTimeSeconds();
  auto* Parameters=GraphBuilder.AllocParameters<FFurVelocityReadbackParameters>();Parameters->Velocity=Texture;
  GraphBuilder.AddPass(RDG_EVENT_NAME("PrivateFurVelocityReadback"),Parameters,ERDGPassFlags::Readback,
   [this,Texture,Rect,Format,Filename,WorldTime](FRHICommandListImmediate& RHICmdList)
   {
    TArray<FLinearColor> Pixels;FReadSurfaceDataFlags Flags(RCM_MinMax);Flags.SetLinearToGamma(false);
    RHICmdList.ReadSurfaceData(Texture->GetRHI(),Rect,Pixels,Flags);
    bool Saved=Pixels.Num()==Rect.Area();
    if(Saved)Saved=FFileHelper::SaveArrayToFile(TArrayView<const uint8>(reinterpret_cast<const uint8*>(Pixels.GetData()),Pixels.Num()*sizeof(FLinearColor)),*Filename);
    TSharedRef<FJsonObject> Data=MakeShared<FJsonObject>();
    Data->SetNumberField(TEXT("width"),Rect.Width());Data->SetNumberField(TEXT("height"),Rect.Height());
    Data->SetStringField(TEXT("format"),Format);Data->SetStringField(TEXT("storage"),TEXT("little-endian float32 RGBA; linear encoded velocity, no display conversion"));
    Data->SetNumberField(TEXT("world_time"),WorldTime);Data->SetBoolField(TEXT("saved"),Saved);Data->SetStringField(TEXT("file"),Filename);
    FString Json;FJsonSerializer::Serialize(Data,TJsonWriterFactory<>::Create(&Json));
    if(Saved)Saved=FFileHelper::SaveStringToFile(Json,*(Filename+TEXT(".json")));
    FScopeLock Lock(&Mutex);Status=Saved?TEXT("complete"):TEXT("error: readback/save failed");
   });
 }
};
static TSharedPtr<FFurVelocityReadback,ESPMode::ThreadSafe> FurVelocityReader;
#endif
bool UFurViewportProbe::ArmVelocityReadback(const FString& Filename)
{
#if WITH_EDITOR
 auto* Client=GCurrentLevelEditingViewportClient;
 if(!Client || !Client->Viewport || Filename.IsEmpty())return false;
 if(!FurVelocityReader)FurVelocityReader=FSceneViewExtensions::NewExtension<FFurVelocityReadback>();
 FScopeLock Lock(&FurVelocityReader->Mutex);
 if(FurVelocityReader->Status==TEXT("pending") || FurVelocityReader->Status==TEXT("reading"))return false;
 FurVelocityReader->Pending=Filename;FurVelocityReader->Target=Client->Viewport;FurVelocityReader->Status=TEXT("pending");return true;
#else
 return false;
#endif
}
FString UFurViewportProbe::VelocityReadbackStatus()
{
#if WITH_EDITOR
 if(!FurVelocityReader)return TEXT("idle");FScopeLock Lock(&FurVelocityReader->Mutex);return FurVelocityReader->Status;
#else
 return TEXT("error: editor required");
#endif
}
