#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "FurAuthoringActor.generated.h"

class UInstancedStaticMeshComponent;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class UStaticMesh;
class UTexture2D;

/** A non-destructive shell-fur preview using the source mesh's UV0 and normals. */
UCLASS(Blueprintable, meta=(DisplayName="Fur Actor"))
class FURAUTHORING_API AFurAuthoringActor : public AActor
{
    GENERATED_BODY()
public:
    AFurAuthoringActor();
    virtual void OnConstruction(const FTransform& Transform) override;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Source")
    TObjectPtr<UStaticMesh> SourceMesh;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Source")
    TObjectPtr<UMaterialInterface> FurMaterial;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Fur|Source")
    TObjectPtr<UInstancedStaticMeshComponent> Shells;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Shape", meta=(ClampMin="1", ClampMax="64"))
    int32 ShellCount = 24;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Shape", meta=(ClampMin="0", ClampMax="30", Units="cm"))
    float Length = 3.0f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Shape", meta=(ClampMin="1", ClampMax="512"))
    float Density = 100.0f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Shape", meta=(ClampMin="0.02", ClampMax="0.48"))
    float StrandWidth = 0.2f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Groom", meta=(ToolTip="World-space comb direction. Magnitude sets bending relative to fur length."))
    FVector Groom = FVector::ZeroVector;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Appearance")
    FLinearColor RootColor = FLinearColor(0.12f, 0.06f, 0.025f);
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Appearance")
    FLinearColor TipColor = FLinearColor(0.6f, 0.32f, 0.12f);
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Appearance", meta=(ClampMin="0.05", ClampMax="1"))
    float Roughness = 0.65f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Weather", meta=(ClampMin="0", ClampMax="1"))
    float Wetness = 0.0f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Weather", meta=(ClampMin="0", ClampMax="2"))
    float WindStrength = 0.15f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Weather")
    FVector WindDirection = FVector(1, 0, 0);
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Weather", meta=(ClampMin="0", ClampMax="10"))
    float WindSpeed = 1.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Maps", meta=(ToolTip="Enable actor controls for M_FurAuthoringMaps. Existing recovered material instances keep their values when disabled."))
    bool bUseMapControls = false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Maps", meta=(EditCondition="bUseMapControls", ToolTip="Linear texture, red channel: black = no fur length, white = full Length."))
    TObjectPtr<UTexture2D> LengthMap;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Maps", meta=(EditCondition="bUseMapControls", ToolTip="Linear texture, red channel: black = bald, white = full coverage. Base surface remains visible."))
    TObjectPtr<UTexture2D> DensityMap;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Maps", meta=(EditCondition="bUseMapControls", ToolTip="Linear RG direction in UV tangent space. (0.5,0.5) is neutral. Use uncompressed linear color, not normal-map compression."))
    TObjectPtr<UTexture2D> GroomMap;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Maps", meta=(EditCondition="bUseMapControls", ClampMin="1", ClampMax="64"))
    float RecoveredDensity = 12.f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Fur|Maps", meta=(EditCondition="bUseMapControls", ClampMin="0", ClampMax="4"))
    float GroomStrength = 1.f;

    UFUNCTION(BlueprintCallable, CallInEditor, Category="Fur|Maps")
    virtual void UseMappedFur();
    UFUNCTION(BlueprintCallable, Category="Fur|Maps")
    void SetFurMaps(UTexture2D* NewLengthMap, UTexture2D* NewDensityMap, UTexture2D* NewGroomMap);

    UFUNCTION(BlueprintCallable, CallInEditor, Category="Fur")
    virtual void RebuildFur();
    UFUNCTION(BlueprintCallable, CallInEditor, Category="Fur|Presets")
    void ShortFurPreset();
    UFUNCTION(BlueprintCallable, CallInEditor, Category="Fur|Presets")
    void WoolPreset();
    UFUNCTION(BlueprintCallable, Category="Fur|Weather")
    void SetWeather(float NewWetness, float NewWindStrength);
protected:
    UPROPERTY(Transient)
    TObjectPtr<UMaterialInstanceDynamic> DynamicMaterial;
    virtual void UpdateParameters();
};
