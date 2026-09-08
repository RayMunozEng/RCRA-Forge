#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "FurViewportProbe.generated.h"

class USkinnedMeshComponent;

// Private fixture diagnostics: never shipped in FurAuthoring.
UCLASS()
class UFurViewportProbe : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="Fur Validation")
    static FString ValidateFurDenoiseGPU();
    UFUNCTION(BlueprintCallable, Category="Fur Validation")
    static bool ArmSurfaceReadback(const FString& Filename);
    UFUNCTION(BlueprintCallable, Category="Fur Validation")
    static FString SurfaceReadbackStatus();
    UFUNCTION(BlueprintCallable, Category="Fur Validation")
    static bool SetSurfaceFilterEnabled(bool Enabled);
    UFUNCTION(BlueprintCallable, Category="Fur Validation")
    static void EnableWorldTicks(bool Enable);
    UFUNCTION(BlueprintCallable, Category="Fur Validation")
    static bool Advance();
    UFUNCTION(BlueprintCallable, Category="Fur Validation")
    static bool SaveSkinnedPose(USkinnedMeshComponent* Component, const FString& Filename);
    UFUNCTION(BlueprintCallable, Category="Fur Validation")
    static void FlushPoseUpdates(USkinnedMeshComponent* Component);
    UFUNCTION(BlueprintCallable, Category="Fur Validation")
    static bool SetVelocityView(bool Enable);
    UFUNCTION(BlueprintCallable, Category="Fur Validation")
    static FString Capture(const FString& Filename);
    UFUNCTION(BlueprintCallable, Category="Fur Validation")
    static bool ArmVelocityReadback(const FString& Filename);
    UFUNCTION(BlueprintCallable, Category="Fur Validation")
    static FString VelocityReadbackStatus();
};
