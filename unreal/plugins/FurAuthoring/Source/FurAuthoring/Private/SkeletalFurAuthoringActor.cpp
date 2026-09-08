#include "SkeletalFurAuthoringActor.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"

ASkeletalFurAuthoringActor::ASkeletalFurAuthoringActor()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.bStartWithTickEnabled = true;
    ShellCount = 16;
    bUseMapControls = true;
    WindStrength = 0.f;
}

void ASkeletalFurAuthoringActor::SetPoseSource(USkinnedMeshComponent* NewSource)
{
    // Reject self-owned followers; otherwise rebuilding would destroy the source.
    if (NewSource && NewSource->GetOwner() == this) return;
    PoseSource = NewSource;
    RebuildFur();
}

void ASkeletalFurAuthoringActor::UseMappedFur()
{
    FurMaterial = LoadObject<UMaterialInterface>(nullptr,
        TEXT("/FurAuthoring/Materials/M_FurSkeletal.M_FurSkeletal"));
    bUseMapControls = true;
    RebuildFur();
}

bool ASkeletalFurAuthoringActor::RefreshPreviewPose()
{
#if WITH_EDITOR
    auto* Source = Cast<USkeletalMeshComponent>(PoseSource);
    if (!IsValid(Source) || !GetWorld() || GetWorld()->IsGameWorld()) return false;
    Source->TickAnimation(0.f, false);
    Source->RefreshBoneTransforms();
    Source->UpdateComponentToWorld();
    Source->MarkRenderTransformDirty();
    Source->MarkRenderDynamicDataDirty();
    for (USkeletalMeshComponent* Layer : SkeletalShells)
        if (IsValid(Layer)) Layer->MarkRenderDynamicDataDirty();
    return true;
#else
    return false;
#endif
}

void ASkeletalFurAuthoringActor::RebuildFur()
{
    for (USkeletalMeshComponent* Layer : SkeletalShells)
        if (IsValid(Layer)) Layer->DestroyComponent();
    SkeletalShells.Reset();
    LayerMaterials.Reset();
    DynamicMaterial = nullptr;
    Shells->ClearInstances();
    Shells->SetStaticMesh(nullptr);
    SourceMesh = nullptr;
    USkinnedMeshComponent* Source = IsValid(PoseSource) ? PoseSource.Get() : nullptr;
    if (Source && Source->GetOwner() == this) Source = nullptr;
    USkeletalMesh* Mesh = Source ? Cast<USkeletalMesh>(Source->GetSkinnedAsset()) : nullptr;
    BuiltSource = Source;
    BuiltMesh = Mesh;
    if (!Source || !Mesh) return;
    if (!FurMaterial)
        FurMaterial = LoadObject<UMaterialInterface>(nullptr,
            TEXT("/FurAuthoring/Materials/M_FurSkeletal.M_FurSkeletal"));
    if (!FurMaterial) return;
    // Reflect the supported value in Details and in inherited material controls.
    ShellCount = FMath::Clamp(ShellCount, 1, 32);
    const int32 Count = ShellCount;
    for (int32 Index = 0; Index < Count; ++Index)
    {
        auto* Layer = NewObject<USkeletalMeshComponent>(this, NAME_None, RF_Transient);
        Layer->CreationMethod = EComponentCreationMethod::UserConstructionScript;
        Layer->SetSkeletalMeshAsset(Mesh);
        Layer->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Layer->SetGenerateOverlapEvents(false);
        Layer->SetCanEverAffectNavigation(false);
        Layer->SetCastShadow(true);
        Layer->SetupAttachment(Source);
        Layer->SetRelativeTransform(FTransform::Identity);
        Layer->SetLeaderPoseComponent(Source, true, false);
        Layer->RegisterComponent();
        auto* Material = UMaterialInstanceDynamic::Create(FurMaterial, this);
        for (int32 Slot = 0; Slot < Mesh->GetMaterials().Num(); ++Slot)
            Layer->SetMaterial(Slot, Material);
        Material->SetScalarParameterValue(TEXT("ShellDepth"), float(Index) / float(Count));
        SkeletalShells.Add(Layer);
        LayerMaterials.Add(Material);
    }
    UpdateParameters();
}

void ASkeletalFurAuthoringActor::UpdateParameters()
{
    for (UMaterialInstanceDynamic* Material : LayerMaterials)
    {
        DynamicMaterial = Material;
        Super::UpdateParameters();
        // Match the existing geometry even if a Blueprint edits ShellCount
        // before the explicit rebuild that applies that new request.
        Material->SetScalarParameterValue(TEXT("RecoveredShellCount"), float(SkeletalShells.Num()));
    }
    DynamicMaterial = LayerMaterials.IsEmpty() ? nullptr : LayerMaterials[0];
    if (USkeletalMesh* Mesh = BuiltMesh.Get())
    {
        const float Radius = FMath::Max(Mesh->GetBounds().SphereRadius, 1.f);
        for (USkeletalMeshComponent* Layer : SkeletalShells)
            if (IsValid(Layer)) Layer->SetBoundsScale(1.f + FMath::Clamp(Length, 0.f, 30.f) / Radius);
    }
}

void ASkeletalFurAuthoringActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    USkinnedMeshComponent* Source = IsValid(PoseSource) ? PoseSource.Get() : nullptr;
    USkeletalMesh* Mesh = Source ? Cast<USkeletalMesh>(Source->GetSkinnedAsset()) : nullptr;
    if (Source != BuiltSource.Get() || Mesh != BuiltMesh.Get() || (!Source && !SkeletalShells.IsEmpty()))
        RebuildFur();
}
