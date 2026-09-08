#include "FurViewportProbe.h"
#if WITH_EDITOR
#include "Editor.h"
#include "Editor/EditorPerformanceSettings.h"
#include "HAL/IConsoleManager.h"
#include "LevelEditorViewport.h"
#include "ImageUtils.h"
#include "Misc/FileHelper.h"
#include "SceneView.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#endif

void UFurViewportProbe::EnableWorldTicks(bool Enable)
{
#if WITH_EDITOR
    static TOptional<bool> OriginalThrottle;
    UEditorPerformanceSettings* Settings = GetMutableDefault<UEditorPerformanceSettings>();
    if (Enable)
    {
        if (!OriginalThrottle.IsSet()) OriginalThrottle = Settings->bThrottleCPUWhenNotForeground;
        Settings->bThrottleCPUWhenNotForeground = false;
    }
    else if (OriginalThrottle.IsSet())
    {
        Settings->bThrottleCPUWhenNotForeground = OriginalThrottle.GetValue();
        OriginalThrottle.Reset();
    }
    // Intentionally no PostEditChange or SaveConfig: private process only.
#endif
}

bool UFurViewportProbe::Advance()
{
#if WITH_EDITOR
    FLevelEditorViewportClient* Client = GCurrentLevelEditingViewportClient;
    if (!Client || !Client->Viewport) return false;
    IConsoleManager::Get().FindConsoleVariable(TEXT("Slate.bAllowThrottling"))->Set(0, ECVF_SetByConsole);
    const FText Override = FText::FromString(TEXT("Private Fur Validation"));
    Client->RemoveRealtimeOverride(Override, false);
    Client->AddRealtimeOverride(true, Override);
    Client->UpdateViewForLockedActor();
    // Explicitly advance this persistent viewport on the inactive desktop.
    // Caller caps this to ten frames/sec; no focus/window activation is needed.
    Client->Viewport->Draw(false);
    return true;
#else
    return false;
#endif
}

bool UFurViewportProbe::SetVelocityView(bool Enable)
{
#if WITH_EDITOR
    FLevelEditorViewportClient* Client = GCurrentLevelEditingViewportClient;
    if (!Client || !Client->Viewport) return false;
    if (Enable) Client->ChangeBufferVisualizationMode(FName(TEXT("Velocity")));
    else Client->SetViewMode(VMI_Lit);
    return true;
#else
    return false;
#endif
}

FString UFurViewportProbe::Capture(const FString& Filename)
{
#if WITH_EDITOR
    FLevelEditorViewportClient* Client = GCurrentLevelEditingViewportClient;
    if (!Client || !Client->Viewport) return TEXT("{\"error\":\"No viewport\"}");
    FViewport* Viewport = Client->Viewport;
    TArray<FColor> Pixels;
    if (!Viewport->ReadPixels(Pixels)) return TEXT("{\"error\":\"ReadPixels failed\"}");
    const FIntPoint Size = Viewport->GetSizeXY();
    for (FColor& Pixel : Pixels) Pixel.A = 255;
    TArray64<uint8> PNG;
    FImageUtils::PNGCompressImageArray(Size.X, Size.Y, Pixels, PNG);
    if (!FFileHelper::SaveArrayToFile(PNG, *Filename)) return TEXT("{\"error\":\"Save failed\"}");
    FSceneViewFamilyContext Family(FSceneViewFamily::ConstructionValues(
        Viewport, Client->GetScene(), Client->EngineShowFlags).SetRealtimeUpdate(
            Client->IsRealtime()));
    FSceneView* View = Client->CalcSceneView(&Family);
    TSharedRef<FJsonObject> Data = MakeShared<FJsonObject>();
    Data->SetNumberField(TEXT("width"), Size.X);
    Data->SetNumberField(TEXT("height"), Size.Y);
    Data->SetBoolField(TEXT("realtime"), Client->IsRealtime());
    Data->SetBoolField(TEXT("draw_realtime"), Family.bRealtimeUpdate);
    Data->SetBoolField(TEXT("slate_throttling_disabled"),
        IConsoleManager::Get().FindConsoleVariable(TEXT("Slate.bAllowThrottling"))->GetInt()==0);
    Data->SetBoolField(TEXT("post_processing"), Client->EngineShowFlags.PostProcessing);
    Data->SetBoolField(TEXT("aa_flag"), Client->EngineShowFlags.AntiAliasing);
    Data->SetBoolField(TEXT("temporal_flag"), Client->EngineShowFlags.TemporalAA);
    Data->SetNumberField(TEXT("resolved_aa_method"), View ? int32(View->AntiAliasingMethod) : -1);
    Data->SetBoolField(TEXT("velocity_view"), Client->IsBufferVisualizationModeSelected(FName(TEXT("Velocity"))));
    for (const TCHAR* Name : {TEXT("r.Velocity.EnableVertexDeformation"), TEXT("r.VelocityOutputPass")})
    {
        if (IConsoleVariable* Variable = IConsoleManager::Get().FindConsoleVariable(Name))
            Data->SetNumberField(Name, Variable->GetInt());
    }
    Data->SetStringField(TEXT("image"), Filename);
    FString Result;
    FJsonSerializer::Serialize(Data, TJsonWriterFactory<>::Create(&Result));
    return Result;
#else
    return TEXT("{\"error\":\"Editor required\"}");
#endif
}
