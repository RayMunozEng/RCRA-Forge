#pragma once
#include "FurAuthoringActor.h"
#include "SkeletalFurAuthoringActor.generated.h"

class USkinnedMeshComponent;
class USkeletalMeshComponent;
class USkeletalMesh;

/** Pose-sharing shell fur. The source remains responsible for animation. */
UCLASS(Blueprintable, meta=(DisplayName="Skeletal Fur Actor"))
class FURAUTHORING_API ASkeletalFurAuthoringActor : public AFurAuthoringActor
{
    GENERATED_BODY()
public:
    ASkeletalFurAuthoringActor();
    UPROPERTY(EditInstanceOnly, BlueprintReadOnly, Category="Fur|Animation", meta=(UseComponentPicker, AllowedClasses="/Script/Engine.SkinnedMeshComponent", ToolTip="Animated source component. For Blueprint setup use Set Pose Source. Static Source Mesh is unused by this actor."))
    TObjectPtr<USkinnedMeshComponent> PoseSource;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category="Fur|Animation")
    TArray<TObjectPtr<USkeletalMeshComponent>> SkeletalShells;
    UFUNCTION(BlueprintCallable, Category="Fur|Animation")
    void SetPoseSource(USkinnedMeshComponent* NewSource);
    /** Evaluate the current source animation pose in an editor preview. No effect in game worlds. */
    UFUNCTION(BlueprintCallable, CallInEditor, Category="Fur|Animation")
    bool RefreshPreviewPose();
    virtual void RebuildFur() override;
    virtual void UseMappedFur() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual bool ShouldTickIfViewportsOnly() const override { return true; }
protected:
    virtual void UpdateParameters() override;
private:
    UPROPERTY(Transient)
    TArray<TObjectPtr<UMaterialInstanceDynamic>> LayerMaterials;
    TWeakObjectPtr<USkinnedMeshComponent> BuiltSource;
    TWeakObjectPtr<USkeletalMesh> BuiltMesh;
};
