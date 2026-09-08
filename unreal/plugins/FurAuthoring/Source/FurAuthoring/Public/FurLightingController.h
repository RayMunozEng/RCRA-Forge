#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "FurLightingController.generated.h"

class ADirectionalLight;
class AFurAuthoringActor;
class USceneCaptureComponent2D;
class UTextureRenderTarget2D;
class UTextureCube;
class UTexture2D;

/** Recovered key, fill and rim lighting with a bounded key-light depth map. */
UCLASS(Blueprintable)
class FURAUTHORING_API AFurLightingController : public AActor
{
    GENERATED_BODY()
public:
    AFurLightingController();
    virtual void Tick(float DeltaSeconds) override;
    virtual void OnConstruction(const FTransform& Transform) override;
    virtual bool ShouldTickIfViewportsOnly() const override { return true; }
    UPROPERTY(EditInstanceOnly, BlueprintReadWrite, Category="Fur Lighting")
    TObjectPtr<ADirectionalLight> KeyLight;
    /** Optional additive fill. Evaluates the recovered hair lobes; no shadow capture. */
    UPROPERTY(EditInstanceOnly, BlueprintReadWrite, Category="Fur Lighting")
    TObjectPtr<ADirectionalLight> FillLight;
    /** Optional additive rim. Duplicate key/fill assignments are ignored. No shadow capture. */
    UPROPERTY(EditInstanceOnly, BlueprintReadWrite, Category="Fur Lighting")
    TObjectPtr<ADirectionalLight> RimLight;

    UPROPERTY(EditInstanceOnly, BlueprintReadWrite, Category="Fur Lighting")
    TArray<TObjectPtr<AFurAuthoringActor>> Targets;
    UPROPERTY(EditInstanceOnly, BlueprintReadWrite, Category="Fur Lighting|Shadows")
    TArray<TObjectPtr<AActor>> ShadowCasters;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur Lighting|Shadows")
    bool bEnableShadows = true;
    /** Refresh bone/WPO deformation even when the caster actor does not move. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur Lighting|Shadows")
    bool bRefreshAnimatedCasters = false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur Lighting|Shadows", meta=(EditCondition="bRefreshAnimatedCasters",ClampMin="1",ClampMax="30",Units="Hz"))
    float ShadowUpdatesPerSecond = 10.f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur Lighting|Shadows", meta=(ClampMin="50",ClampMax="2000",Units="cm"))
    float ShadowWidth = 300.f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur Lighting|Shadows", meta=(ClampMin="0.01",ClampMax="10",Units="cm"))
    float ShadowBias = .5f;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Fur Lighting|Shadows")
    TObjectPtr<USceneCaptureComponent2D> ShadowCapture;
    UPROPERTY(Transient, VisibleAnywhere, BlueprintReadOnly, Category="Fur Lighting|Shadows")
    TObjectPtr<UTextureRenderTarget2D> ShadowDepth;
    /** Off preserves existing material settings; turning off restores parent defaults. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur Lighting|Environment")
    bool bOverrideEnvironment = false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur Lighting|Environment", meta=(EditCondition="bOverrideEnvironment"))
    bool bEnableEnvironment = true;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur Lighting|Environment", meta=(EditCondition="bOverrideEnvironment", ToolTip="Linear prefiltered cube. Ordinary Unreal axis orientation."))
    TObjectPtr<UTextureCube> EnvironmentCube;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur Lighting|Environment", meta=(EditCondition="bOverrideEnvironment", DisplayName="Environment BRDF", ToolTip="Linear RG lookup, clamp addressing: U = absolute normal/view cosine, V = gloss."))
    TObjectPtr<UTexture2D> EnvironmentBRDF;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur Lighting|Environment", meta=(EditCondition="bOverrideEnvironment", ClampMin="0", UIMax="4"))
    float EnvironmentIntensity = .6f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur Lighting|Environment", meta=(EditCondition="bOverrideEnvironment", ClampMin="0", ClampMax="16"))
    float EnvironmentMaxMip = 5.f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, AdvancedDisplay, Category="Fur Lighting|Environment", meta=(EditCondition="bOverrideEnvironment"))
    bool bEnvironmentRecoveredAxes = false;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category="Fur Lighting|Environment")
    FString EnvironmentStatus;
    UFUNCTION(BlueprintCallable, Category="Fur Lighting|Environment")
    void SetEnvironment(UTextureCube* Cube, UTexture2D* BRDF, float Intensity = .6f);
    UFUNCTION(BlueprintCallable, CallInEditor, Category="Fur Lighting")
    void RefreshLighting();
    UFUNCTION(BlueprintPure, Category="Fur Lighting|Shadows")
    int32 GetShadowCaptureCount() const { return ShadowCaptureCount; }
private:
    void BindLighting();
    uint32 LastSceneHash = 0;
    bool bShadowValid = false;
    bool bEnvironmentWasOverridden = false;
    float SecondsSinceShadowUpdate = 0.f;
    int32 ShadowCaptureCount = 0;
};
