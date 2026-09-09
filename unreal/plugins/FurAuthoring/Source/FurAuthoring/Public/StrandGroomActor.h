#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ProceduralMeshComponent.h"
#include "StrandGroomActor.generated.h"

class UMaterialInstanceDynamic;
class UMaterialInterface;
class UStrandGroomAsset;
class USkinnedMeshComponent;

/** Discrete authored strands for character accents; independent of shell fur. */
UCLASS(Blueprintable, meta=(DisplayName="Strand Groom Actor"))
class FURAUTHORING_API AStrandGroomActor : public AActor
{
    GENERATED_BODY()
public:
    AStrandGroomActor();
    virtual void OnConstruction(const FTransform& Transform) override;
    virtual void Tick(float DeltaSeconds) override;
    virtual bool ShouldTickIfViewportsOnly() const override { return true; }

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Strand Groom")
    TObjectPtr<UProceduralMeshComponent> Ribbons;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Source")
    TObjectPtr<UStrandGroomAsset> GroomAsset;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Source")
    TObjectPtr<UMaterialInterface> StrandMaterial;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Source")
    TObjectPtr<USkinnedMeshComponent> BindingMesh;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Shape", meta=(ClampMin="0.001", Units="cm"))
    float StrandWidth = 0.08f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Shape", meta=(ClampMin="0", ClampMax="20"))
    int32 TessellationOverride = 0;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Appearance")
    FLinearColor RootColor = FLinearColor(0.08f, 0.035f, 0.015f);
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Appearance")
    FLinearColor TipColor = FLinearColor(0.45f, 0.22f, 0.08f);
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Appearance")
    FVector SceneKeyDirection = FVector(.6f, .8f, 1.f);
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Appearance")
    FLinearColor SceneKeyRadiance = FLinearColor::White;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Simulation", meta=(ClampMin="0"))
    float WindStrength = 0.04f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Simulation")
    FVector WindDirection = FVector(1, 0, 0);
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Simulation", meta=(ClampMin="0", ClampMax="1"))
    float WindTurbulence = 0.f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Simulation", meta=(ClampMin="0"))
    float StiffnessInverseLength = 20.f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Simulation", meta=(ClampMin="0"))
    float StiffnessPower = 2.f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Simulation", meta=(ClampMin="0", ClampMax="1"))
    float Drag = 0.5f;
    /** Half-precision per-object animation force read by the retail wind shader. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Simulation", meta=(ClampMin="0", ClampMax="1"))
    float AnimationForce = 0.13269043f;
    /** Object radius in metres used to cap the directional wind contribution. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Simulation", meta=(ClampMin="0", Units="m"))
    float WindRadiusMetres = 0.47065133f;
    /** Phase origin; the default is the value captured at retail tail event 24762. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Simulation")
    float WindTimerOffset = 981.71575928f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom|Weather", meta=(ClampMin="0", ClampMax="1"))
    float Wetness = 0.f;

    UFUNCTION(BlueprintCallable, CallInEditor, Category="Strand Groom")
    void RebuildGroom();
    UFUNCTION(BlueprintCallable, Category="Strand Groom|Weather")
    void SetStrandWeather(float NewWetness, float NewWindStrength);
    UFUNCTION(BlueprintCallable, Category="Strand Groom|Appearance")
    void SetStrandLighting(FVector KeyDirection, FLinearColor KeyRadiance);
    UFUNCTION(BlueprintCallable, Category="Strand Groom|Simulation")
    void ResetSimulation();
    UFUNCTION(BlueprintPure, Category="Strand Groom|Simulation")
    float GetMaximumDisplacementCm() const;
    /** Current skinned root position for evidence-backed binding tests. */
    UFUNCTION(BlueprintPure, Category="Strand Groom|Binding")
    FVector GetGuideRootWorldPosition(int32 GuideIndex) const;
    /** Current skinned root normal; proves the authored groom rotates with pose. */
    UFUNCTION(BlueprintPure, Category="Strand Groom|Binding")
    FVector GetGuideRootWorldNormal(int32 GuideIndex) const;
    /** Current skinned secondary root frame; used by retail clump placement. */
    UFUNCTION(BlueprintPure, Category="Strand Groom|Binding")
    FVector GetGuideRootWorldFrameY(int32 GuideIndex) const;

private:
    UPROPERTY(Transient)
    TObjectPtr<UMaterialInstanceDynamic> DynamicMaterial;
    TArray<FVector> RestPositions;
    TArray<FVector> SkinnedBasePositions;
    TArray<FVector> CurrentPositions;
    TArray<FVector> PreviousPositions;
    TArray<FVector> SkinnedRootNormals;
    TArray<FVector> SkinnedRootFrameYs;
    TArray<int32> GuideOffsets;
    TArray<float> RestLengths;
    TArray<FTransform> ReferenceComponentTransforms;
    TArray<FVector> MeshVertices;
    TArray<FVector> MeshNormals;
    TArray<FVector2D> MeshUVs;
    TArray<FVector2D> MeshUV1s;
    TArray<FVector2D> MeshUV2s;
    TArray<FVector2D> MeshUV3s;
    TArray<FLinearColor> MeshColors;
    TArray<FProcMeshTangent> MeshTangents;
    TArray<int32> MeshTriangles;
    int32 BuiltTessellation = 0;

    void Simulate(float DeltaSeconds);
    void BuildRibbonVertices();
    void UpdateMaterialParameters();
    FVector SampleGuide(int32 GuideIndex, float Fraction) const;
    void BuildSkinnedBasePositions();
};
